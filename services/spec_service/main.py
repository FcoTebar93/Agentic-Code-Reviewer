from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response, agent_execution_time, llm_tokens
from shared.contracts.events import (
    BaseEvent,
    EventType,
    TaskAssignedPayload,
    SpecGeneratedPayload,
    TokensUsedPayload,
    spec_generated,
    metrics_tokens_used,
)
from shared.llm_adapter import get_llm_provider, LLMProvider, LLMResponse
from shared.utils import (
    EventBus,
    IdempotencyStore,
    store_event,
    infer_framework_hint,
    guarded_http_get,
)
from services.spec_service.config import SpecConfig
from services.spec_service.prompts import SPEC_PROMPT


SERVICE_NAME = "spec_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: SpecConfig | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = SpecConfig.from_env()
    http_client = httpx.AsyncClient(base_url=cfg.memory_service_url, timeout=30.0)

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_tasks())
    logger.info("Spec Service ready (strategy=%s)", cfg.strategy)
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Spec Service",
    version="0.1.0",
    description="Generates task specifications and test suggestions before dev_service runs",
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
    """
    Listen for task.assigned events and generate a spec/tests helper for each task.
    """
    idem_store = IdempotencyStore()

    async def handler(event: BaseEvent) -> None:
        payload = TaskAssignedPayload.model_validate(event.payload)
        await _handle_task(payload)

    await event_bus.subscribe(
        queue_name="spec_service.tasks",
        routing_keys=[EventType.TASK_ASSIGNED.value],
        handler=handler,
        idempotency_store=idem_store,
        max_retries=3,
    )


async def _handle_task(payload: TaskAssignedPayload) -> None:
    """
    Generate spec and test suggestions for a single task.
    """
    if cfg is None:
        return

    task = payload.task
    plan_id = payload.plan_id
    mode = getattr(payload, "mode", "normal") or "normal"

    logger.info(
        "Generating spec for task %s (plan %s, mode=%s, file=%s)",
        task.task_id[:8],
        plan_id[:8],
        mode,
        task.file_path,
    )

    if await _has_existing_spec(plan_id, task.task_id):
        logger.info(
            "Spec already exists for task %s (plan %s), skipping regeneration",
            task.task_id[:8],
            plan_id[:8],
        )
        return

    normalized_mode = (mode or "normal").strip().lower()
    if normalized_mode in {"save", "ahorro"} and len((task.description or "").strip()) < 60:
        logger.info(
            "Skipping spec generation for simple task %s (plan %s) in save mode",
            task.task_id[:8],
            plan_id[:8],
        )
        return

    try:
        with agent_execution_time.labels(service=SERVICE_NAME, operation="spec_gen").time():
            llm = get_llm_provider(
                provider_name=cfg.llm_provider,
                redis_url=cfg.redis_url,
            )
            plan_context = await _build_plan_context(plan_id, task.task_id, task.file_path)
            test_layout = _infer_test_layout(task.file_path, task.language)
            spec_result, prompt_tokens, completion_tokens = await _generate_spec(
                llm=llm,
                description=task.description,
                file_path=task.file_path,
                language=task.language,
                plan_context=plan_context,
                test_layout=test_layout,
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
                    error_message="Failed to store spec_service metrics event %s",
                )
    except Exception:
        logger.exception(
            "Spec Service failed while generating spec for task %s (plan %s). "
            "Continuing pipeline without spec/tests suggestions.",
            task.task_id[:8],
            plan_id[:8],
        )
        return

    spec_payload = SpecGeneratedPayload(
        plan_id=plan_id,
        task_id=task.task_id,
        file_path=task.file_path,
        language=task.language,
        spec_text=spec_result["spec"],
        test_suggestions=spec_result["tests"],
    )
    event = spec_generated(SERVICE_NAME, spec_payload)
    await event_bus.publish(event)
    await store_event(
        http_client,
        event,
        logger=logger,
        error_message="Failed to store spec.generated event %s",
    )

    logger.info(
        "Spec generated for task %s (plan %s)", task.task_id[:8], plan_id[:8]
    )


