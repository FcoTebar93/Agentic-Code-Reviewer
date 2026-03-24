from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from shared.contracts.events import EventType

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def short_term_memory_event_limit() -> int:
    """Max events to pull for plan-scoped memory (dev + QA). Bounded for token safety."""
    try:
        n = int(os.environ.get("AGENT_SHORT_TERM_MEMORY_EVENTS", "20"))
    except ValueError:
        n = 20
    return max(5, min(n, 100))


def _quality_pattern_rollout(events: list[dict[str, Any]]) -> str:
    """
    Aggregate QA/security/spec signals across the whole fetched window (not only the tail).
    Helps downstream agents spot retry loops and hotspots without reading every line.
    """
    qa_fail: dict[str, int] = defaultdict(int)
    qa_pass: dict[str, int] = defaultdict(int)
    qa_fail_sev: dict[str, str] = {}
    sec_blocked = 0
    sec_ok = 0
    spec_files: list[str] = []
    pipeline_note = ""

    for evt in events:
        etype = evt.get("event_type", "")
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        if etype == EventType.QA_FAILED.value:
            fp = str(payload.get("file_path", "") or "").strip()
            if fp:
                qa_fail[fp] += 1
                sev = str(payload.get("severity_hint", "") or "").strip().lower()
                if sev in _SEVERITY_RANK:
                    r_new = _SEVERITY_RANK[sev]
                    r_old = _SEVERITY_RANK.get(qa_fail_sev.get(fp, ""), -1)
                    if r_new >= r_old:
                        qa_fail_sev[fp] = sev
        elif etype == EventType.QA_PASSED.value:
            fp = str(payload.get("file_path", "") or "").strip()
            if fp:
                qa_pass[fp] += 1
        elif etype == EventType.SECURITY_BLOCKED.value:
            sec_blocked += 1
        elif etype == EventType.SECURITY_APPROVED.value:
            sec_ok += 1
        elif etype == EventType.SPEC_GENERATED.value:
            fp = str(payload.get("file_path", "") or "").strip()
            if fp and fp not in spec_files:
                spec_files.append(fp)
        elif etype == EventType.PIPELINE_CONCLUSION.value:
            for key in ("summary", "outcome", "status"):
                v = str(payload.get(key, "") or "").strip()
                if v:
                    pipeline_note = v[:160]
                    break

    chunks: list[str] = []
    if qa_fail:
        parts: list[str] = []
        for fp, c in sorted(qa_fail.items(), key=lambda x: (-x[1], x[0]))[:6]:
            sev = qa_fail_sev.get(fp, "")
            parts.append(f"{fp} x{c}" + (f" (max_sev={sev})" if sev else ""))
        chunks.append("QA_FAIL by file: " + "; ".join(parts))
    if qa_pass:
        parts = [
            f"{fp} x{c}"
            for fp, c in sorted(qa_pass.items(), key=lambda x: (-x[1], x[0]))[:6]
        ]
        chunks.append("QA_PASS by file: " + "; ".join(parts))
    if sec_blocked or sec_ok:
        chunks.append(f"Security scans in window: blocked={sec_blocked}, approved={sec_ok}")
    if spec_files:
        chunks.append("Spec generated for: " + ", ".join(spec_files[:10]))
    if pipeline_note:
        chunks.append("Pipeline (latest): " + pipeline_note)

    return "\n".join(chunks)


def build_short_term_memory_window(
    events: list[dict[str, Any]],
    limit: int = 15,
    max_chars: int = 2400,
) -> str:
    """
    Build a compact textual window from a list of events.

    Used by dev_service and qa_service to summarise recent activity for a plan.
    """
    if not events:
        return ""

    rollout = _quality_pattern_rollout(events)
    lines: list[str] = []
    if rollout:
        lines.append("QUALITY PATTERNS (aggregated in this window):")
        lines.append(rollout)

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
        elif etype == EventType.SPEC_GENERATED.value:
            fp = str(payload.get("file_path", "") or "")
            st = str(payload.get("spec_text", "") or "").strip().split("\n", 1)[0][:140]
            summary = f"{fp}" + (f" :: {st}" if st else "")
        elif etype in (
            EventType.QA_PASSED.value,
            EventType.QA_FAILED.value,
            EventType.SECURITY_APPROVED.value,
            EventType.SECURITY_BLOCKED.value,
        ):
            summary = str(payload.get("reasoning", ""))[:200]
        elif etype == EventType.TASK_ASSIGNED.value:
            task = payload.get("task")
            fp = ""
            if isinstance(task, dict):
                fp = str(task.get("file_path", "") or "")
            summary = fp[:200]

        line = f"[{etype}] from {producer} at {created_at}"
        if summary:
            line += f" :: {summary}"
        lines.append(line)

    window = "\n".join(lines)
    if len(window) > max_chars:
        window = window[:max_chars]
    return window

