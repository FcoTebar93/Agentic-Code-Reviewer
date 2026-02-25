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

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response, agent_execution_time, tasks_completed
from shared.contracts.events import (
    BaseEvent,
    EventType,
    CodeGeneratedPayload,
    PRRequestedPayload,
    TaskAssignedPayload,
    QAResultPayload,
    TaskSpec,
    code_generated,
    pr_requested,
    task_assigned,
    qa_passed,
    qa_failed,
)
from shared.llm_adapter import get_llm_provider
from shared.utils.rabbitmq import EventBus, IdempotencyStore
from shared.tools import ToolRegistry, execute_tool
from services.qa_service.config import QAConfig
from services.qa_service.reviewer import review_code, ReviewResult
from services.qa_service.tools import build_qa_tool_registry

SERVICE_NAME = "qa_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: QAConfig | None = None
tool_registry: ToolRegistry | None = None

_dev_reasoning_cache: dict[str, str] = {}
_qa_reasoning_cache: dict[str, str] = {}

@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg, tool_registry
    logger = setup_logging(SERVICE_NAME)

    cfg = QAConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=30.0)

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
        await _handle_code_review(payload)

    await event_bus.subscribe(
        queue_name="qa_service.code_review",
        routing_keys=[EventType.CODE_GENERATED.value],
        handler=handler,
        idempotency_store=idem_store,
        max_retries=3,
    )


async def _handle_code_review(payload: CodeGeneratedPayload) -> None:
    plan_id = payload.plan_id
    task_id = payload.task_id
    logger.info(
        "Reviewing code for task %s (plan %s, qa_attempt=%d)",
        task_id[:8],
        plan_id[:8],
        payload.qa_attempt,
    )

    dev_reasoning = payload.reasoning or ""
    _dev_reasoning_cache[task_id] = dev_reasoning

    with agent_execution_time.labels(service=SERVICE_NAME, operation="code_review").time():
        static_issues = await _run_static_lint(
            code=payload.code,
            file_path=payload.file_path,
            language=payload.language,
        )

        if static_issues:
            reasoning = (
                f"Static linting detected {len(static_issues)} issue(s) before LLM review. "
                "Rejecting this change until the issues reported by the linter are fixed."
            )
            result = ReviewResult(
                passed=False,
                issues=static_issues,
                reasoning=reasoning,
            )
        else:
            llm = get_llm_provider()
            short_term_memory = await _build_short_term_memory(plan_id)
            result = await review_code(
                llm=llm,
                code=payload.code,
                file_path=payload.file_path,
                language=payload.language,
                task_description=f"Generate {payload.language} code for {payload.file_path}",
                dev_reasoning=dev_reasoning,
                short_term_memory=short_term_memory,
            )

    _qa_reasoning_cache[task_id] = result.reasoning or ""

    qa_payload = QAResultPayload(
        plan_id=plan_id,
        task_id=task_id,
        passed=result.passed,
        issues=result.issues,
        code=payload.code,
        file_path=payload.file_path,
        qa_attempt=payload.qa_attempt,
        reasoning=result.reasoning,
    )

    if result.passed:
        step_delay = float(cfg.step_delay)
        if step_delay > 0:
            logger.info("Pausing %.1fs before publishing qa.passed (AGENT_STEP_DELAY)", step_delay)
            await asyncio.sleep(step_delay)

        logger.info("QA PASSED for task %s", task_id[:8])
        tasks_completed.labels(service=SERVICE_NAME).inc()

        qa_event = qa_passed(SERVICE_NAME, qa_payload)
        await event_bus.publish(qa_event)
        await _store_event(qa_event)

        await _update_task_state(task_id, plan_id, "qa_passed")
        await _check_plan_ready_for_pr(plan_id)
    else:
        logger.warning(
            "QA FAILED for task %s (attempt %d): %s",
            task_id[:8],
            payload.qa_attempt,
            result.issues,
        )
        if payload.qa_attempt < cfg.max_qa_retries:
            await _retry_task(payload, result.issues)
        else:
            logger.error(
                "QA exhausted retries for task %s -> marking qa.failed",
                task_id[:8],
            )
            fail_event = qa_failed(SERVICE_NAME, qa_payload)
            await event_bus.publish(fail_event)
            await _store_event(fail_event)
            await _update_task_state(task_id, plan_id, "qa_failed")


