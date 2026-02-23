"""
Dev Service -- the AI developer agent.

Phase 2 change: dev_service no longer publishes pr.requested.
PR creation is now triggered by qa_service after all tasks pass review.
This service only generates code and publishes code.generated.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response, agent_execution_time, tasks_completed, llm_tokens
from shared.contracts.events import (
    BaseEvent,
    EventType,
    TaskAssignedPayload,
    CodeGeneratedPayload,
    code_generated,
)
from shared.llm_adapter import get_llm_provider
from shared.utils.rabbitmq import EventBus, IdempotencyStore
from services.dev_service.config import DevConfig
from services.dev_service.generator import generate_code

SERVICE_NAME = "dev_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: DevConfig | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = DevConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=30.0)

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_tasks())
    logger.info("Dev Service ready")
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Dev Service",
    version="0.2.0",
    description="Generates code via LLM based on task specifications",
    lifespan=lifespan,
)
logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

async def _consume_tasks() -> None:
    idem_store = IdempotencyStore(
        redis_url=cfg.redis_url if hasattr(cfg, "redis_url") else None
    )

    async def handler(event: BaseEvent) -> None:
        payload = TaskAssignedPayload.model_validate(event.payload)
        await _handle_task(payload)

    await event_bus.subscribe(
        queue_name="dev_service.tasks",
        routing_keys=[EventType.TASK_ASSIGNED.value],
        handler=handler,
        idempotency_store=idem_store,
        max_retries=3,
    )


async def _handle_task(payload: TaskAssignedPayload) -> None:
    task = payload.task
    plan_id = payload.plan_id
    qa_feedback = payload.qa_feedback

    logger.info(
        "Processing task %s for plan %s%s",
        task.task_id[:8],
        plan_id[:8],
        f" (QA feedback present)" if qa_feedback else "",
    )

    with agent_execution_time.labels(service=SERVICE_NAME, operation="code_gen").time():
        await _update_task_state(task.task_id, plan_id, "in_progress")

        llm = get_llm_provider()
        code_result = await generate_code(llm, task)

        current_attempt = 0
        try:
            resp = await http_client.get(f"/tasks/{plan_id}")
            if resp.status_code == 200:
                tasks = resp.json()
                for t in tasks:
                    if t["task_id"] == task.task_id:
                        current_attempt = t.get("qa_attempt", 0)
                        break
        except Exception:
            pass

        cg_payload = CodeGeneratedPayload(
            plan_id=plan_id,
            task_id=task.task_id,
            file_path=task.file_path,
            code=code_result.code,
            language=task.language,
            qa_attempt=current_attempt + (1 if qa_feedback else 0),
            reasoning=code_result.reasoning,
        )
        cg_event = code_generated(SERVICE_NAME, cg_payload)
        await event_bus.publish(cg_event)
        await _store_event(cg_event)

        await _update_task_state(
            task.task_id, plan_id, "completed",
            task.file_path, code_result.code, payload.repo_url,
        )
        tasks_completed.labels(service=SERVICE_NAME).inc()

    logger.info("Task %s code generated, forwarded to qa_service", task.task_id[:8])

async def _store_event(event: BaseEvent) -> None:
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
        logger.exception("Failed to store event %s", event.event_id[:8])


async def _update_task_state(
    task_id: str, plan_id: str, status: str,
    file_path: str = "", code: str = "", repo_url: str = "",
) -> None:
    try:
        await http_client.post(
            "/tasks",
            json={
                "task_id": task_id,
                "plan_id": plan_id,
                "status": status,
                "file_path": file_path,
                "code": code,
                "repo_url": repo_url,
            },
        )
    except Exception:
        logger.exception("Failed to update task state %s", task_id[:8])
