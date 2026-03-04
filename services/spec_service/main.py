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
from shared.utils import EventBus, IdempotencyStore, store_event
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

    with agent_execution_time.labels(service=SERVICE_NAME, operation="spec_gen").time():
        llm = get_llm_provider(
            provider_name=cfg.llm_provider,
            redis_url=cfg.redis_url,
        )
        spec_result, prompt_tokens, completion_tokens = await _generate_spec(
            llm=llm,
            description=task.description,
            file_path=task.file_path,
            language=task.language,
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
) -> tuple[dict[str, str], int, int]:
    """
    Call the LLM once to produce SPEC and TESTS sections.
    Returns ({spec: str, tests: str}, prompt_tokens, completion_tokens).
    """
    prompt = SPEC_PROMPT.format(
        language=language or "python",
        description=description,
        file_path=file_path,
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