async def _retry_task(
    original: CodeGeneratedPayload, issues: list[str]
) -> None:
    """Re-enqueue the task to dev_service with QA feedback embedded."""
    feedback = "Previous QA issues to fix:\n" + "\n".join(f"- {i}" for i in issues)
    retry_spec = TaskSpec(
        task_id=original.task_id,
        description=f"Fix the following issues in {original.file_path}:\n{feedback}",
        file_path=original.file_path,
        language=original.language,
    )
    retry_payload = TaskAssignedPayload(
        plan_id=original.plan_id,
        task=retry_spec,
        qa_feedback=feedback,
    )
    retry_event = task_assigned(SERVICE_NAME, retry_payload)
    await event_bus.publish(retry_event)
    await _store_event(retry_event)

    await _update_task_state(
        original.task_id,
        original.plan_id,
        "qa_retry",
        qa_attempt=original.qa_attempt + 1,
    )
    logger.info(
        "Re-enqueued task %s to dev_service (qa_attempt=%d)",
        original.task_id[:8],
        original.qa_attempt + 1,
    )


async def _check_plan_ready_for_pr(plan_id: str) -> None:
    """
    Check if all tasks in the plan have passed QA.
    If so, aggregate files (with combined dev+QA reasoning) and publish pr.requested.
    """
    try:
        resp = await http_client.get(f"/tasks/{plan_id}")
        resp.raise_for_status()
        all_tasks = resp.json()

        if not all_tasks:
            return

        if all(t["status"] == "qa_passed" for t in all_tasks):
            files = [
                CodeGeneratedPayload(
                    plan_id=plan_id,
                    task_id=t["task_id"],
                    file_path=t["file_path"],
                    code=t["code"],
                    reasoning=_build_chain_reasoning(t["task_id"]),
                )
                for t in all_tasks
            ]
            repo_url = next((t.get("repo_url", "") for t in all_tasks), "")
            pr_payload = PRRequestedPayload(
                plan_id=plan_id,
                repo_url=repo_url,
                branch_name=f"admadc/plan-{plan_id[:8]}",
                files=files,
                commit_message=f"feat: implement plan {plan_id[:8]} (QA approved)",
                security_approved=False,
            )
            pr_event = pr_requested(SERVICE_NAME, pr_payload)
            await event_bus.publish(pr_event)
            await _store_event(pr_event)
            logger.info(
                "All tasks QA-passed for plan %s, pr.requested published to security_service",
                plan_id[:8],
            )
    except Exception:
        logger.exception("Error checking plan QA completion for %s", plan_id[:8])


def _build_chain_reasoning(task_id: str) -> str:
    """Build the combined dev+QA reasoning string for a task."""
    dev = _dev_reasoning_cache.get(task_id, "")
    qa = _qa_reasoning_cache.get(task_id, "")
    parts = []
    if dev:
        parts.append(f"[Developer] {dev}")
    if qa:
        parts.append(f"[QA Reviewer] {qa}")
    return "\n".join(parts)


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
    task_id: str,
    plan_id: str,
    status: str,
    qa_attempt: int | None = None,
) -> None:
    try:
        body: dict[str, Any] = {
            "task_id": task_id,
            "plan_id": plan_id,
            "status": status,
            "file_path": "",
            "code": "",
        }
        if qa_attempt is not None:
            body["qa_attempt"] = qa_attempt
        await http_client.post("/tasks", json=body)
    except Exception:
        logger.exception("Failed to update task state %s", task_id[:8])


async def _build_short_term_memory(plan_id: str, limit: int = 30) -> str:
    """
    Build a compact short-term memory window for QA for a given plan_id by
    querying recent events from the memory_service.
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
                "Failed to fetch QA short-term memory for plan %s (status=%s)",
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
            "Error while building QA short-term memory for plan %s",
            plan_id[:8],
        )
        return ""


async def _run_static_lint(
    code: str,
    file_path: str,
    language: str,
) -> list[str]:
    """
    Ejecuta el tool python_lint cuando el lenguaje es Python y devuelve
    una lista de issues en formato legible para el agente.
    """
    global tool_registry
    if language.lower() != "python":
        return []
    if not tool_registry:
        return []

    try:
        result = await execute_tool(
            tool_registry,
            "python_lint",
            {
                "language": "python",
                "code": code,
                "file_path": file_path or "tmp.py",
            },
        )
        if not result.success:
            logger.warning("python_lint tool failed: %s", result.error)
            return []

        payload = result.output or {}
        if not payload.get("supported", True):
            return []
        issues = payload.get("issues") or []
        formatted: list[str] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            line = issue.get("line")
            col = issue.get("column")
            code_str = issue.get("code", "")
            msg = issue.get("message", "")
            formatted.append(f"[ruff {code_str}] L{line}:C{col} {msg}")
        return formatted
    except Exception:
        logger.exception("Error while running python_lint tool")
        return []
