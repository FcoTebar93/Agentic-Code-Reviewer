import logging
import time
from typing import Any

from shared.utils.event_consumer import maybe_agent_delay, subscribe_typed_event
from shared.utils.memory_window import (
    build_short_term_memory_window,
    short_term_memory_event_limit,
)
from shared.utils.rabbitmq import EventBus, IdempotencyStore
from shared.utils.repo_style_hints import build_repo_style_hints

__all__ = [
    "EventBus",
    "IdempotencyStore",
    "build_short_term_memory_window",
    "short_term_memory_event_limit",
    "build_repo_style_hints",
    "maybe_agent_delay",
    "subscribe_typed_event",
    "publish_and_store",
    "store_event",
    "infer_framework_hint",
    "guarded_http_get",
]


async def store_event(
    http_client,
    event,
    logger: logging.Logger | None = None,
    error_message: str | None = None,
) -> None:
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


async def publish_and_store(
    event_bus,
    http_client,
    event,
    *,
    logger: logging.Logger | None = None,
    error_message: str = "Failed to store event %s",
) -> None:
    await event_bus.publish(event)
    await store_event(
        http_client,
        event,
        logger=logger,
        error_message=error_message,
    )


def infer_framework_hint(language: str, file_path: str | None) -> str:
    """
    Small heuristic to infer the likely framework for a given file.

    It is intentionally conservative: it returns a short human-readable hint
    (in Spanish) that can be prepended to prompts, but it never blocks logic.
    """
    lang = (language or "").lower()
    fp = (file_path or "").replace("\\", "/")
    name = fp.rsplit("/", 1)[-1]
    lower_fp = fp.lower()

    if lang == "python":
        if "fastapi" in lower_fp or "/api/" in lower_fp or name.startswith("router_"):
            return "Posible stack FastAPI / API HTTP en Python."
        if "django" in lower_fp or "views.py" in name or "urls.py" in name:
            return "Posible stack Django (vistas/URLs de una aplicación web)."

    if lang in {"javascript", "js", "typescript", "ts"}:
        if "next" in lower_fp or "/pages/" in lower_fp or "/app/" in lower_fp:
            return "Posible stack Next.js (rutas/app de React)."
        if "components" in lower_fp or name.endswith((".tsx", ".jsx")):
            return "Posible componente React / UI (JS/TS)."

    if lang == "java":
        if "controller" in name.lower() or "resource" in name.lower():
            return "Posible controlador HTTP en una API Java (Spring o similar)."

    return ""


_CB_STATE: dict[str, dict[str, Any]] = {}
_CB_MAX_ERRORS = 3
_CB_OPEN_SECONDS = 30.0


async def guarded_http_get(http_client, path: str, logger: logging.Logger | None, *, key: str, **kwargs):
    """
    Small in-process circuit breaker wrapper around http_client.get.

    - key: logical target, e.g. "memory_service:/events"
    - On repeated failures, opens the circuit for a short cool-down period
      and returns None immediately instead of hitting the remote service.
    """
    if http_client is None:
        return None

    now = time.monotonic()
    state = _CB_STATE.get(key) or {"errors": 0, "open_until": 0.0}

    if state["open_until"] > now:
        if logger:
            logger.warning(
                "Circuit breaker OPEN for %s (skipping GET %s)", key, path
            )
        return None

    try:
        resp = await http_client.get(path, **kwargs)
        state["errors"] = 0
        state["open_until"] = 0.0
        _CB_STATE[key] = state
        return resp
    except Exception:
        state["errors"] = int(state.get("errors", 0)) + 1
        if state["errors"] >= _CB_MAX_ERRORS:
            state["open_until"] = now + _CB_OPEN_SECONDS
            if logger:
                logger.warning(
                    "Circuit breaker OPEN for %s after %d error(s)", key, state["errors"]
                )
        _CB_STATE[key] = state
        if logger:
            logger.exception("guarded_http_get failed for %s", key)
        return None
