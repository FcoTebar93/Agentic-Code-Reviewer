"""Parser de secciones del veredicto QA (REQUIRED_CHANGES, etc.)."""

from __future__ import annotations

from services.qa_service.reviewer import _parse_review_response


def test_required_and_optional_sections() -> None:
    raw = """
REASONING: Missing validation.
VERDICT: FAIL
ISSUES:
- [error|security] No input check
REQUIRED_CHANGES:
1. Add bounds check on x
2. Return 400 on bad input
OPTIONAL_IMPROVEMENTS:
- Add docstring
"""
    r = _parse_review_response(raw)
    assert not r.passed
    assert any("input" in i.lower() for i in r.issues)
    assert r.required_changes == [
        "Add bounds check on x",
        "Return 400 on bad input",
    ]
    assert r.optional_improvements == ["Add docstring"]


def test_required_inline_on_header() -> None:
    raw = """REASONING: x
VERDICT: FAIL
ISSUES: none
REQUIRED_CHANGES: Use pathlib for paths
OPTIONAL_IMPROVEMENTS: none
"""
    r = _parse_review_response(raw)
    assert r.required_changes == ["Use pathlib for paths"]
