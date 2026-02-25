from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response, agent_execution_time, llm_tokens
from shared.contracts.events import (
    BaseEvent,
    EventType,
    QAResultPayload,
    SecurityResultPayload,
    PlanRevisionPayload,
    TokensUsedPayload,
    plan_revision_suggested,
    metrics_tokens_used,
)
from shared.llm_adapter import get_llm_provider
from shared.utils.rabbitmq import EventBus, IdempotencyStore
from services.replanner_service.config import ReplannerConfig
from services.replanner_service.critic import analyse_outcome

SERVICE_NAME = "replanner_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: ReplannerConfig | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = ReplannerConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=30.0)

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_outcomes())
    logger.info("Replanner Service ready (strategy=%s)", cfg.strategy)
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Replanner Service",
    version="0.1.0",
    description="Critic agent that suggests plan revisions after QA/Security outcomes",
    lifespan=lifespan,
)
logger = logging.getLogger(SERVICE_NAME)


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()


async def _consume_outcomes() -> None:
    """
    Listen for QA_FAILED and SECURITY_BLOCKED events.

    The replanner acts as a read-only critic for now: it emits plan.revision_suggested
    events with structured suggestions, but does not modify the pipeline behaviour
    directly. Other agents (or humans) can choose how to react.
    """
    idem_store = IdempotencyStore()

    async def handler(event: BaseEvent) -> None:
        if event.event_type == EventType.QA_FAILED:
            payload = QAResultPayload.model_validate(event.payload)
            await _handle_qa_failed(payload)
        elif event.event_type == EventType.SECURITY_BLOCKED:
            payload = SecurityResultPayload.model_validate(event.payload)
            await _handle_security_blocked(payload)

    await event_bus.subscribe(
        queue_name="replanner_service.outcomes",
        routing_keys=[
            EventType.QA_FAILED.value,
            EventType.SECURITY_BLOCKED.value,
        ],
        handler=handler,
        idempotency_store=idem_store,
        max_retries=3,
    )


async def _handle_qa_failed(payload: QAResultPayload) -> None:
    await _analyse_and_emit_revision(
        plan_id=payload.plan_id,
        outcome=payload,
        outcome_type="qa_failed",
    )


async def _handle_security_blocked(payload: SecurityResultPayload) -> None:
    await _analyse_and_emit_revision(
        plan_id=payload.plan_id,
        outcome=payload,
        outcome_type="security_blocked",
    )


async def _analyse_and_emit_revision(
    plan_id: str,
    outcome: Any,
    outcome_type: str,
) -> None:
    """
    Run the replanner LLM on a failing outcome and, if it decides that a
    revision is needed, emit a plan.revision_suggested event.
    """
    if cfg is None:
        return

    with agent_execution_time.labels(
        service=SERVICE_NAME, operation=f"replan_{outcome_type}"
    ).time():
        llm = get_llm_provider()
        memory_context = await _fetch_memory_context(plan_id)

        result, prompt_tokens, completion_tokens = await analyse_outcome(
            llm=llm,
            agent_goal=cfg.agent_goal,
            plan_id=plan_id,
            outcome=outcome,
            memory_context=memory_context,
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

    if not result.revision_needed:
        logger.info(
            "Replanner decided no revision needed for plan %s (severity=%s)",
            plan_id[:8],
            result.severity,
        )
        return

    revision_payload = PlanRevisionPayload(
        original_plan_id=plan_id,
        reason=result.reason,
        summary=(
            f"Replanner suggests revising plan {plan_id[:8]} after {outcome_type}."
        ),
        suggestions=result.suggestions,
        severity=result.severity,
    )
    event = plan_revision_suggested(SERVICE_NAME, revision_payload)
    await event_bus.publish(event)
    await _store_event(event)

    logger.info(
        "Emitted plan.revision_suggested for original plan %s (new_plan_id=%s, severity=%s)",
        plan_id[:8],
        revision_payload.new_plan_id[:8],
        revision_payload.severity,
    )


async def _fetch_memory_context(plan_id: str, limit: int = 5) -> str:
    """
    Retrieve semantic memory focused on this plan id to provide context
    to the replanner (previous conclusions, QA failures, security blocks).
    """
    if http_client is None:
        return ""

    try:
        resp = await http_client.post(
            "/semantic/search",
            json={
                "query": f"Outcome summary and reasoning for plan {plan_id}",
                "plan_id": plan_id,
                "event_types": [
                    EventType.PIPELINE_CONCLUSION.value,
                    EventType.QA_FAILED.value,
                    EventType.SECURITY_BLOCKED.value,
                ],
                "limit": limit,
            },
        )
        if resp.status_code != 200:
            logger.warning(
                "Replanner semantic search failed for plan %s (status=%s)",
                plan_id[:8],
                resp.status_code,
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
            lines.append(f"- [{etype}] score={score:.3f}: {text}")

        return "\n".join(lines)
    except Exception:
        logger.exception(
            "Failed to fetch memory context for replanner (plan %s)",
            plan_id[:8],
        )
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
        logger.exception("Failed to store replanner event %s", event.event_id[:8])