async def _generate_spec(
    llm: LLMProvider,
    description: str,
    file_path: str,
    language: str,
    plan_context: str,
    test_layout: str,
) -> tuple[dict[str, str], int, int]:
    """
    Call the LLM once to produce SPEC and TESTS sections.
    Returns ({spec: str, tests: str}, prompt_tokens, completion_tokens).
    """
    fw_hint = infer_framework_hint(language, file_path)
    ctx_block = plan_context.strip()
    if fw_hint:
        prefix = f"FRAMEWORK HINT: {fw_hint}\n\n"
        ctx_block = prefix + (ctx_block or "")
    prompt = SPEC_PROMPT.format(
        language=language or "python",
        description=description,
        file_path=file_path,
        plan_context=ctx_block or "None.",
        test_layout=test_layout.strip() or "None.",
    )
    response: LLMResponse = await llm.generate_text(prompt)

    pt = response.prompt_tokens or 0
    ct = response.completion_tokens or 0
    if pt or ct:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)

    spec_text, tests_text = _parse_spec_response(response.content or "")
    return {"spec": spec_text, "tests": tests_text}, pt, ct


def _parse_spec_response(raw: str) -> tuple[str, str]:
    """
    Parse SPEC and TESTS sections from the LLM response.
    """
    spec_block = ""
    tests_block = ""

    current = None
    lines = raw.strip().splitlines()
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("SPEC:"):
            current = "spec"
            content = stripped[len("SPEC:") :].strip()
            if content:
                spec_block += content + "\n"
        elif upper.startswith("TESTS:"):
            current = "tests"
            content = stripped[len("TESTS:") :].strip()
            if content:
                tests_block += content + "\n"
        else:
            if current == "spec":
                spec_block += stripped + "\n"
            elif current == "tests":
                tests_block += stripped + "\n"

    return spec_block.strip(), tests_block.strip()


async def _build_plan_context(plan_id: str, task_id: str, file_path: str) -> str:
    """
    Build a small textual context for the spec agent:
    - Planner reasoning for this plan (if available).
    - Other tasks/files in the same plan.

    This avoids long histories while giving the LLM awareness of how this task
    fits into the overall plan.
    """
    if http_client is None:
        return ""

    try:
        resp = await guarded_http_get(
            http_client,
            "/events",
            logger,
            key="memory_service:/events",
            params={
                "event_type": "plan.created",
                "plan_id": plan_id,
                "limit": 1,
            },
        )
        if resp is None:
            return ""
        if resp.status_code != 200:
            return ""

        events = resp.json()
        if not isinstance(events, list) or not events:
            return ""

        evt = events[0]
        payload = evt.get("payload") or {}
        reasoning = str(payload.get("reasoning", "")).strip()[:400]
        tasks = payload.get("tasks") or []

        lines: list[str] = []
        if reasoning:
            lines.append("Planner reasoning (truncated):")
            lines.append(reasoning)
            lines.append("")

        if isinstance(tasks, list) and tasks:
            sibling_files: list[str] = []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                fp = str(t.get("file_path", "") or "")
                tid = str(t.get("task_id", "") or "")
                if not fp:
                    continue
                if tid == task_id:
                    continue
                sibling_files.append(fp)
            if sibling_files:
                lines.append("Other files in this plan:")
                for fp in sibling_files[:8]:
                    lines.append(f"- {fp}")
                lines.append("")

        spec_hist = await _build_spec_history_for_file(file_path)
        if spec_hist:
            lines.append("Previous specs and tests for this file (truncated):")
            lines.append(spec_hist)
            lines.append("")

        qa_hist = await _build_qa_history_for_file(file_path)
        if qa_hist:
            lines.append("Previous QA failures for this file (truncated):")
            lines.append(qa_hist)

        return "\n".join(lines)
    except Exception:
        logger.exception(
            "Failed to build plan context for spec_service (plan %s, task %s)",
            plan_id[:8],
            task_id[:8],
        )
        return ""


