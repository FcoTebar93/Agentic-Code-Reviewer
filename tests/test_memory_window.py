from __future__ import annotations

from shared.contracts.events import EventType
from shared.utils.memory_window import (
    build_short_term_memory_window,
    short_term_memory_event_limit,
)


def test_quality_rollout_counts_qa_by_file() -> None:
    events = [
        {
            "event_type": EventType.QA_FAILED.value,
            "producer": "qa",
            "created_at": "t1",
            "payload": {
                "file_path": "a.py",
                "reasoning": "bad",
                "severity_hint": "high",
            },
        },
        {
            "event_type": EventType.QA_FAILED.value,
            "producer": "qa",
            "created_at": "t2",
            "payload": {"file_path": "a.py", "reasoning": "still bad"},
        },
        {
            "event_type": EventType.QA_PASSED.value,
            "producer": "qa",
            "created_at": "t3",
            "payload": {"file_path": "b.py", "reasoning": "ok"},
        },
    ]
    out = build_short_term_memory_window(events, limit=10)
    assert "QUALITY PATTERNS" in out
    assert "a.py x2" in out
    assert "max_sev=high" in out
    assert "b.py x1" in out


def test_spec_generated_line_includes_spec_snippet() -> None:
    events = [
        {
            "event_type": EventType.SPEC_GENERATED.value,
            "producer": "spec",
            "created_at": "t0",
            "payload": {
                "file_path": "x.py",
                "spec_text": "Must validate input.\nMore",
            },
        },
    ]
    out = build_short_term_memory_window(events, limit=5)
    assert "Must validate input." in out


def test_short_term_memory_event_limit_clamped(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_SHORT_TERM_MEMORY_EVENTS", "3")
    assert short_term_memory_event_limit() == 5
    monkeypatch.setenv("AGENT_SHORT_TERM_MEMORY_EVENTS", "200")
    assert short_term_memory_event_limit() == 100
