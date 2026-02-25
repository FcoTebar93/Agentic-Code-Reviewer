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
from shared.observability.metrics import metrics_response, agent_execution_time, tasks_completed
from shared.contracts.events import (
    BaseEvent,
    EventType,
    PlanCreatedPayload,
    PlanRequestedPayload,
    TaskAssignedPayload,
    PlanRevisionPayload,
    plan_created,
    task_assigned,
)
from shared.llm_adapter import get_llm_provider
from shared.utils.rabbitmq import EventBus
from services.meta_planner.config import PlannerConfig
from services.meta_planner.planner import decompose_tasks

SERVICE_NAME = "meta_planner"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: PlannerConfig | None = None

_IDEM_TTL_SECONDS = int(os.environ.get("PLAN_IDEM_TTL_SECONDS", "30"))
_plan_idem_cache: dict[str, tuple[str, dict, float]] = {}

@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = PlannerConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=10.0)

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
        result = await _execute_plan(req.prompt, req.project_name, req.repo_url)
        _plan_idem_cache[key] = (result["plan_id"], result, now)
        return result
    except Exception as e:
        logger.exception("Plan execution failed")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Plan execution failed",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )

async def _execute_plan(
    prompt: str,
    project_name: str,
    repo_url: str,
    forced_plan_id: str | None = None,
) -> dict:
    with agent_execution_time.labels(service=SERVICE_NAME, operation="plan").time():
        llm = get_llm_provider()
        memory_context = await _fetch_memory_context(prompt)
        plan_result = await decompose_tasks(llm, prompt, memory_context=memory_context)
        task_specs = plan_result.tasks

        plan_payload = PlanCreatedPayload(
            plan_id=forced_plan_id or PlanCreatedPayload.model_fields["plan_id"].default_factory(),  # type: ignore
            original_prompt=prompt,
            tasks=task_specs,
            reasoning=plan_result.reasoning,
        )
        plan_event = plan_created(SERVICE_NAME, plan_payload)
        plan_id = plan_payload.plan_id

        await event_bus.publish(plan_event)
        await _store_event(plan_event)

        for spec in task_specs:
            ta_payload = TaskAssignedPayload(
                plan_id=plan_id,
                task=spec,
                repo_url=repo_url,
                plan_reasoning=plan_result.reasoning,
            )
            ta_event = task_assigned(SERVICE_NAME, ta_payload)
            await event_bus.publish(ta_event)
            await _store_event(ta_event)

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
    """Listen for plan.requested events from the bus."""

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
        )

    await event_bus.subscribe(
        queue_name="meta_planner.plan_requests",
        routing_keys=[EventType.PLAN_REQUESTED.value],
        handler=handler,
    )


async def _consume_plan_revisions() -> None:
    """
    Listen for plan.revision_suggested events produced by replanner_service.

    For now, we auto-trigger a new planning run only when severity is
    'high' or 'critical'. The new plan is created with the new_plan_id
    suggested by the replanner, and uses an augmented prompt that combines
    the original user request with the replanner's suggestions.
    """

    async def handler(event: BaseEvent) -> None:
        payload = PlanRevisionPayload.model_validate(event.payload)
        severity = (payload.severity or "medium").lower()
        if severity not in {"high", "critical"}:
            logger.info(
                "Ignoring plan.revision_suggested for %s with non-critical severity %s",
                payload.original_plan_id[:8],
                severity,
            )
            return
        await _handle_plan_revision(payload)

    await event_bus.subscribe(
        queue_name="meta_planner.plan_revisions",
        routing_keys=[EventType.PLAN_REVISION_SUGGESTED.value],
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
    )


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

async def _store_event(event: BaseEvent) -> None:
    """Persist event to memory_service via HTTP."""
    try:
        await http_client.post(
            "/events",
            json={
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "producer": event.producer,
                "idempotency_key": event.idempotency_key,
                "payload": event.payload,
            },
        )
    except Exception:
        logger.exception("Failed to store event %s in memory_service", event.event_id[:8])


async def _fetch_memory_context(user_prompt: str, limit: int = 5) -> str:
    """
    Retrieve a compact textual memory window for the planner based on
    the current user prompt.

    This uses the memory_service semantic search endpoint, which combines
    vector similarity with heuristic scoring (importance, recency, etc.).
    """
    if http_client is None:
        return ""

    try:
        resp = await http_client.post(
            "/semantic/search",
            json={
                "query": user_prompt,
                "limit": limit,
                # We intentionally do not filter by plan_id here so that the
                # planner can leverage memories from previous runs.
                "event_types": [
                    EventType.PLAN_CREATED.value,
                    EventType.PIPELINE_CONCLUSION.value,
                    EventType.QA_FAILED.value,
                    EventType.SECURITY_BLOCKED.value,
                ],
            },
        )
        if resp.status_code != 200:
            logger.warning(
                "Semantic search failed with status %s", resp.status_code
            )
            return ""

        data = resp.json()
        results = data.get("results") or []
        if not isinstance(results, list) or not results:
            return ""

        lines: list[str] = []
        for item in results[:limit]:
            payload = item.get("payload") or {}
            score = item.get("heuristic_score", item.get("score", 0.0))
            text = str(payload.get("text", ""))[:400].replace("\n", " ")
            etype = payload.get("event_type", "")
            plan_id = payload.get("plan_id", "")
            lines.append(
                f"- [{etype}] plan_id={plan_id} score={score:.3f}: {text}"
            )

        return "\n".join(lines)
    except Exception:
        logger.exception("Failed to fetch memory context from memory_service")
        return ""