async def _has_existing_spec(plan_id: str, task_id: str, limit: int = 20) -> bool:
    """
    Comprueba en memory_service si ya existe un evento spec.generated para esta tarea.
    Evita gastar tokens del LLM repitiendo trabajo.
    """
    global http_client
    if http_client is None:
        return False
    try:
        resp = await guarded_http_get(
            http_client,
            "/events",
            logger,
            key="memory_service:/events",
            params={
                "plan_id": plan_id,
                "event_type": EventType.SPEC_GENERATED.value,
                "limit": limit,
            },
        )
        if resp is None:
            return False
        if resp.status_code != 200:
            return False
        events = resp.json()
        if not isinstance(events, list):
            return False
        for ev in events:
            payload = ev.get("payload") or {}
            if str(payload.get("task_id", "")) == task_id:
                return True
        return False
    except Exception:
        logger.exception(
            "Error while checking existing spec for task %s (plan %s)",
            task_id[:8],
            plan_id[:8],
        )
        return False


def _infer_test_layout(file_path: str, language: str) -> str:
    """
    Heurística ligera para sugerir rutas y convenciones de tests según el lenguaje
    y el path del archivo, sin inspeccionar el repo.
    """
    lang = (language or "").lower()
    fp = (file_path or "").replace("\\", "/")
    name = fp.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name

    hints: list[str] = []

    if lang in {"python", "py"}:
        hints.append(
            f"Python: tests/test_{stem}.py (pytest) o tests/{stem}/test_{stem}.py"
        )
    elif lang in {"javascript", "js", "typescript", "ts"}:
        hints.append(
            f"JS/TS: __tests__/{stem}.spec.ts(x) o tests/{stem}.test.ts(x) (Jest/Vitest)"
        )
    elif lang == "java":
        hints.append(
            "Java: src/test/java/.../<ClassName>Test.java siguiendo el paquete de src/main/java"
        )
    else:
        hints.append(
            "Sin convenciones específicas detectadas; usar el directorio de tests estándar del proyecto."
        )

    return "\n".join(f"- {h}" for h in hints)


async def _build_spec_history_for_file(file_path: str, limit: int = 20) -> str:
    """
    Recupera algunas specs/tests anteriores para el mismo archivo (cualquier plan),
    truncadas para servir como referencia ligera.
    """
    if http_client is None or not file_path.strip():
        return ""
    try:
        resp = await guarded_http_get(
            http_client,
            "/events",
            logger,
            key="memory_service:/events",
            params={
                "event_type": EventType.SPEC_GENERATED.value,
                "limit": limit,
            },
        )
        if resp is None:
            return ""
        if resp.status_code != 200:
            return ""
        events = resp.json()
        if not isinstance(events, list):
            return ""
        lines: list[str] = []
        for ev in events:
            payload = ev.get("payload") or {}
            if str(payload.get("file_path", "") or "") != file_path:
                continue
            spec_text = str(payload.get("spec_text", "") or "")[:200].strip()
            tests = str(payload.get("test_suggestions", "") or "")[:200].strip()
            if spec_text:
                lines.append(f"- SPEC: {spec_text}")
            if tests:
                lines.append(f"  TESTS: {tests}")
            if len(lines) >= 4:
                break
        return "\n".join(lines)
    except Exception:
        logger.exception(
            "Failed to build spec history context for file %s",
            (file_path or "")[:40],
        )
        return ""


async def _build_qa_history_for_file(file_path: str, limit: int = 20) -> str:
    """
    Recupera algunos fallos de QA anteriores para el mismo archivo, para que el
    spec agent pueda reforzar esos casos en los tests sugeridos.
    """
    if http_client is None or not file_path.strip():
        return ""
    try:
        resp = await guarded_http_get(
            http_client,
            "/events",
            logger,
            key="memory_service:/events",
            params={
                "event_type": EventType.QA_FAILED.value,
                "limit": limit,
            },
        )
        if resp is None:
            return ""
        if resp.status_code != 200:
            return ""
        events = resp.json()
        if not isinstance(events, list):
            return ""
        lines: list[str] = []
        for ev in events:
            payload = ev.get("payload") or {}
            if str(payload.get("file_path", "") or "") != file_path:
                continue
            issues = payload.get("issues") or []
            if isinstance(issues, list):
                for issue in issues:
                    if isinstance(issue, str) and issue.strip():
                        lines.append(f"- {issue.strip()[:200]}")
                    if len(lines) >= 4:
                        break
            if len(lines) >= 4:
                break
        return "\n".join(lines)
    except Exception:
        logger.exception(
            "Failed to build QA history context for file %s",
            (file_path or "")[:40],
        )
        return ""

