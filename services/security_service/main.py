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
import os
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastapi import FastAPI

from services.qa_service.tools import REPO_ROOT
from services.security_service.config import SecurityConfig
from services.security_service.prompts import SECURITY_REVIEW_PROMPT
from services.security_service.scanner import scan_files
from shared.contracts.events import (
    BaseEvent,
    EventType,
    PRRequestedPayload,
    SecurityResultPayload,
    security_approved,
    security_blocked,
)
from shared.http.client import create_async_http_client
from shared.llm_adapter import LLMResponse, get_llm_provider
from shared.logging.logger import setup_logging
from shared.middleware.correlation import install_correlation_middleware
from shared.observability.metrics import (
    agent_execution_time,
    llm_tokens,
    metrics_response,
    tasks_completed,
)
from shared.policies import effective_mode, load_project_policy, policy_for_path
from shared.prompt_locale import (
    security_memory_context_prefix,
)
from shared.utils import (
    EventBus,
    maybe_agent_delay,
    store_event,
    subscribe_typed_event,
)

SERVICE_NAME = "security_service"
event_bus: EventBus = cast(EventBus, None)
http_client: httpx.AsyncClient = cast(httpx.AsyncClient, None)
cfg: SecurityConfig = cast(SecurityConfig, None)


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = SecurityConfig.from_env()
    http_client = create_async_http_client(
        base_url=cfg.memory_service_url,
        default_timeout=30.0,
    )

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
install_correlation_middleware(app)
logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

async def _consume_pr_requests() -> None:
    async def on_payload(payload: PRRequestedPayload) -> None:
        await maybe_agent_delay(logger)
        await _handle_security_scan(payload)

    await subscribe_typed_event(
        event_bus=event_bus,
        queue_name="security_service.pr_requests",
        routing_keys=[EventType.PR_REQUESTED.value],
        payload_model=PRRequestedPayload,
        on_payload=on_payload,
        redis_url=cfg.redis_url,
        max_retries=3,
    )


async def _handle_security_scan(payload: PRRequestedPayload) -> None:
    plan_id = payload.plan_id
    user_locale = getattr(payload, "user_locale", None) or "en"
    raw_mode = getattr(payload, "mode", "normal") or "normal"

    try:
        project_policy = load_project_policy(REPO_ROOT)
    except Exception:
        project_policy = {"default_mode": "normal", "paths": {}}
    representative_path = payload.files[0].file_path if payload.files else ""
    path_policy = policy_for_path(project_policy, representative_path or "")
    default_mode = project_policy.get("default_mode", "normal")
    mode = effective_mode(raw_mode, path_policy, default_mode)
    logger.info(
        "Security scan for plan %s (%d files, mode=%s)",
        plan_id[:8],
        len(payload.files),
        mode,
    )

    with agent_execution_time.labels(
        service=SERVICE_NAME, operation="security_scan"
    ).time():
        files_data = [f.model_dump() for f in payload.files]
        result = scan_files(files_data, cfg)

    severity_hint = "low"
    if not result.approved and result.violations:
        severity_hint = "high"

    reasoning = result.reasoning or ""
    memory_ctx = ""
    if not result.approved and (mode == "strict" or path_policy.get("security_strict")):
        memory_ctx = await _fetch_security_memory_context(plan_id)
        if memory_ctx:
            reasoning = (reasoning + "\n\n" if reasoning else "") + (
                security_memory_context_prefix(user_locale) + memory_ctx
            )

        try:
            llm = get_llm_provider(
                provider_name=os.environ.get(
                    "SECURITY_LLM_PROVIDER",
                    os.environ.get("LLM_PROVIDER", "mock"),
                ),
                redis_url=cfg.redis_url,
            )
            violations_block = (
                "\n".join(f"- {v}" for v in (result.violations or []))
                if result.violations
                else "none"
            )
            prompt = SECURITY_REVIEW_PROMPT.format(
                plan_id=plan_id,
                branch_name=payload.branch_name,
                approved=result.approved,
                scanner_reasoning=result.reasoning or "None.",
                violations_block=violations_block,
                memory_context=memory_ctx or "None.",
            )
            llm_resp: LLMResponse = await llm.generate_text(prompt)
            pt = llm_resp.prompt_tokens or 0
            ct = llm_resp.completion_tokens or 0
            if pt or ct:
                llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
                llm_tokens.labels(
                    service=SERVICE_NAME, direction="completion"
                ).inc(ct)
            summary = (llm_resp.content or "").strip()
            if summary:
                reasoning = (
                    reasoning + "\n\n[Security reviewer LLM]\n" + summary
                    if reasoning
                    else "[Security reviewer LLM]\n" + summary
                )
        except Exception:
            logger.exception(
                "Lightweight security reviewer LLM failed; continuing with scanner output only"
            )

    sec_payload = SecurityResultPayload(
        plan_id=plan_id,
        branch_name=payload.branch_name,
        approved=result.approved,
        violations=result.violations,
        files_scanned=result.files_scanned,
        pr_context=payload.model_dump(),
        reasoning=reasoning,
        severity_hint=severity_hint,
        user_locale=user_locale,
    )

    if result.approved:
        logger.info("Security APPROVED for plan %s", plan_id[:8])
        tasks_completed.labels(service=SERVICE_NAME).inc()

        approved_event = security_approved(SERVICE_NAME, sec_payload)
        await event_bus.publish(approved_event)
        await store_event(
            http_client,
            approved_event,
            logger=logger,
            error_message="Failed to store event %s",
        )
    else:
        logger.error(
            "Security BLOCKED for plan %s: %s", plan_id[:8], result.violations
        )
        blocked_event = security_blocked(SERVICE_NAME, sec_payload)
        await event_bus.publish(blocked_event)
        await store_event(
            http_client,
            blocked_event,
            logger=logger,
            error_message="Failed to store event %s",
        )


async def _fetch_security_memory_context(plan_id: str, limit: int = 5) -> str:
    """
    Retrieve a small set of past security-related memories for this plan
    (or globally if plan-specific events are not present), to be attached
    later to pipeline conclusions or external dashboards.

    Note: the core scanner is intentionally deterministic and does not use
    the LLM; this context is mainly for observability and potential future
    human review.
    """
    if http_client is None:
        return ""

    try:
        resp = await http_client.post(
            "/semantic/search",
            json={
                "query": f"Security findings for plan {plan_id}",
                "plan_id": plan_id,
                "event_types": [
                    EventType.SECURITY_BLOCKED.value,
                    EventType.SECURITY_APPROVED.value,
                ],
                "limit": limit,
            },
        )
        if resp.status_code != 200:
            logger.warning(
                "Semantic search for security context failed (status=%s)",
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
            mem_plan_id = payload.get("plan_id", "")
            lines.append(
                f"- [{etype}] plan_id={mem_plan_id} score={score:.3f}: {text}"
            )

        return "\n".join(lines)
    except Exception:
        logger.exception(
            "Failed to fetch security memory context for plan %s",
            plan_id[:8],
        )
        return ""

async def _store_event(event: BaseEvent) -> None:
    await store_event(
        http_client,
        event,
        logger=logger,
        error_message="Failed to store event %s",
    )
