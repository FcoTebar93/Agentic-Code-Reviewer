from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from shared.contracts.events import (
    BaseEvent,
    EventType,
    CodeGeneratedPayload,
    PRRequestedPayload,
    TaskAssignedPayload,
    QAResultPayload,
    TaskSpec,
    TokensUsedPayload,
    code_generated,
    pr_requested,
    task_assigned,
    qa_passed,
    qa_failed,
    metrics_tokens_used,
)
from shared.llm_adapter import get_llm_provider
from shared.observability.metrics import agent_execution_time, tasks_completed
from shared.tools import ToolRegistry, execute_tool
from shared.utils import EventBus, build_short_term_memory_window, store_event
from services.qa_service.config import QAConfig
from services.qa_service.reviewer import review_code, ReviewResult


@dataclass
class QADeps:
    logger: logging.Logger
    cfg: QAConfig
    http_client: httpx.AsyncClient
    event_bus: EventBus
    tool_registry: ToolRegistry | None
    dev_reasoning_cache: dict[str, str]
    qa_reasoning_cache: dict[str, str]
    pr_requested_plan_ids: set[str]


async def handle_code_review(payload: CodeGeneratedPayload, deps: QADeps) -> None:
    """
    Main entrypoint for handling a code.generated event in qa_service.
    """
    plan_id = payload.plan_id
    task_id = payload.task_id

    deps.logger.info(
        "Reviewing code for task %s (plan %s, qa_attempt=%d)",
        task_id[:8],
        plan_id[:8],
        payload.qa_attempt,
    )

    dev_reasoning = payload.reasoning or ""
    deps.dev_reasoning_cache[task_id] = dev_reasoning

    prompt_tokens = 0
    completion_tokens = 0

    with agent_execution_time.labels(service="qa_service", operation="code_review").time():
        static_issues = await _run_static_lint(
            code=payload.code,
            file_path=payload.file_path,
            language=payload.language,
            deps=deps,
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
            short_term_memory = await _build_short_term_memory(plan_id, deps, limit=15)
            repo_context = await _build_repo_context(
                payload.file_path, payload.code, deps
            )
            memory_with_repo = "\n".join(
                [p for p in [short_term_memory, repo_context] if p]
            )
            static_report = (
                "No static analysis issues or warnings were reported by linters or security tools "
                "(ruff, Bandit, Semgrep, ESLint/javac if enabled)."
            )
            result, prompt_tokens, completion_tokens = await review_code(
                llm=llm,
                code=payload.code,
                file_path=payload.file_path,
                language=payload.language,
                task_description=f"Generate {payload.language} code for {payload.file_path}",
                dev_reasoning=dev_reasoning,
                short_term_memory=memory_with_repo,
                static_analysis_report=static_report,
            )

    if prompt_tokens or completion_tokens:
        tok_event = metrics_tokens_used(
            "qa_service",
            TokensUsedPayload(
                plan_id=plan_id,
                service="qa_service",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )
        await store_event(
            deps.http_client,
            tok_event,
            logger=deps.logger,
            error_message="Failed to store event %s",
        )

    deps.qa_reasoning_cache[task_id] = result.reasoning or ""

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
        step_delay = float(deps.cfg.step_delay)
        if step_delay > 0:
            deps.logger.info(
                "Pausing %.1fs before publishing qa.passed (AGENT_STEP_DELAY)",
                step_delay,
            )
            await asyncio.sleep(step_delay)

        deps.logger.info("QA PASSED for task %s", task_id[:8])
        tasks_completed.labels(service="qa_service").inc()

        qa_event = qa_passed("qa_service", qa_payload)
        await deps.event_bus.publish(qa_event)
        await store_event(
            deps.http_client,
            qa_event,
            logger=deps.logger,
            error_message="Failed to store event %s",
        )

        await _update_task_state(
            deps.http_client,
            task_id,
            plan_id,
            "qa_passed",
        )
        await _check_plan_ready_for_pr(plan_id, deps)
    else:
        deps.logger.warning(
            "QA FAILED for task %s (attempt %d): %s",
            task_id[:8],
            payload.qa_attempt,
            result.issues,
        )
        if payload.qa_attempt < deps.cfg.max_qa_retries:
            await _retry_task(payload, result.issues, deps)
        else:
            deps.logger.error(
                "QA exhausted retries for task %s -> marking qa.failed",
                task_id[:8],
            )
            fail_event = qa_failed("qa_service", qa_payload)
            await deps.event_bus.publish(fail_event)
            await store_event(
                deps.http_client,
                fail_event,
                logger=deps.logger,
                error_message="Failed to store event %s",
            )
            await _update_task_state(
                deps.http_client,
                task_id,
                plan_id,
                "qa_failed",
            )


async def _retry_task(
    original: CodeGeneratedPayload,
    issues: list[str],
    deps: QADeps,
) -> None:
    """Re-enqueue the task to dev_service with QA feedback embedded."""
    next_attempt = original.qa_attempt + 1
    await _update_task_state(
        deps.http_client,
        original.task_id,
        original.plan_id,
        "qa_retry",
        qa_attempt=next_attempt,
    )

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
    retry_event = task_assigned("qa_service", retry_payload)
    await deps.event_bus.publish(retry_event)
    await store_event(
        deps.http_client,
        retry_event,
        logger=deps.logger,
        error_message="Failed to store event %s",
    )

    deps.logger.info(
        "Re-enqueued task %s to dev_service (qa_attempt=%d)",
        original.task_id[:8],
        next_attempt,
    )


async def _check_plan_ready_for_pr(plan_id: str, deps: QADeps) -> None:
    """
    Check if all tasks in the plan have passed QA.
    If so, aggregate files (with combined dev+QA reasoning) and publish pr.requested.
    """
    try:
        if plan_id in deps.pr_requested_plan_ids:
            return

        resp = await deps.http_client.get(f"/tasks/{plan_id}")
        resp.raise_for_status()
        all_tasks = resp.json()

        if not all_tasks:
            return

        if not all(t["status"] == "qa_passed" for t in all_tasks):
            return

        seen_paths: set[str] = set()
        files: list[CodeGeneratedPayload] = []
        for t in all_tasks:
            fp = t.get("file_path", "")
            if fp in seen_paths:
                continue
            seen_paths.add(fp)
            files.append(
                CodeGeneratedPayload(
                    plan_id=plan_id,
                    task_id=t["task_id"],
                    file_path=fp,
                    code=t["code"],
                    reasoning=_build_chain_reasoning(
                        t["task_id"], deps.dev_reasoning_cache, deps.qa_reasoning_cache
                    ),
                )
            )

        deps.pr_requested_plan_ids.add(plan_id)
        repo_url = next((t.get("repo_url", "") for t in all_tasks), "")
        pr_payload = PRRequestedPayload(
            plan_id=plan_id,
            repo_url=repo_url,
            branch_name=f"admadc/plan-{plan_id[:8]}",
            files=files,
            commit_message=f"feat: implement plan {plan_id[:8]} (QA approved)",
            security_approved=False,
        )
        pr_event = pr_requested("qa_service", pr_payload)
        await deps.event_bus.publish(pr_event)
        await store_event(
            deps.http_client,
            pr_event,
            logger=deps.logger,
            error_message="Failed to store event %s",
        )
        deps.logger.info(
            "All tasks QA-passed for plan %s, pr.requested published (%d file(s))",
            plan_id[:8],
            len(files),
        )
    except Exception:
        deps.logger.exception("Error checking plan QA completion for %s", plan_id[:8])


def _build_chain_reasoning(
    task_id: str,
    dev_reasoning_cache: dict[str, str],
    qa_reasoning_cache: dict[str, str],
) -> str:
    """Build the combined dev+QA reasoning string for a task."""
    dev = dev_reasoning_cache.get(task_id, "")
    qa = qa_reasoning_cache.get(task_id, "")
    parts: list[str] = []
    if dev:
        parts.append(f"[Developer] {dev}")
    if qa:
        parts.append(f"[QA Reviewer] {qa}")
    return "\n".join(parts)


async def _update_task_state(
    http_client: httpx.AsyncClient,
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
        pass


async def _build_short_term_memory(
    plan_id: str,
    deps: QADeps,
    limit: int = 15,
) -> str:
    """
    Build a compact short-term memory window for QA using the tool query_events.
    """
    if not deps.tool_registry:
        return ""

    try:
        result = await execute_tool(
            deps.tool_registry,
            "query_events",
            {"plan_id": plan_id, "event_type": None, "limit": limit},
        )
        if not result.success:
            deps.logger.warning(
                "query_events tool failed for plan %s: %s",
                plan_id[:8],
                result.error,
            )
            return ""

        payload = result.output or {}
        events = (
            payload.get("events")
            if isinstance(payload.get("events"), list)
            else []
        )
        if not events:
            return ""

        return build_short_term_memory_window(events, limit=limit)
    except Exception:
        deps.logger.exception(
            "Error while building QA short-term memory for plan %s",
            plan_id[:8],
        )
        return ""


async def _build_repo_context(
    file_path: str,
    code: str,
    deps: QADeps,
) -> str:
    """
    Use the search_in_repo tool to find references to the module/file
    in the directory, giving context to the reviewer (style, similar usages).
    """
    if not deps.tool_registry or not (file_path or "").strip():
        return ""
    base = file_path.replace("\\", "/").rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    if not stem or len(stem) < 2:
        return ""
    directory = (
        file_path.replace("\\", "/").rsplit("/", 1)[0]
        if "/" in file_path
        else "."
    )
    try:
        result = await execute_tool(
            deps.tool_registry,
            "search_in_repo",
            {"pattern": stem, "directory": directory, "max_results": 15},
        )
        if not result.success:
            return ""
        out = result.output or {}
        matches = out.get("matches") or []
        if not matches:
            return ""
        lines = [
            f"  {m.get('file', '')}:L{m.get('line', 0)} {str(m.get('snippet', ''))[:80]}"
            for m in matches[:10]
            if isinstance(m, dict)
        ]
        return "Related usages in repo (search_in_repo):\n" + "\n".join(lines)
    except Exception:
        return ""


async def _run_static_lint(
    code: str,
    file_path: str,
    language: str,
    deps: QADeps,
) -> list[str]:
    """
    Run language-specific static analysis tools and return a list of issues
    formatted for the QA agent.
    """
    if not deps.tool_registry:
        return []

    lang = (language or "").lower()
    formatted: list[str] = []

    if lang == "python":
        try:
            result = await execute_tool(
                deps.tool_registry,
                "python_lint",
                {
                    "language": "python",
                    "code": code,
                    "file_path": file_path or "tmp.py",
                },
            )
            if not result.success:
                deps.logger.warning("python_lint tool failed: %s", result.error)
            else:
                payload = result.output or {}
                if payload.get("supported", True):
                    issues = payload.get("issues") or []
                    for issue in issues:
                        if not isinstance(issue, dict):
                            continue
                        line = issue.get("line")
                        col = issue.get("column")
                        code_str = issue.get("code", "")
                        msg = issue.get("message", "")
                        formatted.append(f"[ruff {code_str}] L{line}:C{col} {msg}")
        except Exception:
            deps.logger.exception("Error while running python_lint tool")

        try:
            result = await execute_tool(
                deps.tool_registry,
                "python_security_scan",
                {
                    "language": "python",
                    "code": code,
                    "file_path": file_path or "tmp.py",
                },
            )
            if not result.success:
                deps.logger.warning("python_security_scan tool failed: %s", result.error)
            else:
                payload = result.output or {}
                if payload.get("supported", True):
                    issues = payload.get("issues") or []
                    for issue in issues:
                        if not isinstance(issue, dict):
                            continue
                        line = issue.get("line")
                        sev = (issue.get("severity") or "").upper()
                        code_str = issue.get("code", "")
                        msg = issue.get("message", "")
                        formatted.append(f"[bandit {sev} {code_str}] L{line}: {msg}")
        except Exception:
            deps.logger.exception("Error while running python_security_scan tool")

    if lang in {"javascript", "js", "typescript", "ts"}:
        try:
            result = await execute_tool(
                deps.tool_registry,
                "js_ts_lint",
                {
                    "language": language,
                    "code": code,
                    "file_path": file_path or "tmp",
                },
            )
            if not result.success:
                deps.logger.warning("js_ts_lint tool failed: %s", result.error)
            else:
                payload = result.output or {}
                if payload.get("supported", True):
                    issues = payload.get("issues") or []
                    for issue in issues:
                        if not isinstance(issue, dict):
                            continue
                        line = issue.get("line")
                        col = issue.get("column")
                        rule_id = issue.get("rule_id", "")
                        msg = issue.get("message", "")
                        formatted.append(f"[eslint {rule_id}] L{line}:C{col} {msg}")
        except Exception:
            deps.logger.exception("Error while running js_ts_lint tool")

    if lang == "java":
        try:
            result = await execute_tool(
                deps.tool_registry,
                "java_lint",
                {
                    "language": "java",
                    "code": code,
                    "file_path": file_path or "Tmp.java",
                },
            )
            if not result.success:
                deps.logger.warning("java_lint tool failed: %s", result.error)
            else:
                payload = result.output or {}
                if payload.get("supported", True):
                    issues = payload.get("issues") or []
                    for issue in issues:
                        if not isinstance(issue, dict):
                            continue
                        line = issue.get("line")
                        msg = issue.get("message", "")
                        formatted.append(f"[javac] L{line}: {msg}")
        except Exception:
            deps.logger.exception("Error while running java_lint tool")

    if lang in {"python", "javascript", "js", "typescript", "ts", "java"}:
        try:
            result = await execute_tool(
                deps.tool_registry,
                "semgrep_scan",
                {
                    "language": language,
                    "code": code,
                    "file_path": file_path or "tmp",
                },
            )
            if not result.success:
                deps.logger.warning("semgrep_scan tool failed: %s", result.error)
            else:
                payload = result.output or {}
                if payload.get("supported", True):
                    issues = payload.get("issues") or []
                    for issue in issues:
                        if not isinstance(issue, dict):
                            continue
                        line = issue.get("line")
                        sev = (issue.get("severity") or "").upper()
                        code_str = issue.get("code", "")
                        msg = issue.get("message", "")
                        formatted.append(f"[semgrep {sev} {code_str}] L{line}: {msg}")
        except Exception:
            deps.logger.exception("Error while running semgrep_scan tool")

    return formatted

