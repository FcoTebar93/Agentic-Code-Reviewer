"""
Meta Planner Service -- the orchestrator.

Receives user prompts, decomposes them into tasks via LLM,
and publishes events for the dev_service to consume.

Entry points:
- HTTP POST /plan  (user-facing)
- RabbitMQ consumer for plan.requested events

Idempotency: identical request (prompt + project_name + repo_url) within
IDEM_TTL_SECONDS returns the same plan without re-running the pipeline,
avoiding duplicate task.assigned and duplicate files.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response, agent_execution_time, tasks_completed, llm_tokens
from shared.contracts.events import (
    BaseEvent,
    EventType,
    PlanCreatedPayload,
    PlanRequestedPayload,
    TaskAssignedPayload,
    PlanRevisionPayload,
    TokensUsedPayload,
    plan_created,
    task_assigned,
    metrics_tokens_used,
)
from shared.llm_adapter import get_llm_provider
from shared.utils import EventBus, IdempotencyStore, store_event
from shared.tools import ToolRegistry, execute_tool
from services.meta_planner.config import PlannerConfig
from services.meta_planner.planner import decompose_tasks
from services.meta_planner.tools import build_planner_tool_registry

SERVICE_NAME = "meta_planner"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: PlannerConfig | None = None
tool_registry: ToolRegistry | None = None

_IDEM_TTL_SECONDS = int(os.environ.get("PLAN_IDEM_TTL_SECONDS", "30"))
_plan_idem_cache: dict[str, tuple[str, dict, float]] = {}
_MAX_AUTO_REPLANS_PER_ORIGINAL_PLAN = int(
    os.environ.get("MAX_AUTO_REPLANS_PER_ORIGINAL_PLAN", "1")
)
_replans_per_original_plan: dict[str, int] = {}


def _infer_group_id(file_path: str) -> str:
    """
    Agrupa tareas por módulo aproximado a partir del file_path.

    Se usa tanto en el plan original como en replannings para poder
    limitar revisiones a subconjuntos coherentes de archivos.
    """
    norm = (file_path or "").replace("\\", "/").strip()
    if not norm:
        return "root"
    parts = norm.split("/")
    if len(parts) >= 3:
        return "/".join(parts[:3])
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return norm


def _summarise_planner_memory(
    semantic_results: list[dict] | None,
    events: list[dict] | None,
    max_lines: int = 8,
) -> str:
    """
    Construye un resumen compacto y de alto nivel a partir de:
    - resultados semánticos (plan.created, pipeline.conclusion, qa.failed, security.blocked)
    - eventos recientes crudos

    Objetivo: dar al planner "reglas aprendidas" y contexto mínimo sin volcar
    todos los textos ni scores completos para ahorrar tokens.
    """
    semantic_results = semantic_results or []
    events = events or []

    lines: list[str] = []

    if semantic_results:
        type_counts: dict[str, int] = {}
        for item in semantic_results:
            payload = item.get("payload") or {}
            etype = str(payload.get("event_type", "") or "")
            if not etype:
                continue
            type_counts[etype] = type_counts.get(etype, 0) + 1

        if type_counts:
            summary_parts = [
                f"{etype} x{count}" for etype, count in sorted(type_counts.items())
            ]
            lines.append(
                "Semantic history summary: " + "; ".join(summary_parts)
            )

        for item in semantic_results[:3]:
            payload = item.get("payload") or {}
            score = item.get("heuristic_score", item.get("score", 0.0))
            text = str(payload.get("text", "")).replace("\n", " ")[:200]
            etype = payload.get("event_type", "")
            plan_id = payload.get("plan_id", "")[:8]
            if text:
                lines.append(
                    f"- [{etype}] plan={plan_id} score={score:.2f}: {text}"
                )
            if len(lines) >= max_lines:
                return "\n".join(lines)

    if events and len(lines) < max_lines:
        recent_lines: list[str] = []
        for ev in events[: max_lines - len(lines)]:
            etype = ev.get("event_type", "")
            created = ev.get("created_at", "")[:19]
            pid = (ev.get("payload") or {}).get("plan_id", "")[:8]
            recent_lines.append(f"{created} [{etype}] plan={pid}")
        if recent_lines:
            lines.append("Recent activity:")
            lines.extend(recent_lines)

    return "\n".join(lines)

@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg, tool_registry
    logger = setup_logging(SERVICE_NAME)

    cfg = PlannerConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=10.0)

    tool_registry = build_planner_tool_registry(memory_service_url=cfg.memory_service_url)

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_plan_requests())
    asyncio.create_task(_consume_plan_revisions())
    logger.info("Meta Planner ready (with replanning support)")
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Meta Planner",
    version="0.1.0",
    description="Orchestrates task decomposition and agent coordination",
    lifespan=lifespan,
)
logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

class PlanRequest(BaseModel):
    prompt: str
    project_name: str = "default"
    repo_url: str = ""
    mode: str = "normal"


class PlanResponse(BaseModel):
    plan_id: str
    task_count: int
    tasks: list[dict]


@app.post("/plan", response_model=PlanResponse)
async def create_plan(req: PlanRequest):
    key = hashlib.sha256(
        f"{req.prompt}|{req.project_name}|{req.repo_url}".encode()
    ).hexdigest()
    now = time.monotonic()
    if key in _plan_idem_cache:
        cached_plan_id, cached_resp, cached_at = _plan_idem_cache[key]
        if now - cached_at < _IDEM_TTL_SECONDS:
            logger.info(
                "Idempotent plan request (same key within %ds), returning cached plan %s",
                _IDEM_TTL_SECONDS,
                cached_plan_id[:8],
            )
            return cached_resp
        else:
            del _plan_idem_cache[key]

    try:
        result = await _execute_plan(
            req.prompt,
            req.project_name,
            req.repo_url,
            mode=req.mode or "normal",
        )
        _plan_idem_cache[key] = (result["plan_id"], result, now)
        return result
    except Exception as e:
        err_str = str(e)
        is_rate_limit = (
            "429" in err_str
            or "rate limit" in err_str.lower()
            or "RateLimitError" in (type(e).__name__,)
        )
        if is_rate_limit:
            logger.warning("LLM rate limit (429): %s", err_str[:200])
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Límite de uso del LLM alcanzado (rate limit). Espera unos minutos o cambia de proveedor.",
                    "hint": "Groq free tier: 100k tokens/día. Puedes usar LLM_PROVIDER=gemini o LLM_PROVIDER=local (Ollama) mientras tanto.",
                    "error": err_str[:500],
                    "error_type": type(e).__name__,
                },
            )
        logger.exception("Plan execution failed")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Plan execution failed",
                "error": err_str,
                "error_type": type(e).__name__,
            },
        )

async def _execute_plan(
    prompt: str,
    project_name: str,
    repo_url: str,
    forced_plan_id: str | None = None,
    mode: str = "normal",
) -> dict:
    with agent_execution_time.labels(service=SERVICE_NAME, operation="plan").time():
        llm = get_llm_provider(provider_name=cfg.llm_provider)
        memory_context = await _fetch_memory_context(prompt)
        plan_result, prompt_tokens, completion_tokens = await decompose_tasks(
            llm, prompt, memory_context=memory_context
        )
        seen_paths: set[str] = set()
        task_specs = []
        for spec in plan_result.tasks:
            if spec.file_path in seen_paths:
                continue
            seen_paths.add(spec.file_path)
            gid = (getattr(spec, "group_id", "") or "").strip()
            if not gid:
                try:
                    spec.group_id = _infer_group_id(spec.file_path)
                except Exception:
                    spec.group_id = "root"
            task_specs.append(spec)
        if len(task_specs) < len(plan_result.tasks):
            logger.info(
                "Deduplicated tasks by file_path: %d -> %d",
                len(plan_result.tasks),
                len(task_specs),
            )

        plan_payload = PlanCreatedPayload(
            plan_id=forced_plan_id
            or PlanCreatedPayload.model_fields["plan_id"].default_factory(),
            original_prompt=prompt,
            tasks=task_specs,
            reasoning=plan_result.reasoning,
            mode=mode or "normal",
        )
        plan_event = plan_created(SERVICE_NAME, plan_payload)
        plan_id = plan_payload.plan_id

        if prompt_tokens or completion_tokens:
            tok_event = metrics_tokens_used(
                SERVICE_NAME,
                TokensUsedPayload(
                    plan_id=plan_id,
                    service=SERVICE_NAME,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                ),
            )
            await store_event(
                http_client,
                tok_event,
                logger=logger,
                error_message="Failed to store event %s in memory_service",
            )

        await event_bus.publish(plan_event)
        await store_event(
            http_client,
            plan_event,
            logger=logger,
            error_message="Failed to store event %s in memory_service",
        )

        for spec in task_specs:
            ta_payload = TaskAssignedPayload(
                plan_id=plan_id,
                task=spec,
                repo_url=repo_url,
                plan_reasoning=plan_result.reasoning,
                mode=plan_payload.mode,
            )
            ta_event = task_assigned(SERVICE_NAME, ta_payload)
            await event_bus.publish(ta_event)
            await store_event(
                http_client,
                ta_event,
                logger=logger,
                error_message="Failed to store event %s in memory_service",
            )

        tasks_completed.labels(service=SERVICE_NAME).inc()
        logger.info(
            "Plan %s created with %d tasks. Reasoning: %.60r",
            plan_id[:8],
            len(task_specs),
            plan_result.reasoning,
        )

    return {
        "plan_id": plan_id,
        "task_count": len(task_specs),
        "tasks": [t.model_dump() for t in task_specs],
    }

async def _consume_plan_requests() -> None:
    """
    Listen for plan.requested events from the bus.
    Idempotencia: mismo evento (mismo idempotency_key) no se ejecuta dos veces.
    """
    idem_store = IdempotencyStore()

    async def handler(event: BaseEvent) -> None:
        delay_sec = int(os.environ.get("AGENT_DELAY_SECONDS", "0"))
        if delay_sec > 0:
            logger.info("Agent delay: waiting %ds before processing", delay_sec)
            await asyncio.sleep(delay_sec)
        payload = PlanRequestedPayload.model_validate(event.payload)
        await _execute_plan(
            payload.user_prompt,
            payload.project_name,
            payload.repo_url,
            mode=getattr(payload, "mode", "normal") or "normal",
        )

    await event_bus.subscribe(
        queue_name="meta_planner.plan_requests",
        routing_keys=[EventType.PLAN_REQUESTED.value],
        handler=handler,
        idempotency_store=idem_store,
        max_retries=3,
    )


async def _consume_plan_revisions() -> None:
    """
    Listen for plan.revision_suggested and plan.revision_confirmed events.

    - plan.revision_suggested: suggestion only (no automatic replanning).
    - plan.revision_confirmed: always replan (human confirmed in the UI).
    """

    async def handler(event: BaseEvent) -> None:
        payload = PlanRevisionPayload.model_validate(event.payload)
        if event.event_type == EventType.PLAN_REVISION_SUGGESTED:
            logger.info(
                "Received plan.revision_suggested for %s (severity=%s) - waiting for human confirmation.",
                payload.original_plan_id[:8],
                (payload.severity or "medium"),
            )
            # No automatic replanning on suggestions anymore; wait for plan.revision_confirmed.
            return

        if event.event_type == EventType.PLAN_REVISION_CONFIRMED:
            await _handle_plan_revision(payload)

    await event_bus.subscribe(
        queue_name="meta_planner.plan_revisions",
        routing_keys=[
            EventType.PLAN_REVISION_SUGGESTED.value,
            EventType.PLAN_REVISION_CONFIRMED.value,
        ],
        handler=handler,
    )


async def _handle_plan_revision(payload: PlanRevisionPayload) -> None:
    """
    Replan automatically based on a PlanRevisionPayload.

    - Fetches the original plan.created event to recover the original prompt.
    - Builds an augmented prompt that incorporates the replanner suggestions.
    - Infers the repo_url from the existing task state, if any.
    - Executes a new plan with the provided new_plan_id.
    """
    original_plan_id = payload.original_plan_id
    new_plan_id = payload.new_plan_id

    current_replans = _replans_per_original_plan.get(original_plan_id, 0)
    if current_replans >= _MAX_AUTO_REPLANS_PER_ORIGINAL_PLAN:
        logger.info(
            "Skipping auto-replanning for original plan %s: max auto replans reached (%d)",
            original_plan_id[:8],
            _MAX_AUTO_REPLANS_PER_ORIGINAL_PLAN,
        )
        return

    original_prompt, original_reasoning = await _fetch_original_plan_prompt(
        original_plan_id
    )
    if not original_prompt:
        logger.warning(
            "Could not find original plan.prompt for plan %s; skipping replanning",
            original_plan_id[:8],
        )
        return

    augmented_prompt_lines = [
        original_prompt.strip(),
        "",
        "---",
        f"A replanning agent analysed the previous execution of plan {original_plan_id[:8]} "
        f"and suggested revising the plan.",
        f"Severity: {payload.severity or 'medium'}",
    ]
    target_groups = getattr(payload, "target_group_ids", []) or []
    if target_groups:
        augmented_prompt_lines.append("Scope limitation:")
        augmented_prompt_lines.append(
            "Only replan the following modules/groups; keep the rest of the project "
            "and tasks unchanged as much as possible:"
        )
        for g in target_groups:
            augmented_prompt_lines.append(f"- {g}")
    if payload.reason:
        augmented_prompt_lines.append(f"Replanner reason: {payload.reason}")
    if original_reasoning:
        augmented_prompt_lines.append(
            f"Original planner reasoning (for context, may be outdated): {original_reasoning}"
        )
    if payload.suggestions:
        augmented_prompt_lines.append("")
        augmented_prompt_lines.append("Replanner suggestions:")
        for s in payload.suggestions:
            augmented_prompt_lines.append(f"- {s}")

    augmented_prompt = "\n".join(augmented_prompt_lines)

    repo_url = await _infer_repo_url_for_plan(original_plan_id)

    logger.info(
        "Auto-replanning for original plan %s -> new plan %s (severity=%s)",
        original_plan_id[:8],
        new_plan_id[:8],
        payload.severity,
    )
    await _execute_plan(
        augmented_prompt,
        project_name="default",
        repo_url=repo_url or "",
        forced_plan_id=new_plan_id,
        mode="normal",
    )
    _replans_per_original_plan[original_plan_id] = current_replans + 1


async def _fetch_original_plan_prompt(
    plan_id: str,
) -> tuple[str, str]:
    """
    Retrieve the original user prompt and planner reasoning for a plan.

    Uses memory_service /events filtered by event_type=plan.created and plan_id.
    """
    if http_client is None:
        return "", ""

    try:
        resp = await http_client.get(
            "/events",
            params={
                "event_type": "plan.created",
                "plan_id": plan_id,
                "limit": 1,
            },
        )
        if resp.status_code != 200:
            logger.warning(
                "Failed to fetch original plan.created for %s (status=%s)",
                plan_id[:8],
                resp.status_code,
            )
            return "", ""

        events = resp.json()
        if not isinstance(events, list) or not events:
            return "", ""

        evt = events[0]
        payload = evt.get("payload") or {}
        original_prompt = str(payload.get("original_prompt", "")).strip()
        reasoning = str(payload.get("reasoning", "")).strip()
        return original_prompt, reasoning
    except Exception:
        logger.exception(
            "Error while fetching original plan.created for %s",
            plan_id[:8],
        )
        return "", ""


async def _infer_repo_url_for_plan(plan_id: str) -> str:
    """
    Infer the repo_url for a given plan by asking memory_service for task state.

    This allows the replanned version to keep targeting the same repository.
    """
    if http_client is None:
        return ""

    try:
        resp = await http_client.get(f"/tasks/{plan_id}")
        if resp.status_code != 200:
            return ""
        tasks = resp.json()
        if not isinstance(tasks, list) or not tasks:
            return ""
        for t in tasks:
            repo_url = t.get("repo_url") or ""
            if isinstance(repo_url, str) and repo_url.strip():
                return repo_url.strip()
        return ""
    except Exception:
        logger.exception(
            "Error while inferring repo_url for plan %s",
            plan_id[:8],
        )
        return ""

async def _fetch_memory_context(user_prompt: str, limit: int = 3) -> str:
    """
    Retrieve a compact textual memory window for the planner based on
    the current user prompt.

    This uses the memory_service semantic search endpoint, which combines
    vector similarity with heuristic scoring (importance, recency, etc.).
    """
    global tool_registry
    if tool_registry is None:
        return ""

    try:
        result = await execute_tool(
            tool_registry,
            "semantic_search_memory",
            {
                "query": user_prompt,
                "plan_id": None,
                "event_types": [
                    EventType.PLAN_CREATED.value,
                    EventType.PIPELINE_CONCLUSION.value,
                    EventType.QA_FAILED.value,
                    EventType.SECURITY_BLOCKED.value,
                ],
                "limit": limit,
            },
        )
        semantic_results: list[dict] = []
        if result.success and isinstance(result.output, dict):
            raw_results = result.output.get("results") or []
            if isinstance(raw_results, list):
                semantic_results = raw_results
        elif not result.success:
            logger.warning("Semantic search tool failed: %s", result.error)

        events_list: list[dict] = []
        events_result = await execute_tool(
            tool_registry,
            "query_events",
            {"plan_id": None, "event_type": None, "limit": 10},
        )
        if events_result.success and isinstance(events_result.output, dict):
            raw_events = events_result.output.get("events") or []
            if isinstance(raw_events, list):
                events_list = raw_events

        summary = _summarise_planner_memory(
            semantic_results=semantic_results,
            events=events_list,
            max_lines=8,
        )

        patterns_summary = ""
        patterns_result = await execute_tool(
            tool_registry,
            "failure_patterns",
            {"module_prefix": None, "limit": 200},
        )
        if patterns_result.success and isinstance(patterns_result.output, dict):
            raw_patterns = patterns_result.output.get("patterns") or []
            lines: list[str] = []
            for p in raw_patterns[:4]:
                if not isinstance(p, dict):
                    continue
                module = str(p.get("module", ""))
                qa_n = int(p.get("qa_failed", 0) or 0)
                sec_n = int(p.get("security_blocked", 0) or 0)
                if qa_n == 0 and sec_n == 0:
                    continue
                pieces = []
                if qa_n:
                    pieces.append(f"QA_FAILED x{qa_n}")
                if sec_n:
                    pieces.append(f"SEC_BLOCKED x{sec_n}")
                lines.append(f"- {module}: " + ", ".join(pieces))
            if lines:
                patterns_summary = "Historical failure patterns by module:\n" + "\n".join(
                    lines
                )

        if patterns_summary:
            if summary.strip():
                return summary + "\n\n" + patterns_summary
            return patterns_summary
        return summary
    except Exception:
        logger.exception("Failed to fetch memory context from memory_service")
        return ""
