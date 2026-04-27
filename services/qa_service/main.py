"""QA Service -- code quality gate between dev_service and github_service."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastapi import FastAPI

from services.qa_service.config import QAConfig
from services.qa_service.handlers import QADeps, handle_code_review
from services.qa_service.tools import build_qa_tool_registry
from shared.contracts.events import CodeGeneratedPayload, EventType
from shared.http.client import create_async_http_client
from shared.logging.logger import setup_logging
from shared.middleware.correlation import install_correlation_middleware
from shared.observability.metrics import metrics_response
from shared.tools import ToolRegistry
from shared.utils import EventBus, maybe_agent_delay, subscribe_typed_event

SERVICE_NAME = "qa_service"
event_bus: EventBus = cast(EventBus, None)
http_client: httpx.AsyncClient = cast(httpx.AsyncClient, None)
cfg: QAConfig = cast(QAConfig, None)
tool_registry: ToolRegistry = cast(ToolRegistry, None)

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
    logger.info(
        "QA Service ready (max_qa_retries=%d, tool_loop=%s)",
        cfg.max_qa_retries,
        getattr(cfg, "enable_tool_loop", False),
    )
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
install_correlation_middleware(app)
logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

async def _consume_code_generated() -> None:
    async def on_payload(payload: CodeGeneratedPayload) -> None:
        await maybe_agent_delay(logger)
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

    await subscribe_typed_event(
        event_bus=event_bus,
        queue_name="qa_service.code_review",
        routing_keys=[EventType.CODE_GENERATED.value],
        payload_model=CodeGeneratedPayload,
        on_payload=on_payload,
        redis_url=cfg.redis_url,
        max_retries=3,
    )



