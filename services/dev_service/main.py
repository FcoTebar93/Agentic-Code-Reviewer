"""
Dev Service -- the AI developer agent.

Phase 2 change: dev_service no longer publishes pr.requested.
PR creation is now triggered by qa_service after all tasks pass review.
This service only generates code and publishes code.generated.
"""

from __future__ import annotations

import asyncio
import logging
import os
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
    TokensUsedPayload,
    code_generated,
    metrics_tokens_used,
)
from shared.llm_adapter import get_llm_provider
from shared.utils.rabbitmq import EventBus, IdempotencyStore
from services.dev_service.config import DevConfig
from services.dev_service.generator import generate_code
from services.dev_service.tools import build_dev_tool_registry, ReadFileInput
from shared.tools import execute_tool, ToolRegistry

SERVICE_NAME = "dev_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: DevConfig | None = None
tool_registry: ToolRegistry | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg, tool_registry
    logger = setup_logging(SERVICE_NAME)

    cfg = DevConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=30.0)

    tool_registry = build_dev_tool_registry()

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
        delay_sec = int(os.environ.get("AGENT_DELAY_SECONDS", "0"))
        if delay_sec > 0:
            logger.info("Agent delay: waiting %ds before processing", delay_sec)
            await asyncio.sleep(delay_sec)
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

    # Idempotencia: si ya existe un code.generated para este task_id (reintento tras fallo), no regenerar ni publicar de nuevo
    try:
        resp = await http_client.get(
            "/events",
            params={"plan_id": plan_id, "event_type": EventType.CODE_GENERATED.value, "limit": 100},
        )
        if resp.status_code == 200:
            events = resp.json() if isinstance(resp.json(), list) else []
            for ev in events:
                payload = ev.get("payload") or {}
                if payload.get("task_id") == task.task_id:
                    logger.info(
                        "Task %s already has code.generated, skipping (idempotent)",
                        task.task_id[:8],
                    )
                    return
    except Exception:
        pass

    logger.info(
        "Processing task %s for plan %s%s",
        task.task_id[:8],
        plan_id[:8],
        f" (QA feedback present)" if qa_feedback else "",
    )

    with agent_execution_time.labels(service=SERVICE_NAME, operation="code_gen").time():
        await _update_task_state(task.task_id, plan_id, "in_progress")

        llm = get_llm_provider()
        short_term_memory = await _build_short_term_memory(plan_id)
        existing_file_preview = await _maybe_read_existing_file(task.file_path)
        code_result, prompt_tokens, completion_tokens = await generate_code(
            llm,
            task,
            plan_reasoning=payload.plan_reasoning,
            short_term_memory="\n".join(
                [p for p in [short_term_memory, existing_file_preview] if p]
            ),
        )

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
            await _store_event(tok_event)

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
            qa_attempt=current_attempt,
            reasoning=code_result.reasoning,
        )
        step_delay = float(cfg.step_delay)
        if step_delay > 0:
            logger.info("Pausing %.1fs before publishing (AGENT_STEP_DELAY)", step_delay)
            await asyncio.sleep(step_delay)

        cg_event = code_generated(SERVICE_NAME, cg_payload)
        await event_bus.publish(cg_event)
        await _store_event(cg_event)

        await _update_task_state(
            task.task_id, plan_id, "completed",
            task.file_path, code_result.code, payload.repo_url,
        )
        tasks_completed.labels(service=SERVICE_NAME).inc()

    logger.info("Task %s code generated, forwarded to qa_service", task.task_id[:8])


async def _maybe_read_existing_file(file_path: str) -> str:
    """
    Best-effort helper: usa el tool read_file para recuperar un pequeño
    preview del archivo objetivo, si ya existe en el repo.
    """
    global tool_registry
    if not tool_registry:
        return ""
    if not file_path.strip():
        return ""
    try:
        result = await execute_tool(
            tool_registry,
            "read_file",
            {"path": file_path, "max_bytes": 4000},
        )
        if not result.success:
            return ""
        payload = result.output or {}
        if not payload.get("exists"):
            return ""
        content = str(payload.get("content", ""))[:4000]
        if not content.strip():
            return ""
        return f"Existing contents of {file_path}:\n{content}"
    except Exception:
        return ""

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


async def _build_short_term_memory(plan_id: str, limit: int = 30) -> str:
    """
    Build a compact short-term memory window for a given plan_id by querying
    recent events from the memory_service.
    """
    if http_client is None:
        return ""

    try:
        resp = await http_client.get(
            "/events",
            params={"plan_id": plan_id, "limit": limit},
        )
        if resp.status_code != 200:
            logger.warning(
                "Failed to fetch short-term memory for plan %s (status=%s)",
                plan_id[:8],
                resp.status_code,
            )
            return ""

        events = resp.json()
        if not isinstance(events, list):
            return ""

        lines: list[str] = []
        for evt in events:
            etype = evt.get("event_type", "")
            producer = evt.get("producer", "")
            created_at = evt.get("created_at", "")
            payload = evt.get("payload") or {}

            summary = ""
            if etype == EventType.PLAN_CREATED.value:
                summary = str(payload.get("reasoning", ""))[:200]
            elif etype == EventType.CODE_GENERATED.value:
                summary = f"{payload.get('file_path', '')}"
            elif etype in (
                EventType.QA_PASSED.value,
                EventType.QA_FAILED.value,
                EventType.SECURITY_APPROVED.value,
                EventType.SECURITY_BLOCKED.value,
            ):
                summary = str(payload.get("reasoning", ""))[:200]
            else:
                summary = ""

            line = f"[{etype}] from {producer} at {created_at}"
            if summary:
                line += f" :: {summary}"
            lines.append(line)

        window = "\n".join(lines[:limit])
        if len(window) > 2000:
            window = window[:2000]
        return window
    except Exception:
        logger.exception(
            "Error while building short-term memory for plan %s",
            plan_id[:8],
        )
        return ""


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
