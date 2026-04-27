"""Meta Planner: plan creation, semantic Q&A, and replanning orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.meta_planner.ask_agent import run_ask_agent
from services.meta_planner.config import PlannerConfig
from services.meta_planner.deps import MetaPlannerDeps
from services.meta_planner.planner import (
    decompose_tasks,
    decompose_tasks_with_tool_loop,
)
from services.meta_planner.tools import build_planner_tool_registry
from shared.contracts.events import (
    EventType,
    PlanCreatedPayload,
    PlanRequestedPayload,
    PlanRevisionPayload,
    TaskAssignedPayload,
    plan_created,
    task_assigned,
)
from shared.http.client import create_async_http_client
from shared.llm_adapter import get_llm_provider
from shared.logging.logger import setup_logging
from shared.middleware.correlation import install_correlation_middleware
from shared.observability.metrics import (
    agent_execution_time,
    llm_tokens,
    tasks_completed,
)
from shared.observability.routing import register_health_metrics_routes
from shared.observability.tokens import emit_token_usage_event
from shared.plan_idempotency import plan_idempotency_key_meta_planner
from shared.tools import ToolRegistry, execute_tool
from shared.utils.path_grouping import infer_group_id
from shared.utils import (
    EventBus,
    guarded_http_get,
    maybe_agent_delay,
    store_event,
    subscribe_typed_event,
)
from shared.utils.lifecycle import connect_event_bus, shutdown_runtime

SERVICE_NAME = "meta_planner"
event_bus: EventBus = cast(EventBus, None)
http_client: httpx.AsyncClient = cast(httpx.AsyncClient, None)
cfg: PlannerConfig = cast(PlannerConfig, None)
tool_registry: ToolRegistry = cast(ToolRegistry, None)

_IDEM_TTL_SECONDS = int(os.environ.get("PLAN_IDEM_TTL_SECONDS", "30"))
_plan_idem_cache: dict[str, tuple[str, dict, float]] = {}
_MAX_AUTO_REPLANS_PER_ORIGINAL_PLAN = int(
    os.environ.get("MAX_AUTO_REPLANS_PER_ORIGINAL_PLAN", "1")
)
_replans_per_original_plan: dict[str, int] = {}


def _summarise_planner_memory(
    semantic_results: list[dict] | None,
    events: list[dict] | None,
    max_lines: int = 8,
) -> str:
    """Build compact planner memory summary from semantic results and events."""
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
    http_client = create_async_http_client(
        base_url=cfg.memory_service_url,
        default_timeout=10.0,
    )

    tool_registry = build_planner_tool_registry(memory_service_url=cfg.memory_service_url)

    event_bus = await connect_event_bus(cfg.rabbitmq_url)

    application.state.meta_planner_deps = MetaPlannerDeps(
        http_client=http_client,
        cfg=cfg,
        event_bus=event_bus,
        tool_registry=tool_registry,
    )

    asyncio.create_task(_consume_plan_requests())
    asyncio.create_task(_consume_plan_revisions())
    logger.info("Meta Planner ready (with replanning support)")
    yield

    await shutdown_runtime(logger=logger, event_bus=event_bus, http_client=http_client)


app = FastAPI(
    title="ADMADC - Meta Planner",
    version="0.1.0",
    description="Orchestrates task decomposition and agent coordination",
    lifespan=lifespan,
)
install_correlation_middleware(app)
logger = logging.getLogger(SERVICE_NAME)
register_health_metrics_routes(app, SERVICE_NAME)

class PlanRequest(BaseModel):
    prompt: str
    project_name: str = "default"
    repo_url: str = ""
    mode: str = "normal"
    user_locale: str = "en"


class PlanResponse(BaseModel):
    plan_id: str
    task_count: int
    tasks: list[dict]


class AskRequest(BaseModel):
    question: str
    plan_id: str | None = None
    user_locale: str = "en"


class AskResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


@app.post("/plan", response_model=PlanResponse)
async def create_plan(req: PlanRequest):
    key = plan_idempotency_key_meta_planner(req.model_dump())
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
            user_locale=getattr(req, "user_locale", None) or "en",
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


@app.post("/ask", response_model=AskResponse)
async def agent_ask(req: AskRequest):
    """Answer questions using semantic memory and optional plan-scoped events."""
    global http_client, cfg
    if http_client is None or cfg is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Service not ready"},
        )
    q = (req.question or "").strip()
    if not q:
        return JSONResponse(
            status_code=400,
            content={"detail": "question must be non-empty"},
        )
    try:
        llm = get_llm_provider(provider_name=cfg.llm_provider)
        answer, sources, pt, ct = await run_ask_agent(
            llm,
            memory_client=http_client,
            question=q,
            plan_id=(req.plan_id or "").strip() or None,
            user_locale=getattr(req, "user_locale", None) or "en",
        )
        if pt or ct:
            llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
            llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)
        return AskResponse(
            answer=answer,
            sources=sources,
            prompt_tokens=pt,
            completion_tokens=ct,
        )
    except Exception as e:
        logger.exception("agent ask failed")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Agent ask failed",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )


async def _execute_plan(
    prompt: str,
    project_name: str,
    repo_url: str,
    forced_plan_id: str | None = None,
    mode: str = "normal",
    user_locale: str = "en",
) -> dict:
    with agent_execution_time.labels(service=SERVICE_NAME, operation="plan").time():
        llm = get_llm_provider(provider_name=cfg.llm_provider)
        memory_context = await _fetch_memory_context(prompt)
        if cfg.enable_tool_loop and tool_registry is not None:
            plan_result, prompt_tokens, completion_tokens = (
                await decompose_tasks_with_tool_loop(
                    llm,
                    tool_registry,
                    prompt,
                    memory_seed=memory_context,
                    max_steps=cfg.tool_loop_max_steps,
                    plan_id=None,
                    redis_url=cfg.redis_url,
                    user_locale=user_locale,
                )
            )
        else:
            plan_result, prompt_tokens, completion_tokens = await decompose_tasks(
                llm, prompt, memory_context=memory_context, user_locale=user_locale
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
                    spec.group_id = infer_group_id(spec.file_path)
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
            plan_id=forced_plan_id or str(uuid4()),
            original_prompt=prompt,
            tasks=task_specs,
            reasoning=plan_result.reasoning,
            mode=mode or "normal",
            user_locale=user_locale,
        )
        plan_event = plan_created(SERVICE_NAME, plan_payload)
        plan_id = plan_payload.plan_id

        await emit_token_usage_event(
            service_name=SERVICE_NAME,
            plan_id=plan_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            http_client=http_client,
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
                user_locale=user_locale,
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
    """Consume `plan.requested` and execute plans with delay support."""
    async def on_payload(payload: PlanRequestedPayload) -> None:
        await maybe_agent_delay(logger)
        await _execute_plan(
            payload.user_prompt,
            payload.project_name,
            payload.repo_url,
            mode=getattr(payload, "mode", "normal") or "normal",
            user_locale=getattr(payload, "user_locale", None) or "en",
        )

    await subscribe_typed_event(
        event_bus=event_bus,
        queue_name="meta_planner.plan_requests",
        routing_keys=[EventType.PLAN_REQUESTED.value],
        payload_model=PlanRequestedPayload,
        on_payload=on_payload,
        max_retries=3,
    )


async def _consume_plan_revisions() -> None:
    """Consume replanning events and trigger confirmed plan revisions."""
    async def on_suggested(payload: PlanRevisionPayload) -> None:
        logger.info(
            "Received plan.revision_suggested for %s (severity=%s) - waiting for human confirmation.",
            payload.original_plan_id[:8],
            (payload.severity or "medium"),
        )

    async def on_confirmed(payload: PlanRevisionPayload) -> None:
        await _handle_plan_revision(payload)

    await subscribe_typed_event(
        event_bus=event_bus,
        queue_name="meta_planner.plan_revisions.suggested",
        routing_keys=[EventType.PLAN_REVISION_SUGGESTED.value],
        payload_model=PlanRevisionPayload,
        on_payload=on_suggested,
        max_retries=3,
    )
    await subscribe_typed_event(
        event_bus=event_bus,
        queue_name="meta_planner.plan_revisions.confirmed",
        routing_keys=[EventType.PLAN_REVISION_CONFIRMED.value],
        payload_model=PlanRevisionPayload,
        on_payload=on_confirmed,
        max_retries=3,
    )


async def _handle_plan_revision(payload: PlanRevisionPayload) -> None:
    """Replan automatically from a confirmed `PlanRevisionPayload`."""
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

    original_prompt, original_reasoning, revision_locale = (
        await _fetch_original_plan_prompt(original_plan_id)
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
        user_locale=revision_locale or "en",
    )
    _replans_per_original_plan[original_plan_id] = current_replans + 1


async def _fetch_original_plan_prompt(
    plan_id: str,
) -> tuple[str, str, str]:
    """Get original prompt, planner reasoning, and user_locale for a plan."""
    if http_client is None:
        return "", "", "en"

    resp = await guarded_http_get(
        http_client,
        "/events",
        logger,
        key="memory_service:/events",
        params={
            "event_type": "plan.created",
            "plan_id": plan_id,
            "limit": 1,
        },
    )
    if resp is None:
        return "", "", "en"
    if resp.status_code != 200:
        logger.warning(
            "Failed to fetch original plan.created for %s (status=%s)",
            plan_id[:8],
            resp.status_code,
        )
        return "", "", "en"
    try:
        events = resp.json()
        if not isinstance(events, list) or not events:
            return "", "", "en"

        evt = events[0]
        payload = evt.get("payload") or {}
        original_prompt = str(payload.get("original_prompt", "")).strip()
        reasoning = str(payload.get("reasoning", "")).strip()
        user_locale = str(payload.get("user_locale", "") or "en").strip() or "en"
        return original_prompt, reasoning, user_locale
    except Exception:
        logger.exception("Error while parsing original plan.created for %s", plan_id[:8])
        return "", "", "en"


async def _infer_repo_url_for_plan(plan_id: str) -> str:
    """Infer repo URL from stored task state for a plan."""
    if http_client is None:
        return ""

    resp = await guarded_http_get(
        http_client,
        f"/tasks/{plan_id}",
        logger,
        key="memory_service:/tasks",
    )
    if resp is None or resp.status_code != 200:
        return ""
    try:
        tasks = resp.json()
        if not isinstance(tasks, list) or not tasks:
            return ""
        for t in tasks:
            repo_url = t.get("repo_url") or ""
            if isinstance(repo_url, str) and repo_url.strip():
                return repo_url.strip()
        return ""
    except Exception:
        logger.exception("Error while parsing tasks for plan %s", plan_id[:8])
        return ""

async def _fetch_memory_context(user_prompt: str, limit: int = 3) -> str:
    """Build compact planner memory context from semantic and pattern tools."""
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
