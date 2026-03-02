import logging

from shared.utils.rabbitmq import EventBus
from shared.utils.memory_window import build_short_term_memory_window

__all__ = ["EventBus", "build_short_term_memory_window", "store_event"]


async def store_event(http_client, event, logger: logging.Logger | None = None, error_message: str | None = None) -> None:
    """
    Persist an event to memory_service via the given HTTP client.

    Small shared helper used by multiple services (dev, qa, meta_planner, etc.).
    """
    if http_client is None:
        return
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
        if logger is not None:
            if not error_message:
                error_message = "Failed to store event %s"
            event_id = getattr(event, "event_id", "")
            short_id = event_id[:8] if isinstance(event_id, str) else event_id
            logger.exception(error_message, short_id)
