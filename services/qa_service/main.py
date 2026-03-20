"""
QA Service -- code quality gate between dev_service and github_service.

Pipeline role:
  dev_service -> [code.generated] -> qa_service -> [pr.requested] -> security_service

On QA pass: aggregates all tasks for the plan and publishes pr.requested.
On QA fail (retries remaining): re-enqueues task.assigned with feedback for dev_service.
On QA fail (retries exhausted): publishes qa.failed and logs to memory_service.

Inter-agent reasoning:
  - Each code.generated event carries the developer's reasoning.
  - The QA reviewer receives this reasoning and explicitly responds to it.
  - Dev + QA reasoning are cached per task and forwarded to security_service
    so the final security scan can reference the full reasoning chain.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from shared.http.client import create_async_http_client
from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response
from shared.contracts.events import BaseEvent, EventType, CodeGeneratedPayload
from shared.utils import EventBus, IdempotencyStore
from shared.tools import ToolRegistry
from services.qa_service.config import QAConfig
from services.qa_service.tools import build_qa_tool_registry
from services.qa_service.handlers import QADeps, handle_code_review

SERVICE_NAME = "qa_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: QAConfig | None = None
tool_registry: ToolRegistry | None = None

_dev_reasoning_cache: dict[str, str] = {}
_qa_reasoning_cache: dict[str, str] = {}
_pr_requested_plan_ids: set[str] = set()

@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg, tool_registry
    logger = setup_logging(SERVICE_NAME)

    cfg = QAConfig.from_env()
    http_client = create_async_http_client(
        base_url=cfg.memory_service_url,
        default_timeout=30.0,
    )

    tool_registry = build_qa_tool_registry()

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_code_generated())
    logger.info("QA Service ready (max_qa_retries=%d)", cfg.max_qa_retries)
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - QA Service",
    version="0.1.0",
    description="Quality gate: reviews generated code before PR creation",
    lifespan=lifespan,
)
logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

async def _consume_code_generated() -> None:
    idem_store = IdempotencyStore(redis_url=cfg.redis_url)

    async def handler(event: BaseEvent) -> None:
        delay_sec = int(os.environ.get("AGENT_DELAY_SECONDS", "0"))
        if delay_sec > 0:
            logger.info("Agent delay: waiting %ds before processing", delay_sec)
            await asyncio.sleep(delay_sec)
        payload = CodeGeneratedPayload.model_validate(event.payload)
        deps = QADeps(
            logger=logger,
            cfg=cfg,
            http_client=http_client,
            event_bus=event_bus,
            tool_registry=tool_registry,
            dev_reasoning_cache=_dev_reasoning_cache,
            qa_reasoning_cache=_qa_reasoning_cache,
            pr_requested_plan_ids=_pr_requested_plan_ids,
        )
        await handle_code_review(payload, deps)

    await event_bus.subscribe(
        queue_name="qa_service.code_review",
        routing_keys=[EventType.CODE_GENERATED.value],
        handler=handler,
        idempotency_store=idem_store,
        max_retries=3,
    )



