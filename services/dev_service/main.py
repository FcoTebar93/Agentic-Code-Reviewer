"""
Dev Service -- the AI developer agent.

Phase 2 change: dev_service no longer publishes pr.requested.
PR creation is now triggered by qa_service after all tasks pass review.
This service only generates code and publishes code.generated.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response, agent_execution_time, tasks_completed, llm_tokens
from shared.contracts.events import (
    BaseEvent,
    EventType,
    TaskAssignedPayload,
    CodeGeneratedPayload,
    TokensUsedPayload,
    code_generated,
    metrics_tokens_used,
)
from shared.llm_adapter import get_llm_provider
from shared.utils import (
    EventBus,
    IdempotencyStore,
    build_short_term_memory_window,
    store_event,
    guarded_http_get,
)
from services.dev_service.config import DevConfig
from services.dev_service.generator import generate_code
from services.dev_service.tools import build_dev_tool_registry, ReadFileInput
from shared.tools import execute_tool, ToolRegistry
from shared.contracts.events import EventType, SpecGeneratedPayload

SERVICE_NAME = "dev_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: DevConfig | None = None
tool_registry: ToolRegistry | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg, tool_registry
    logger = setup_logging(SERVICE_NAME)

    cfg = DevConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=30.0)

    tool_registry = build_dev_tool_registry()

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_tasks())
    logger.info("Dev Service ready")
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Dev Service",
    version="0.2.0",
    description="Generates code via LLM based on task specifications",
    lifespan=lifespan,
)
logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

async def _consume_tasks() -> None:
    idem_store = IdempotencyStore(
        redis_url=cfg.redis_url if hasattr(cfg, "redis_url") else None
    )

    async def handler(event: BaseEvent) -> None:
        delay_sec = int(os.environ.get("AGENT_DELAY_SECONDS", "0"))
        if delay_sec > 0:
            logger.info("Agent delay: waiting %ds before processing", delay_sec)
            await asyncio.sleep(delay_sec)
        payload = TaskAssignedPayload.model_validate(event.payload)
        await _handle_task(payload)

    await event_bus.subscribe(
        queue_name="dev_service.tasks",
        routing_keys=[EventType.TASK_ASSIGNED.value],
        handler=handler,
        idempotency_store=idem_store,
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
        f" (QA feedback present)" if qa_feedback else "",
    )

    raw_mode = getattr(payload, "mode", "normal") or "normal"
    mode = str(raw_mode).strip().lower()

    with agent_execution_time.labels(service=SERVICE_NAME, operation="code_gen").time():
        await _update_task_state(task.task_id, plan_id, "in_progress")

        llm = get_llm_provider(provider_name=cfg.llm_provider, redis_url=cfg.redis_url)
        short_term_memory = await _build_short_term_memory(plan_id)
        existing_file_preview = await _maybe_read_existing_file(task.file_path)
        files_in_dir = await _list_files_in_task_directory(task)
        spec_block = await _fetch_task_spec(plan_id, task.task_id)
        dev_context = _build_dev_context(
            short_term_memory=short_term_memory,
            existing_file_preview=existing_file_preview,
            files_in_dir=files_in_dir,
            spec_block=spec_block,
        )
        code_result, prompt_tokens, completion_tokens = await generate_code(
            llm,
            task,
            plan_reasoning=payload.plan_reasoning,
            short_term_memory=dev_context,
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
                error_message="Failed to store event %s",
            )

        current_attempt = 0
        try:
            resp = await http_client.get(f"/tasks/{plan_id}")
            if resp.status_code == 200:
                tasks = resp.json()
                for t in tasks:
                    if t["task_id"] == task.task_id:
                        current_attempt = t.get("qa_attempt", 0)
                        break
        except Exception:
            pass

        tests_summary = await _maybe_run_auto_tests(task, mode)
        lints_summary = await _maybe_run_auto_lints(task, qa_feedback, mode)

        combined_reasoning = code_result.reasoning
        if tests_summary:
            suffix = f"\n[Dev Service] Automated tests summary: {tests_summary}"
            combined_reasoning = (combined_reasoning + suffix).strip()
        if lints_summary:
            suffix = f"\n[Dev Service] Automated lints summary: {lints_summary}"
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

        cg_payload = CodeGeneratedPayload(
            plan_id=plan_id,
            task_id=task.task_id,
            file_path=task.file_path,
            code=formatted_code,
            language=task.language,
            qa_attempt=current_attempt,
            reasoning=combined_reasoning,
            mode=raw_mode,
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
    """
    Apply defensive idempotency rules before processing a task.

    Returns True if the task should be skipped, False otherwise.
    """
    has_feedback = bool((qa_feedback or "").strip())
    try:
        resp_tasks = await http_client.get(f"/tasks/{plan_id}")
        if resp_tasks.status_code == 200:
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
            resp_events = await http_client.get(
                "/events",
                params={
                    "plan_id": plan_id,
                    "event_type": EventType.CODE_GENERATED.value,
                    "limit": 100,
                },
            )
            if resp_events.status_code == 200:
                events = resp_events.json() if isinstance(resp_events.json(), list) else []
                for ev in events:
                    ev_payload = ev.get("payload") or {}
                    if ev_payload.get("task_id") == task.task_id:
                        logger.info(
                            "Task %s already has code.generated event, skipping (idempotent)",
                            task.task_id[:8],
                        )
                        return True
    except Exception:
        logger.warning("Idempotency pre-check failed for task %s", task.task_id[:8])
    return False


async def _maybe_run_auto_tests(task, mode: str) -> str:
    """
    Optionally run configured automated tests for the task's language.

    Returns a short human-readable summary, or an empty string if tests
    are disabled or fail in a non-critical way.
    """
    try:
        normalized_mode = (mode or "normal").strip().lower()
        test_cmd = ""
        lang = (task.language or "").lower()
        if cfg and cfg.enable_auto_tests and tool_registry is not None:
            if lang == "python":
                test_cmd = cfg.test_command_python
            elif lang in ("javascript", "js"):
                test_cmd = cfg.test_command_javascript
            elif lang in ("typescript", "ts"):
                test_cmd = cfg.test_command_typescript
            elif lang == "java":
                test_cmd = cfg.test_command_java

        if not test_cmd:
            return ""

        tests_result = await execute_tool(
            tool_registry,
            "run_tests",
            {"command": test_cmd, "timeout_s": 300.0},
        )
        if tests_result.success and isinstance(tests_result.output, dict):
            tr = tests_result.output
            status = (
                "PASSED"
                if tr.get("exit_code") == 0 and not tr.get("timed_out")
                else "FAILED"
            )
            return (
                f"Automated tests ({tr.get('command')}): {status}. "
                f"exit_code={tr.get('exit_code')}, timed_out={tr.get('timed_out')}."
            )
        if not tests_result.success:
            return f"Automated tests failed to run: {tests_result.error}"
    except Exception:
        return ""
    return ""


async def _maybe_run_auto_lints(task, qa_feedback: str, mode: str) -> str:
    """
    Optionally run configured automated linters for the task's language.

    Estrategia:
    - Solo corre si DEV_ENABLE_AUTO_LINTS está activo.
    - Se da más prioridad cuando hay qa_feedback (reintento tras QA).
    - Usa el tool run_lints con un comando apropiado por lenguaje.
    """
    try:
        if not cfg or not getattr(cfg, "enable_auto_lints", False):
            return ""
        if tool_registry is None:
            return ""

        lang = (getattr(task, "language", "") or "").lower()
        edit_scope = str(getattr(task, "edit_scope", "file") or "").lower()
        normalized_mode = (mode or "normal").strip().lower()

        lint_cmd = ""
        if lang in ("python", "py"):
            lint_cmd = os.environ.get("DEV_LINT_COMMAND_PYTHON", "ruff .")
        elif lang in ("javascript", "js"):
            lint_cmd = os.environ.get("DEV_LINT_COMMAND_JAVASCRIPT", "npm run lint")
        elif lang in ("typescript", "ts"):
            lint_cmd = os.environ.get("DEV_LINT_COMMAND_TYPESCRIPT", "npm run lint")
        elif lang == "java":
            lint_cmd = os.environ.get("DEV_LINT_COMMAND_JAVA", "")

        if not lint_cmd:
            return ""

        has_feedback = bool((qa_feedback or "").strip())
        if normalized_mode != "strict" and not has_feedback and edit_scope == "file":
            return ""

        lints_result = await execute_tool(
            tool_registry,
            "run_lints",
            {"command": lint_cmd, "timeout_s": 300.0},
        )
        if lints_result.success and isinstance(lints_result.output, dict):
            lr = lints_result.output
            status = (
                "PASSED"
                if lr.get("exit_code") == 0 and not lr.get("timed_out")
                else "FAILED"
            )
            return (
                f"Lints ({lr.get('command')}): {status}. "
                f"exit_code={lr.get('exit_code')}, timed_out={lr.get('timed_out')}."
            )
        if not lints_result.success:
            return f"Lints failed to run: {lints_result.error}"
    except Exception:
        return ""
    return ""

def _glob_pattern_for_language(language: str) -> str:
    """Patr?n glob por lenguaje para list_project_files."""
    lang = (language or "python").lower()
    if lang in ("python", "py"):
        return "*.py"
    if lang in ("javascript", "js"):
        return "*.js"
    if lang in ("typescript", "ts"):
        return "*.ts"
    if lang == "java":
        return "*.java"
    return "*"


async def _list_files_in_task_directory(task) -> str:
    """
    Usa el tool list_project_files para listar archivos del directorio de la tarea,
    as? el generador conoce qu? archivos existen (imports, consistencia).
    """
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
    """
    Best-effort helper: usa el tool read_file para recuperar un peque?o
    preview del archivo objetivo, si ya existe en el repo.
    """
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

async def _build_short_term_memory(plan_id: str, limit: int = 15) -> str:
    """
    Build a compact short-term memory window for a given plan_id by querying
    recent events from the memory_service.
    """
    if http_client is None:
        return ""

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


async def _fetch_task_spec(plan_id: str, task_id: str, limit: int = 20) -> str:
    """
    Fetch spec/tests for a given task from memory_service (spec.generated events).

    This keeps the dev prompt informed without requiring direct coupling to
    spec_service internals.
    """
    if http_client is None:
        return ""

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
                        f"SPEC FOR TASK {task_id[:8]}:\n{spec_payload.spec_text.strip()}"
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


def _build_dev_context(
    short_term_memory: str,
    existing_file_preview: str,
    files_in_dir: str,
    spec_block: str = "",
    max_chars: int = 2500,
) -> str:
    """
    Construye un contexto compacto y estructurado para el LLM del dev_service.

    - Da prioridad a los eventos recientes (short_term_memory).
    - Añade un pequeño preview del archivo objetivo si existe.
    - Añade un resumen de archivos del directorio de trabajo.
    - Recorta el resultado total para mantener bajo el uso de tokens.
    """
    blocks: list[str] = []

    spec = (spec_block or "").strip()
    if spec:
        blocks.append("TASK SPEC & TESTS:\n" + spec[:700])

    stm = (short_term_memory or "").strip()
    if stm:
        blocks.append("RECENT EVENTS:\n" + stm[:1400])

    preview = (existing_file_preview or "").strip()
    if preview:
        blocks.append("EXISTING FILE PREVIEW:\n" + preview[:700])

    listing = (files_in_dir or "").strip()
    if listing:
        blocks.append("FILES IN DIRECTORY:\n" + listing[:300])

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
