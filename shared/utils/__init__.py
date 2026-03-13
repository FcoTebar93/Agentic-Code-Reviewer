import logging

from shared.utils.rabbitmq import EventBus
from shared.utils.memory_window import build_short_term_memory_window

__all__ = [
    "EventBus",
    "build_short_term_memory_window",
    "store_event",
    "infer_framework_hint",
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
