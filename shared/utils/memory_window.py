from __future__ import annotations

from typing import Any

from shared.contracts.events import EventType


def build_short_term_memory_window(
    events: list[dict[str, Any]],
    limit: int = 15,
    max_chars: int = 2000,
) -> str:
    """
    Build a compact textual window from a list of events.

    Used by dev_service and qa_service to summarise recent activity for a plan.
    """
    if not events:
        return ""

    lines: list[str] = []
    for evt in events[:limit]:
        etype = evt.get("event_type", "")
        producer = evt.get("producer", "")
        created_at = evt.get("created_at", "")
        payload = evt.get("payload") or {}

        summary = ""
        if etype == EventType.PLAN_CREATED.value:
            summary = str(payload.get("reasoning", ""))[:200]
        elif etype == EventType.CODE_GENERATED.value:
            summary = f"{payload.get('file_path', '')}"
        elif etype in (
            EventType.QA_PASSED.value,
            EventType.QA_FAILED.value,
            EventType.SECURITY_APPROVED.value,
            EventType.SECURITY_BLOCKED.value,
        ):
            summary = str(payload.get("reasoning", ""))[:200]

        line = f"[{etype}] from {producer} at {created_at}"
        if summary:
            line += f" :: {summary}"
        lines.append(line)

    window = "\n".join(lines)
    if len(window) > max_chars:
        window = window[:max_chars]
    return window

