"""
Security Service -- last gate before code reaches GitHub.

Pipeline role:
  qa_service -> [pr.requested] -> security_service -> [security.approved] -> github_service
                                                    -> [security.blocked]  -> (pipeline stopped)

On approval: re-publishes the original pr.requested payload enriched with
             security_approved=True as a security.approved event.
On block: publishes security.blocked and stores the result in memory_service.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response, agent_execution_time, tasks_completed
from shared.contracts.events import (
    BaseEvent,
    EventType,
    PRRequestedPayload,
    SecurityResultPayload,
    CodeGeneratedPayload,
    security_approved,
    security_blocked,
)
from shared.utils.rabbitmq import EventBus, IdempotencyStore
from services.security_service.config import SecurityConfig
from services.security_service.scanner import scan_files

SERVICE_NAME = "security_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: SecurityConfig | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = SecurityConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=30.0)

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_pr_requests())
    logger.info("Security Service ready")
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Security Service",
    version="0.1.0",
    description="Security gate: scans aggregated PR code before GitHub publication",
    lifespan=lifespan,
)
logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

async def _consume_pr_requests() -> None:
    idem_store = IdempotencyStore(redis_url=cfg.redis_url)

    async def handler(event: BaseEvent) -> None:
        payload = PRRequestedPayload.model_validate(event.payload)
        await _handle_security_scan(payload)

    await event_bus.subscribe(
        queue_name="security_service.pr_requests",
        routing_keys=[EventType.PR_REQUESTED.value],
        handler=handler,
        idempotency_store=idem_store,
        max_retries=3,
    )


async def _handle_security_scan(payload: PRRequestedPayload) -> None:
    plan_id = payload.plan_id
    logger.info(
        "Security scan for plan %s (%d files)", plan_id[:8], len(payload.files)
    )

    with agent_execution_time.labels(service=SERVICE_NAME, operation="security_scan").time():
        files_data = [f.model_dump() for f in payload.files]
        result = scan_files(files_data)

    sec_payload = SecurityResultPayload(
        plan_id=plan_id,
        branch_name=payload.branch_name,
        approved=result.approved,
        violations=result.violations,
        files_scanned=result.files_scanned,
        pr_context=payload.model_dump() if result.approved else {},
    )

    if result.approved:
        logger.info("Security APPROVED for plan %s", plan_id[:8])
        tasks_completed.labels(service=SERVICE_NAME).inc()

        approved_event = security_approved(SERVICE_NAME, sec_payload)
        await event_bus.publish(approved_event)
        await _store_event(approved_event)
    else:
        logger.error(
            "Security BLOCKED for plan %s: %s", plan_id[:8], result.violations
        )
        blocked_event = security_blocked(SERVICE_NAME, sec_payload)
        await event_bus.publish(blocked_event)
        await _store_event(blocked_event)

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
