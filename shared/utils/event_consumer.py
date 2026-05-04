from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar

from shared.contracts.events import BaseEvent
from shared.utils.rabbitmq import EventBus, IdempotencyStore

PayloadT = TypeVar("PayloadT")


class _PayloadModel(Protocol[PayloadT]):  # type: ignore[misc]
    @classmethod
    def model_validate(cls, value: Any) -> PayloadT: ...


async def maybe_agent_delay(
    logger: Any, env_key: str = "AGENT_DELAY_SECONDS"
) -> None:
    """
    Small shared delay hook used by event consumers.
    """
    delay_sec = int(os.environ.get(env_key, "0") or 0)
    if delay_sec <= 0:
        return
    logger.info("Agent delay: waiting %ds before processing", delay_sec)
    await asyncio.sleep(delay_sec)


async def subscribe_typed_event(
    *,
    event_bus: EventBus,
    queue_name: str,
    routing_keys: list[str],
    payload_model: _PayloadModel[PayloadT],
    on_payload: Callable[[PayloadT], Awaitable[None]],
    redis_url: str | None = None,
    idempotency_store: IdempotencyStore | None = None,
    max_retries: int = 3,
) -> None:
    """
    Subscribe to one event route and dispatch a validated payload.
    """
    idem_store = idempotency_store or IdempotencyStore(redis_url=redis_url)

    async def handler(event: BaseEvent) -> None:
        payload = payload_model.model_validate(event.payload)
        await on_payload(payload)

    await event_bus.subscribe(
        queue_name=queue_name,
        routing_keys=routing_keys,
        handler=handler,
        idempotency_store=idem_store,
        max_retries=max_retries,
    )
