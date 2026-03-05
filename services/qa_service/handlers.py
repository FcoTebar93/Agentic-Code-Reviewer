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
            static_report = _summarise_static_report(static_issues)
        else:
            static_report = (
                "No static analysis issues or warnings were reported by linters or "
                "security tools (ruff, Bandit, Semgrep, ESLint/javac if enabled)."
            )

        raw_mode = getattr(payload, "mode", "normal") or "normal"
        mode = str(raw_mode).strip().lower()
        if mode in {"save", "ahorro"} and not _has_severe_static_issues(static_issues):
            auto_reason = (
                "Approved in save mode: linters and security tools did not find "
                "high-severity issues. PASS is allowed without running the full "
                "LLM review."
            )
            result = ReviewResult(
                passed=True,
                issues=static_issues,
                reasoning=auto_reason,
            )
            prompt_tokens = 0
            completion_tokens = 0
        else:
            llm = get_llm_provider(
                provider_name=deps.cfg.llm_provider,
                redis_url=deps.cfg.redis_url,
            )
            short_term_memory = await _build_short_term_memory(plan_id, deps, limit=15)
            repo_context = await _build_repo_context(
                payload.file_path, payload.code, deps
            )
            patterns_context = await _build_failure_patterns_context(
                payload.file_path, deps
            )
            if patterns_context:
                if repo_context:
                    repo_context = repo_context + "\n\n" + patterns_context
                else:
                    repo_context = patterns_context
            qa_context = _build_qa_context(
                short_term_memory=short_term_memory,
                repo_context=repo_context,
            )
            result, prompt_tokens, completion_tokens = await review_code(
                llm=llm,
                code=payload.code,
                file_path=payload.file_path,
                language=payload.language,
                task_description=(
                    f"Generate {payload.language} code for {payload.file_path}"
                ),
                dev_reasoning=dev_reasoning,
                short_term_memory=qa_context,
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
        mode=getattr(payload, "mode", "normal"),
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
        edit_scope="file",
    )
    retry_payload = TaskAssignedPayload(
        plan_id=original.plan_id,
        task=retry_spec,
        qa_feedback=feedback,
        mode=getattr(original, "mode", "normal"),
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


def _build_qa_context(
    short_term_memory: str,
    repo_context: str,
    max_chars: int = 2500,
) -> str:
    """
    Construye un contexto compacto y estructurado para el LLM de QA.

    - Da prioridad a la memoria reciente del plan.
    - Añade un pequeño bloque con usos relacionados en el repositorio.
    - Recorta el resultado para mantener bajo el uso de tokens.
    """
    blocks: list[str] = []

    stm = (short_term_memory or "").strip()
    if stm:
        blocks.append("MEMORIA RECIENTE DEL PLAN:\n" + stm[:1800])

    repo = (repo_context or "").strip()
    if repo:
        blocks.append("CONTEXTO DEL REPOSITORIO:\n" + repo[:500])

    combined = "\n\n".join(blocks)
    if len(combined) > max_chars:
        combined = combined[:max_chars]
    return combined or "None."


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


async def _build_failure_patterns_context(
    file_path: str,
    deps: QADeps,
) -> str:
    """
    Usa la herramienta failure_patterns para recuperar patrones históricos
    de fallos en módulos cercanos al archivo que estamos revisando.
    """
    if not deps.tool_registry or not (file_path or "").strip():
        return ""
    directory = (
        file_path.replace("\\", "/").rsplit("/", 1)[0]
        if "/" in file_path.replace("\\", "/")
        else ""
    )
    try:
        result = await execute_tool(
            deps.tool_registry,
            "failure_patterns",
            {"module_prefix": directory or None, "limit": 200},
        )
        if not result.success:
            return ""
        payload = result.output or {}
        patterns = payload.get("patterns") or []
        if not isinstance(patterns, list) or not patterns:
            return ""
        lines: list[str] = []
        for p in patterns[:3]:
            if not isinstance(p, dict):
                continue
            module = str(p.get("module", ""))
            qa_n = int(p.get("qa_failed", 0) or 0)
            sec_n = int(p.get("security_blocked", 0) or 0)
            pieces = []
            if qa_n:
                pieces.append(f"QA_FAILED x{qa_n}")
            if sec_n:
                pieces.append(f"SEC_BLOCKED x{sec_n}")
            if not pieces:
                continue
            lines.append(f"- {module}: " + ", ".join(pieces))
        if not lines:
            return ""
        return (
            "Historical failure patterns near this module "
            "(aggregated qa.failed/security.blocked):\n" + "\n".join(lines)
        )
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

    if lang in {"javascript", "js", "typescript", "ts"} and deps.cfg.enable_js_lint:
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

    if lang == "java" and deps.cfg.enable_java_lint:
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

    if deps.cfg.enable_semgrep and lang in {
        "python",
        "javascript",
        "js",
        "typescript",
        "ts",
        "java",
    }:
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


def _summarise_static_report(issues: list[str], max_examples: int = 8) -> str:
    """
    Resume la salida de linters/herramientas estáticas para el prompt de QA.

    - Agrupa por origen (ruff, bandit, semgrep, eslint, javac, etc.).
    - Devuelve un resumen corto con contadores y algunos ejemplos, en lugar de
      volcar todas las líneas, para reducir tokens.
    """
    if not issues:
        return (
            "No static analysis issues or warnings were reported by linters or "
            "security tools (ruff, Bandit, Semgrep, ESLint/javac if enabled)."
        )

    by_source: dict[str, int] = {}
    for issue in issues:
        prefix = issue.split("]", 1)[0] if issue.startswith("[") else issue.split(" ", 1)[0]
        by_source[prefix] = by_source.get(prefix, 0) + 1

    summary_parts = [f"{src} x{count}" for src, count in sorted(by_source.items())]
    header = "Static analysis tools reported the following issues and warnings:\n"
    header += "Resumen por origen: " + "; ".join(summary_parts)

    examples: list[str] = []
    for idx, issue in enumerate(issues[:max_examples], start=1):
        examples.append(f"{idx}. {issue}")

    if len(issues) > max_examples:
        examples.append(
            f"... y {len(issues) - max_examples} issue(s) adicionales no listados aquí."
        )

    return header + "\nEjemplos:\n" + "\n".join(examples)


def _has_severe_static_issues(issues: list[str]) -> bool:
    """
    Heurística simple para detectar issues \"graves\" a partir del texto de
    los linters/semgrep/bandit: buscamos palabras clave de severidad alta.
    """
    if not issues:
        return False
    severe_keywords = ("HIGH", "CRITICAL", "BLOCKER", "ERROR")
    for issue in issues:
        upper = issue.upper()
        if any(kw in upper for kw in severe_keywords):
            return True
    return False

