"""Dev Service -- the AI developer agent."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastapi import FastAPI

from services.dev_service.config import DevConfig
from services.dev_service.deps import DevPipelineDeps
from services.dev_service.deterministic_gates import format_gate_command
from services.dev_service.generator import generate_code, generate_code_with_tool_loop
from services.dev_service.tools import REPO_ROOT, build_dev_tool_registry
from shared.contracts.events import (
    CodeGeneratedPayload,
    EventType,
    SpecGeneratedPayload,
    TaskAssignedPayload,
    code_generated,
)
from shared.http.client import create_async_http_client
from shared.llm_adapter import get_llm_provider
from shared.logging.logger import setup_logging
from shared.middleware.correlation import install_correlation_middleware
from shared.observability.routing import register_health_metrics_routes
from shared.observability.tokens import emit_token_usage_event
from shared.observability.metrics import (
    agent_execution_time,
    tasks_completed,
)
from shared.policies import (
    ProjectPolicy,
    effective_mode,
    load_project_policy,
    policy_for_path,
)
from shared.tools import ToolRegistry, execute_tool
from shared.utils import (
    EventBus,
    build_repo_style_hints,
    build_short_term_memory_window,
    guarded_http_get,
    maybe_agent_delay,
    short_term_memory_event_limit,
    subscribe_typed_event,
    store_event,
)
from shared.utils.code_change_guard import large_change_note
from shared.utils.lifecycle import connect_event_bus, shutdown_runtime

SERVICE_NAME = "dev_service"
event_bus: EventBus = cast(EventBus, None)
http_client: httpx.AsyncClient = cast(httpx.AsyncClient, None)
cfg: DevConfig = cast(DevConfig, None)
tool_registry: ToolRegistry = cast(ToolRegistry, None)
project_policy: ProjectPolicy | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg, tool_registry, project_policy
    logger = setup_logging(SERVICE_NAME)

    cfg = DevConfig.from_env()
    http_client = create_async_http_client(
        base_url=cfg.memory_service_url,
        default_timeout=30.0,
    )

    tool_registry = build_dev_tool_registry()
    try:
        project_policy = load_project_policy(REPO_ROOT)
    except Exception:
        project_policy = {"default_mode": "normal", "paths": {}}

    event_bus = await connect_event_bus(cfg.rabbitmq_url)

    application.state.dev_pipeline_deps = DevPipelineDeps(
        http_client=http_client,
        cfg=cfg,
        event_bus=event_bus,
        tool_registry=tool_registry,
    )

    asyncio.create_task(_consume_tasks())
    logger.info("Dev Service ready")
    yield

    await shutdown_runtime(logger=logger, event_bus=event_bus, http_client=http_client)


app = FastAPI(
    title="ADMADC - Dev Service",
    version="0.2.0",
    description="Generates code via LLM based on task specifications",
    lifespan=lifespan,
)
install_correlation_middleware(app)
logger = logging.getLogger(SERVICE_NAME)
register_health_metrics_routes(app, SERVICE_NAME)

async def _consume_tasks() -> None:
    async def on_payload(payload: TaskAssignedPayload) -> None:
        await maybe_agent_delay(logger)
        await _handle_task(payload)

    await subscribe_typed_event(
        event_bus=event_bus,
        queue_name="dev_service.tasks",
        routing_keys=[EventType.TASK_ASSIGNED.value],
        payload_model=TaskAssignedPayload,
        on_payload=on_payload,
        redis_url=cfg.redis_url if hasattr(cfg, "redis_url") else None,
        max_retries=3,
    )


async def _handle_task(payload: TaskAssignedPayload) -> None:
    task = payload.task
    plan_id = payload.plan_id
    qa_feedback = payload.qa_feedback
    if await _should_skip_task_for_idempotency(task, plan_id, qa_feedback):
        return

    logger.info(
        "Processing task %s for plan %s%s",
        task.task_id[:8],
        plan_id[:8],
        " (QA feedback present)" if qa_feedback else "",
    )

    raw_mode = getattr(payload, "mode", "normal") or "normal"

    global project_policy
    if project_policy is None:
        try:
            project_policy = load_project_policy(REPO_ROOT)
        except Exception:
            project_policy = {"default_mode": "normal", "paths": {}}
    path_policy = policy_for_path(project_policy, task.file_path or "")
    default_mode = project_policy.get("default_mode", "normal")
    mode = effective_mode(raw_mode, path_policy, default_mode)

    with agent_execution_time.labels(service=SERVICE_NAME, operation="code_gen").time():
        await _update_task_state(task.task_id, plan_id, "in_progress")

        llm = get_llm_provider(provider_name=cfg.llm_provider, redis_url=cfg.redis_url)
        short_term_memory = await _build_short_term_memory(plan_id)
        existing_file_preview = await _maybe_read_existing_file(task.file_path)
        files_in_dir = await _list_files_in_task_directory(task)
        wait_spec = not bool((qa_feedback or "").strip())
        spec_block = await _fetch_task_spec(
            plan_id,
            task.task_id,
            wait_if_missing=wait_spec,
        )
        failure_patterns_block = await _build_failure_patterns_for_dev(task.file_path)
        repo_style_hints = build_repo_style_hints(
            REPO_ROOT,
            language=task.language,
            file_path=task.file_path or "",
            max_total_chars=550,
        )
        dev_context = _build_dev_context(
            short_term_memory=short_term_memory,
            existing_file_preview=existing_file_preview,
            files_in_dir=files_in_dir,
            spec_block=spec_block,
            failure_patterns_block=failure_patterns_block,
            repo_style_hints=repo_style_hints,
            spec_max_chars=cfg.spec_context_max_chars,
            max_chars=cfg.dev_context_max_chars,
        )
        if cfg.enable_tool_loop and tool_registry is not None:
            code_result, prompt_tokens, completion_tokens = (
                await generate_code_with_tool_loop(
                    llm,
                    task,
                    plan_reasoning=payload.plan_reasoning,
                    short_term_memory=dev_context,
                    registry=tool_registry,
                    max_steps=cfg.tool_loop_max_steps,
                    include_ci_tools=cfg.tool_loop_include_ci_tools,
                    plan_id=plan_id,
                    redis_url=cfg.redis_url,
                    user_locale=getattr(payload, "user_locale", None) or "en",
                    qa_feedback=qa_feedback or "",
                )
            )
        else:
            code_result, prompt_tokens, completion_tokens = await generate_code(
                llm,
                task,
                plan_reasoning=payload.plan_reasoning,
                short_term_memory=dev_context,
                user_locale=getattr(payload, "user_locale", None) or "en",
                qa_feedback=qa_feedback or "",
            )

        await emit_token_usage_event(
            service_name=SERVICE_NAME,
            plan_id=plan_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            http_client=http_client,
            logger=logger,
        )

        current_attempt = 0
        resp = await guarded_http_get(
            http_client,
            f"/tasks/{plan_id}",
            logger,
            key="memory_service:/tasks",
        )
        if resp is not None and resp.status_code == 200:
            tasks = resp.json()
            for t in tasks:
                if t["task_id"] == task.task_id:
                    current_attempt = t.get("qa_attempt", 0)
                    break

        run_tests = path_policy.get("enable_auto_tests", True)
        run_lints = path_policy.get("enable_auto_lints", True)

        gate_timeout = cfg.auto_gates_timeout_seconds if cfg else 180.0
        lints_summary = (
            await _maybe_run_auto_lints(task, qa_feedback, mode, gate_timeout)
            if run_lints
            else ""
        )
        typecheck_summary = (
            await _maybe_run_auto_typecheck(task, qa_feedback, mode, gate_timeout)
            if cfg and cfg.enable_auto_typecheck
            else ""
        )
        tests_summary = (
            await _maybe_run_auto_tests(task, gate_timeout)
            if run_tests
            else ""
        )

        combined_reasoning = code_result.reasoning
        if lints_summary:
            suffix = f"\n[Dev Service] Automated lints summary: {lints_summary}"
            combined_reasoning = (combined_reasoning + suffix).strip()
        if typecheck_summary:
            suffix = f"\n[Dev Service] Automated typecheck summary: {typecheck_summary}"
            combined_reasoning = (combined_reasoning + suffix).strip()
        if tests_summary:
            suffix = f"\n[Dev Service] Automated tests summary: {tests_summary}"
            combined_reasoning = (combined_reasoning + suffix).strip()

        formatted_code = code_result.code
        if mode == "strict" and tool_registry is not None:
            try:
                lang = (task.language or "").lower()
                if lang in ("python", "py", "javascript", "js", "typescript", "ts"):
                    fmt_result = await execute_tool(
                        tool_registry,
                        "format_code",
                        {
                            "language": task.language,
                            "code": formatted_code,
                            "file_path": task.file_path or "tmp",
                        },
                    )
                    if fmt_result.success and isinstance(fmt_result.output, dict):
                        out = fmt_result.output
                        if out.get("supported") and isinstance(
                            out.get("formatted_code"), str
                        ):
                            formatted_code = out["formatted_code"]
                            combined_reasoning = (
                                combined_reasoning
                                + "\n[Dev Service] Code was auto-formatted before QA."
                            ).strip()
            except Exception:
                pass

        if cfg.large_diff_warn_enabled:
            prev_disk = _read_existing_repo_full_text(task.file_path or "")
            diff_note = large_change_note(
                prev_disk,
                formatted_code,
                soft_line_limit=max(10, cfg.large_diff_soft_lines),
                similarity_warn_below=min(0.95, max(0.1, cfg.large_diff_similarity)),
                qa_retry=bool((qa_feedback or "").strip()),
            )
            if diff_note:
                logger.warning(
                    "Large-change heuristic for %s: %s",
                    task.file_path,
                    diff_note,
                )
                combined_reasoning = (
                    combined_reasoning + f"\n[Dev Service] {diff_note}"
                ).strip()

        cg_payload = CodeGeneratedPayload(
            plan_id=plan_id,
            task_id=task.task_id,
            file_path=task.file_path,
            code=formatted_code,
            language=task.language,
            qa_attempt=current_attempt,
            reasoning=combined_reasoning,
            mode=mode,
            user_locale=getattr(payload, "user_locale", None) or "en",
        )
        step_delay = float(cfg.step_delay)
        if step_delay > 0:
            logger.info("Pausing %.1fs before publishing (AGENT_STEP_DELAY)", step_delay)
            await asyncio.sleep(step_delay)

        cg_event = code_generated(SERVICE_NAME, cg_payload)
        await event_bus.publish(cg_event)
        await store_event(
            http_client,
            cg_event,
            logger=logger,
            error_message="Failed to store event %s",
        )

        await _update_task_state(
            task.task_id, plan_id, "completed",
            task.file_path, code_result.code, payload.repo_url,
        )
        tasks_completed.labels(service=SERVICE_NAME).inc()

    logger.info("Task %s code generated, forwarded to qa_service", task.task_id[:8])


async def _should_skip_task_for_idempotency(task, plan_id: str, qa_feedback: str) -> bool:
    has_feedback = bool((qa_feedback or "").strip())
    resp_tasks = await guarded_http_get(
        http_client,
        f"/tasks/{plan_id}",
        logger,
        key="memory_service:/tasks",
    )
    if resp_tasks is not None and resp_tasks.status_code == 200:
        tasks = resp_tasks.json() if isinstance(resp_tasks.json(), list) else []
        existing_status: str | None = None
        for t in tasks:
            if t.get("task_id") == task.task_id:
                existing_status = str(t.get("status") or "")
                break

        if existing_status is not None:
            if not has_feedback:
                logger.info(
                    "Task %s already has task state '%s', skipping original assignment (idempotent)",
                    task.task_id[:8],
                    existing_status,
                )
                return True
            if existing_status in {"qa_passed", "qa_failed"}:
                logger.info(
                    "Task %s already finished with status '%s', skipping QA retry (idempotent)",
                    task.task_id[:8],
                    existing_status,
                )
                return True

    if not has_feedback:
        resp_events = await guarded_http_get(
            http_client,
            "/events",
            logger,
            key="memory_service:/events",
            params={
                "plan_id": plan_id,
                "event_type": EventType.CODE_GENERATED.value,
                "limit": 100,
            },
        )
        if resp_events is not None and resp_events.status_code == 200:
            events = resp_events.json() if isinstance(resp_events.json(), list) else []
            for ev in events:
                ev_payload = ev.get("payload") or {}
                if ev_payload.get("task_id") == task.task_id:
                    logger.info(
                        "Task %s already has code.generated event, skipping (idempotent)",
                        task.task_id[:8],
                    )
                    return True
    return False


async def _maybe_run_auto_tests(task, timeout_s: float) -> str:
    try:
        lang = (task.language or "").lower()
        if not (cfg and cfg.enable_auto_tests and tool_registry is not None):
            return ""
        test_cmd = _resolve_test_command(task, lang)
        return await _run_gate_command(
            tool_name="run_tests",
            command=test_cmd,
            timeout_s=timeout_s,
            ok_label="Automated tests",
            fail_label="Automated tests",
        )
    except Exception:
        return ""


async def _maybe_run_auto_lints(
    task, qa_feedback: str, mode: str, timeout_s: float
) -> str:
    try:
        if not cfg or not getattr(cfg, "enable_auto_lints", False):
            return ""
        if tool_registry is None:
            return ""

        lang = (getattr(task, "language", "") or "").lower()
        if not _should_run_wide_gate(task, qa_feedback, mode, language=lang):
            return ""

        fp = getattr(task, "file_path", "") or ""
        lint_cmd = ""
        if lang in ("python", "py"):
            tmpl = (
                cfg.lint_python_scoped_template
                if cfg.auto_gates_scoped
                else cfg.lint_python_wide_template
            )
            lint_cmd = format_gate_command(tmpl, fp)
        elif lang in ("javascript", "js"):
            lint_cmd = os.environ.get("DEV_LINT_COMMAND_JAVASCRIPT", "npm run lint")
        elif lang in ("typescript", "ts"):
            lint_cmd = os.environ.get("DEV_LINT_COMMAND_TYPESCRIPT", "npm run lint")
        elif lang == "java":
            lint_cmd = os.environ.get("DEV_LINT_COMMAND_JAVA", "")

        if not lint_cmd:
            return ""

        return await _run_gate_command(
            tool_name="run_lints",
            command=lint_cmd,
            timeout_s=timeout_s,
            ok_label="Lints",
            fail_label="Lints",
        )
    except Exception:
        return ""


async def _maybe_run_auto_typecheck(
    task, qa_feedback: str, mode: str, timeout_s: float
) -> str:
    try:
        if not cfg or not tool_registry:
            return ""
        lang = (getattr(task, "language", "") or "").lower()
        tmpl = (cfg.typecheck_python_template or "").strip()
        if lang not in ("python", "py") or not tmpl:
            return ""

        if not _should_run_wide_gate(task, qa_feedback, mode, language=lang):
            return ""

        fp = getattr(task, "file_path", "") or ""
        cmd = format_gate_command(tmpl, fp)
        if not cmd:
            return ""

        return await _run_gate_command(
            tool_name="run_lints",
            command=cmd,
            timeout_s=timeout_s,
            ok_label="Typecheck",
            fail_label="Typecheck",
        )
    except Exception:
        return ""


async def _run_gate_command(
    *,
    tool_name: str,
    command: str,
    timeout_s: float,
    ok_label: str,
    fail_label: str,
) -> str:
    if not command or not tool_registry:
        return ""
    result = await execute_tool(
        tool_registry,
        tool_name,
        {"command": command, "timeout_s": timeout_s},
    )
    if not result.success:
        return f"{fail_label} failed to run: {result.error}"
    if not isinstance(result.output, dict):
        return ""
    out = result.output
    status = (
        "PASSED"
        if out.get("exit_code") == 0 and not out.get("timed_out")
        else "FAILED"
    )
    return (
        f"{ok_label} ({out.get('command')}): {status}. "
        f"exit_code={out.get('exit_code')}, timed_out={out.get('timed_out')}."
    )


def _should_run_wide_gate(task, qa_feedback: str, mode: str, *, language: str) -> bool:
    if cfg and cfg.auto_gates_scoped and language in ("python", "py"):
        return True
    edit_scope = str(getattr(task, "edit_scope", "file") or "").lower()
    normalized_mode = (mode or "normal").strip().lower()
    has_feedback = bool((qa_feedback or "").strip())
    return normalized_mode == "strict" or has_feedback or edit_scope != "file"


def _resolve_test_command(task, lang: str) -> str:
    if not cfg:
        return ""
    if lang == "python":
        return format_gate_command(
            cfg.test_python_template,
            getattr(task, "file_path", "") or "",
        )
    if lang in ("javascript", "js"):
        return cfg.test_command_javascript
    if lang in ("typescript", "ts"):
        return cfg.test_command_typescript
    if lang == "java":
        return cfg.test_command_java
    return ""


def _glob_pattern_for_language(language: str) -> str:
    lang = (language or "python").lower()
    return {
        "python": "*.py",
        "py": "*.py",
        "javascript": "*.js",
        "js": "*.js",
        "typescript": "*.ts",
        "ts": "*.ts",
        "java": "*.java",
    }.get(lang, "*")


async def _list_files_in_task_directory(task) -> str:
    global tool_registry
    if not tool_registry:
        return ""
    file_path = getattr(task, "file_path", "") or ""
    if not file_path.strip():
        return ""
    directory = file_path if "/" not in file_path and "\\" not in file_path else file_path.replace("\\", "/").rsplit("/", 1)[0]
    if not directory:
        directory = "."
    pattern = _glob_pattern_for_language(getattr(task, "language", "python"))
    try:
        result = await execute_tool(
            tool_registry,
            "list_project_files",
            {"directory": directory, "pattern": pattern, "max_results": 80},
        )
        if not result.success:
            return ""
        out = result.output or {}
        files = out.get("files") or []
        if not files:
            return ""
        return f"Files in target directory ({directory}, {pattern}): " + ", ".join(files[:50]) + (" ..." if len(files) > 50 else "")
    except Exception:
        return ""


async def _maybe_read_existing_file(file_path: str) -> str:
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

def _read_existing_repo_full_text(file_path: str, max_bytes: int = 400_000) -> str:
    if not file_path.strip():
        return ""
    root = REPO_ROOT.resolve()
    try:
        p = (root / file_path).resolve()
        if not str(p).startswith(str(root)):
            return ""
        if not p.is_file():
            return ""
        data = p.read_bytes()[:max_bytes]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


async def _build_short_term_memory(plan_id: str, limit: int | None = None) -> str:
    if http_client is None:
        return ""

    if limit is None:
        limit = short_term_memory_event_limit()

    try:
        resp = await guarded_http_get(
            http_client,
            "/events",
            logger,
            key="memory_service:/events",
            params={"plan_id": plan_id, "limit": limit},
        )
        if resp is None:
            return ""
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

        return build_short_term_memory_window(events, limit=limit)
    except Exception:
        logger.exception(
            "Error while building short-term memory for plan %s",
            plan_id[:8],
        )
        return ""


async def _build_failure_patterns_for_dev(file_path: str, limit: int = 200) -> str:
    if http_client is None or not file_path.strip():
        return ""
    try:
        norm = file_path.replace("\\", "/").strip()
        parts = norm.split("/")
        if len(parts) >= 3:
            module_prefix = "/".join(parts[:3])
        elif len(parts) >= 2:
            module_prefix = "/".join(parts[:2])
        else:
            module_prefix = norm

        resp = await http_client.get(
            "/patterns/failures",
            params={"limit": limit},
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        patterns = data.get("patterns") or []
        if not isinstance(patterns, list):
            return ""

        lines: list[str] = []
        for p in patterns:
            if not isinstance(p, dict):
                continue
            mod = str(p.get("module", "") or "").replace("\\", "/")
            if not mod.startswith(module_prefix):
                continue
            qa_n = int(p.get("qa_failed", 0) or 0)
            sec_n = int(p.get("security_blocked", 0) or 0)
            if not qa_n and not sec_n:
                continue
            pieces: list[str] = []
            if qa_n:
                pieces.append(f"QA_FAILED x{qa_n}")
            if sec_n:
                pieces.append(f"SECURITY_BLOCKED x{sec_n}")
            lines.append(f"- {mod}: " + ", ".join(pieces))

        if not lines:
            return ""

        header = (
            "HISTORICAL FAILURE PATTERNS NEAR THIS MODULE "
            f"(prefix '{module_prefix}', aggregated qa.failed/security.blocked):\n"
        )
        return header + "\n".join(lines[:5])
    except Exception:
        logger.exception(
            "Error while building failure patterns context for dev_service (file %s)",
            (file_path or "")[:40],
        )
        return ""

async def _fetch_task_spec(
    plan_id: str,
    task_id: str,
    *,
    wait_if_missing: bool = False,
    limit: int = 40,
) -> str:
    if http_client is None:
        return ""

    async def _once() -> str:
        try:
            resp = await http_client.get(
                "/events",
                params={
                    "plan_id": plan_id,
                    "event_type": EventType.SPEC_GENERATED.value,
                    "limit": limit,
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch spec events for plan %s (status=%s)",
                    plan_id[:8],
                    resp.status_code,
                )
                return ""
            events = resp.json()
            if not isinstance(events, list):
                return ""

            for ev in events:
                payload = ev.get("payload") or {}
                try:
                    spec_payload = SpecGeneratedPayload.model_validate(payload)
                except Exception:
                    continue
                if spec_payload.task_id == task_id:
                    parts: list[str] = []
                    if spec_payload.spec_text.strip():
                        parts.append(
                            f"SPEC FOR TASK {task_id[:8]}:\n"
                            + spec_payload.spec_text.strip()
                        )
                    if spec_payload.test_suggestions.strip():
                        parts.append(
                            "TEST SUGGESTIONS:\n"
                            + spec_payload.test_suggestions.strip()
                        )
                    return "\n\n".join(parts)
            return ""
        except Exception:
            logger.exception(
                "Error while fetching spec for task %s (plan %s)",
                task_id[:8],
                plan_id[:8],
            )
            return ""

    interval = cfg.spec_wait_interval_seconds if cfg else 0.2
    max_wait = 0.0
    if cfg and wait_if_missing and cfg.spec_wait_max_seconds > 0:
        max_wait = float(cfg.spec_wait_max_seconds)
    deadline = time.monotonic() + max_wait

    while True:
        out = await _once()
        if out.strip():
            return out
        if max_wait <= 0 or time.monotonic() >= deadline:
            return ""
        await asyncio.sleep(interval)


def _build_dev_context(
    short_term_memory: str,
    existing_file_preview: str,
    files_in_dir: str,
    spec_block: str = "",
    failure_patterns_block: str = "",
    repo_style_hints: str = "",
    *,
    spec_max_chars: int = 3000,
    max_chars: int = 5600,
) -> str:
    blocks: list[str] = []

    spec = (spec_block or "").strip()
    if spec:
        cap = max(400, spec_max_chars)
        blocks.append("TASK SPEC & TESTS:\n" + spec[:cap])

    style = (repo_style_hints or "").strip()
    if style:
        blocks.append("REPO STYLE & LINTER CONFIG (truncated):\n" + style[:520])

    stm = (short_term_memory or "").strip()
    if stm:
        blocks.append("RECENT EVENTS:\n" + stm[:1400])

    preview = (existing_file_preview or "").strip()
    if preview:
        blocks.append("EXISTING FILE PREVIEW:\n" + preview[:700])

    listing = (files_in_dir or "").strip()
    if listing:
        blocks.append("FILES IN DIRECTORY:\n" + listing[:300])

    fp_block = (failure_patterns_block or "").strip()
    if fp_block:
        blocks.append("HISTORICAL FAILURE PATTERNS:\n" + fp_block[:600])

    combined = "\n\n".join(blocks)
    if len(combined) > max_chars:
        combined = combined[:max_chars]
    return combined or "None."


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
