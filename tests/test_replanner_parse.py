"""Tests de parsing de salida LLM del replanner."""

from __future__ import annotations

from services.replanner_service.critic import ReplanDecision, _parse_replanner_response


def test_empty() -> None:
    d = _parse_replanner_response("")
    assert d == ReplanDecision(
        revision_needed=False,
        severity="medium",
        reason="",
        suggestions=[],
    )


def test_full() -> None:
    raw = """
REASON: QA failed on validation; narrow scope.
SEVERITY: high
REVISION_NEEDED: yes
SUGGESTIONS:
- Add unit tests for edge cases in validators
- Re-run lint before merge
"""
    d = _parse_replanner_response(raw)
    assert d.revision_needed and d.severity == "high"
    assert "validation" in d.reason
    assert len(d.suggestions) == 2
    assert "unit tests" in d.suggestions[0]


def test_revision_no() -> None:
    raw = """REASON: Acceptable noise.
SEVERITY: low
REVISION_NEEDED: no
SUGGESTIONS:
- none
"""
    d = _parse_replanner_response(raw)
    assert not d.revision_needed and d.severity == "low"


def test_skip_none_suggestions() -> None:
    raw = """REASON: ok
SEVERITY: medium
REVISION_NEEDED: no
SUGGESTIONS:
- none
- n/a
- Real suggestion here
"""
    d = _parse_replanner_response(raw)
    assert d.suggestions == ["Real suggestion here"]


def test_any_order() -> None:
    raw = """REVISION_NEEDED: yes
SEVERITY: critical
REASON: Out of order lines still parse.
SUGGESTIONS:
- Fix A
"""
    d = _parse_replanner_response(raw)
    assert d.revision_needed and d.severity == "critical"
    assert "Out of order" in d.reason


def test_lowercase_labels() -> None:
    raw = """reason: Lowercase label
severity: HIGH
revision_needed: YES
SUGGESTIONS:
- One
"""
    d = _parse_replanner_response(raw)
    assert d.reason.startswith("Lowercase")
    assert d.severity == "high"
    assert d.revision_needed
