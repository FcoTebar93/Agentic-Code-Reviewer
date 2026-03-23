from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from shared.http.client import create_async_http_client
from shared.logging.logger import setup_logging
from shared.middleware.correlation import install_correlation_middleware
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
from shared.utils import EventBus, IdempotencyStore, store_event
from shared.tools import ToolRegistry, execute_tool
from services.replanner_service.config import ReplannerConfig
from services.replanner_service.critic import analyse_outcome, analyse_outcome_with_tool_loop
from services.replanner_service.tools import build_replanner_tool_registry

SERVICE_NAME = "replanner_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: ReplannerConfig | None = None
tool_registry: ToolRegistry | None = None

_replan_suggested_for_plan: dict[str, bool] = {}

def _infer_group_id(file_path: str) -> str:
    """
    Deriva un identificador de grupo/módulo a partir del file_path.

    Mantiene la misma heurística que el meta_planner para poder alinear
    las decisiones de replanning con los grupos de tareas originales.
    """
    norm = (file_path or "").replace("\\", "/").strip()
    if not norm:
        return "root"
    parts = norm.split("/")
    if len(parts) >= 3:
        return "/".join(parts[:3])
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return norm


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg, tool_registry
    logger = setup_logging(SERVICE_NAME)

    cfg = ReplannerConfig.from_env()
    http_client = create_async_http_client(
        base_url=cfg.memory_service_url,
        default_timeout=30.0,
    )

    tool_registry = build_replanner_tool_registry(memory_service_url=cfg.memory_service_url)

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
install_correlation_middleware(app)
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

    Degradación controlada: si algo falla (LLM, memory_service, etc.), el
    pipeline continúa sin replanning para este plan.
    """
    if cfg is None:
        return

    target_group_ids: list[str] = []
    if isinstance(outcome, QAResultPayload):
        fp = (outcome.file_path or "").strip()
        if fp:
            target_group_ids.append(_infer_group_id(fp))
    elif isinstance(outcome, SecurityResultPayload):
        ctx = getattr(outcome, "pr_context", {}) or {}
        files = ctx.get("files") or []
        modules: set[str] = set()
        if isinstance(files, list):
            for f in files:
                if not isinstance(f, dict):
                    continue
                fp = (f.get("file_path") or "").strip()
                if not fp:
                    continue
                modules.add(_infer_group_id(fp))
        if modules:
            target_group_ids.extend(list(modules)[:5])

    try:
        with agent_execution_time.labels(
            service=SERVICE_NAME, operation=f"replan_{outcome_type}"
        ).time():
            llm = get_llm_provider(provider_name=cfg.llm_provider)
            memory_context = await _fetch_memory_context(plan_id)

            if cfg.enable_tool_loop and tool_registry is not None:
                result, prompt_tokens, completion_tokens = (
                    await analyse_outcome_with_tool_loop(
                        llm,
                        tool_registry,
                        agent_goal=cfg.agent_goal,
                        plan_id=plan_id,
                        outcome=outcome,
                        memory_context=memory_context,
                        outcome_type=outcome_type,
                        max_steps=cfg.tool_loop_max_steps,
                    )
                )
            else:
                result, prompt_tokens, completion_tokens = await analyse_outcome(
                    llm=llm,
                    agent_goal=cfg.agent_goal,
                    plan_id=plan_id,
                    outcome=outcome,
                    memory_context=memory_context,
                    outcome_type=outcome_type,
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
                await store_event(
                    http_client,
                    tok_event,
                    logger=logger,
                    error_message="Failed to store replanner event %s",
                )
    except Exception:
        logger.exception(
            "Replanner failed while analysing outcome for plan %s (type=%s). "
            "Skipping replanning but keeping pipeline running.",
            plan_id[:8],
            outcome_type,
        )
        return

    if not result.revision_needed:
        logger.info(
            "Replanner decided no revision needed for plan %s (severity=%s)",
            plan_id[:8],
            result.severity,
        )
        return
    if _replan_suggested_for_plan.get(plan_id):
        logger.info(
            "Replanner already emitted a plan.revision_suggested for plan %s; skipping.",
            plan_id[:8],
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
        target_group_ids=target_group_ids,
    )
    event = plan_revision_suggested(SERVICE_NAME, revision_payload)
    await event_bus.publish(event)
    await store_event(
        http_client,
        event,
        logger=logger,
        error_message="Failed to store replanner event %s",
    )

    logger.info(
        "Emitted plan.revision_suggested for original plan %s (new_plan_id=%s, severity=%s)",
        plan_id[:8],
        revision_payload.new_plan_id[:8],
        revision_payload.severity,
    )
    _replan_suggested_for_plan[plan_id] = True


async def _fetch_memory_context(plan_id: str, limit: int = 5) -> str:
    """
    Retrieve semantic memory focused on this plan id to provide context
    to the replanner (previous conclusions, QA failures, security blocks),
    as well as aggregated historical failure patterns by module.
    """
    global tool_registry
    if tool_registry is None:
        return ""

    try:
        semantic_result = await execute_tool(
            tool_registry,
            "semantic_outcome_memory",
            {"plan_id": plan_id, "limit": limit},
        )
        if not semantic_result.success:
            logger.warning(
                "Replanner semantic search tool failed for plan %s: %s",
                plan_id[:8],
                semantic_result.error,
            )
            semantic_lines: list[str] = []
        else:
            payload = semantic_result.output or {}
            results = payload.get("results") or []
            semantic_lines: list[str] = []
            if isinstance(results, list) and results:
                for item in results[:limit]:
                    p = item.get("payload") or {}
                    score = item.get("heuristic_score", item.get("score", 0.0))
                    text = str(p.get("text", ""))[:400].replace("\n", " ")
                    etype = p.get("event_type", "")
                    semantic_lines.append(f"- [{etype}] score={score:.3f}: {text}")

        patterns_lines: list[str] = []
        patterns_result = await execute_tool(
            tool_registry,
            "failure_patterns",
            {"module_prefix": None, "limit": 200},
        )
        if patterns_result.success and isinstance(patterns_result.output, dict):
            raw_patterns = patterns_result.output.get("patterns") or []
            for p in raw_patterns[:4]:
                if not isinstance(p, dict):
                    continue
                module = str(p.get("module", ""))
                qa_n = int(p.get("qa_failed", 0) or 0)
                sec_n = int(p.get("security_blocked", 0) or 0)
                if qa_n == 0 and sec_n == 0:
                    continue
                pieces: list[str] = []
                if qa_n:
                    pieces.append(f"QA_FAILED x{qa_n}")
                if sec_n:
                    pieces.append(f"SEC_BLOCKED x{sec_n}")
                sample = ", ".join(p.get("sample_issues", [])[:2])
                if sample:
                    patterns_lines.append(
                        f"- {module}: " + ", ".join(pieces) + f" | samples: {sample}"
                    )
                else:
                    patterns_lines.append(f"- {module}: " + ", ".join(pieces))

        blocks: list[str] = []
        if semantic_lines:
            blocks.append(
                "SEMANTIC OUTCOME MEMORY (pipeline conclusions, QA/SEC results):\n"
                + "\n".join(semantic_lines)
            )
        if patterns_lines:
            blocks.append(
                "HISTORICAL FAILURE PATTERNS (hot modules with frequent qa.failed/security.blocked):\n"
                + "\n".join(patterns_lines)
            )

        return "\n\n".join(blocks).strip()
    except Exception:
        logger.exception(
            "Failed to fetch memory context for replanner (plan %s)",
            plan_id[:8],
        )
        return ""

