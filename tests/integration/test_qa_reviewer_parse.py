"""Casos adicionales del parser de veredicto QA (sin LLM)."""

from __future__ import annotations

import pytest

from services.qa_service.reviewer import _parse_review_response

pytestmark = [pytest.mark.integration]


def test_parse_verdict_pass_minimal() -> None:
    raw = """REASONING: Looks fine.
VERDICT: PASS
ISSUES: none
REQUIRED_CHANGES: none
OPTIONAL_IMPROVEMENTS: none
"""
    r = _parse_review_response(raw)
    assert r.passed is True
    assert r.required_changes == []


def test_parse_fail_adds_synthetic_issue_when_empty_issues() -> None:
    raw = """REASONING: Bad.
VERDICT: FAIL
ISSUES: none
REQUIRED_CHANGES: none
OPTIONAL_IMPROVEMENTS: none
"""
    r = _parse_review_response(raw)
    assert r.passed is False
    assert any("without specific issues" in i.lower() for i in r.issues)


def test_parse_issues_multiline_with_tags() -> None:
    raw = """
REASONING: Mixed.
VERDICT: FAIL
ISSUES:
- [error|security] Weak crypto
- [warning|style] Long line
REQUIRED_CHANGES: none
OPTIONAL_IMPROVEMENTS: none
"""
    r = _parse_review_response(raw)
    assert not r.passed
    assert len(r.issues) >= 2
    assert r.structured_feedback["security"]
