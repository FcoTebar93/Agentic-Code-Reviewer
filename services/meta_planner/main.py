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
    logger.info("Meta Planner ready")
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
    prompt: str, project_name: str, repo_url: str
) -> dict:
    with agent_execution_time.labels(service=SERVICE_NAME, operation="plan").time():
        llm = get_llm_provider()
        plan_result = await decompose_tasks(llm, prompt)
        task_specs = plan_result.tasks

        plan_payload = PlanCreatedPayload(
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
        await _execute_plan(payload.user_prompt, payload.project_name, payload.repo_url)

    await event_bus.subscribe(
        queue_name="meta_planner.plan_requests",
        routing_keys=[EventType.PLAN_REQUESTED.value],
        handler=handler,
    )

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
