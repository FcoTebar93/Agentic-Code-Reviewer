from __future__ import annotations

import logging
from typing import Any

from shared.utils.rabbitmq import EventBus


async def connect_event_bus(rabbitmq_url: str) -> EventBus:
    """Create and connect an EventBus instance."""
    event_bus = EventBus(rabbitmq_url)
    await event_bus.connect()
    return event_bus


async def shutdown_runtime(
    *,
    logger: logging.Logger,
    event_bus: EventBus | None = None,
    http_client: Any = None,
) -> None:
    """Close EventBus and HTTP client in standard service shutdown order."""
    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()
