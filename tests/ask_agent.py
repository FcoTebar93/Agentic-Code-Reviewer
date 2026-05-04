"""Unit tests for meta_planner ask_agent context formatting."""

from __future__ import annotations

from services.meta_planner.ask_agent import _format_events_block, _format_semantic_block


def test_format_semantic_block_empty() -> None:
    block, sources = _format_semantic_block([])
    assert "No semantic hits" in block
    assert sources == []


def test_format_semantic_block_with_payload() -> None:
    raw = [
        {
            "id": "e1",
            "score": 0.9,
            "heuristic_score": 0.91,
            "payload": {
                "text": "plan created for api",
                "event_type": "plan.created",
                "plan_id": "abc-uuid",
            },
        }
    ]
    block, sources = _format_semantic_block(raw)
    assert "plan.created" in block
    assert "abc-uuid" in block
    assert len(sources) == 1
    assert sources[0]["event_type"] == "plan.created"
    assert sources[0]["plan_id"] == "abc-uuid"


def test_format_events_block_empty() -> None:
    b = _format_events_block([])
    assert "No events loaded" in b


def test_format_events_block_items() -> None:
    evs = [
        {
            "event_type": "qa.failed",
            "created_at": "2025-01-01T12:00:00Z",
            "payload": {"reasoning": "missing tests"},
        }
    ]
    b = _format_events_block(evs)
    assert "qa.failed" in b
    assert "missing" in b
