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


def test_short_term_memory_event_limit_invalid_env_defaults(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_SHORT_TERM_MEMORY_EVENTS", "not-a-number")
    assert short_term_memory_event_limit() == 20


def test_quality_rollout_security_counters() -> None:
    events = [
        {
            "event_type": EventType.SECURITY_BLOCKED.value,
            "producer": "sec",
            "created_at": "t1",
            "payload": {},
        },
        {
            "event_type": EventType.SECURITY_APPROVED.value,
            "producer": "sec",
            "created_at": "t2",
            "payload": {},
        },
    ]
    out = build_short_term_memory_window(events, limit=5)
    assert "blocked=1, approved=1" in out


def test_quality_rollout_pipeline_conclusion_summary() -> None:
    events = [
        {
            "event_type": EventType.PIPELINE_CONCLUSION.value,
            "producer": "gw",
            "created_at": "t1",
            "payload": {"summary": "Merged and verified"},
        },
    ]
    out = build_short_term_memory_window(events, limit=5)
    assert "Merged and verified" in out


def test_window_truncated_to_max_chars() -> None:
    long_reason = "x" * 500
    events = [
        {
            "event_type": EventType.PLAN_CREATED.value,
            "producer": "planner",
            "created_at": "t0",
            "payload": {"reasoning": long_reason},
        },
    ]
    out = build_short_term_memory_window(events, limit=50, max_chars=120)
    assert len(out) <= 120
