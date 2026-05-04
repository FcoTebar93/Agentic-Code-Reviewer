"""Contratos QA/security: eventos ↔ payloads Pydantic."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts.events import (
    EventType,
    QAResultPayload,
    SecurityResultPayload,
    qa_failed,
    qa_passed,
    security_approved,
    security_blocked,
)


def _qa(**overrides: Any) -> QAResultPayload:
    d: dict[str, Any] = {
        "plan_id": "p1",
        "task_id": "t1",
        "passed": True,
        "issues": [],
        "code": "x = 1",
        "file_path": "m.py",
        "qa_attempt": 0,
        "reasoning": "ok",
        "mode": "normal",
        "module": "services/foo",
        "severity_hint": "medium",
        "user_locale": "en",
    }
    d.update(overrides)
    return QAResultPayload(**d)


def _sec(**overrides: Any) -> SecurityResultPayload:
    d: dict[str, Any] = {
        "plan_id": "p1",
        "branch_name": "feat/x",
        "approved": False,
        "violations": ["secret in code"],
        "files_scanned": 2,
        "pr_context": {"repo_url": "https://example/r"},
        "reasoning": "blocked",
        "severity_hint": "high",
        "user_locale": "es",
    }
    d.update(overrides)
    return SecurityResultPayload(**d)


def test_qa_passed() -> None:
    p = _qa(passed=True)
    e = qa_passed("qa_service", p)
    assert e.event_type == EventType.QA_PASSED
    assert e.producer == "qa_service"
    r = QAResultPayload.model_validate(e.payload)
    assert r.plan_id == p.plan_id and r.passed and r.severity_hint == "medium"


def test_qa_failed() -> None:
    p = _qa(passed=False, issues=["lint error"])
    e = qa_failed("qa_service", p)
    assert e.event_type == EventType.QA_FAILED
    r = QAResultPayload.model_validate(e.payload)
    assert not r.passed and r.issues == ["lint error"]


def test_security_ok() -> None:
    p = _sec(approved=True, violations=[])
    e = security_approved("security_service", p)
    assert e.event_type == EventType.SECURITY_APPROVED
    r = SecurityResultPayload.model_validate(e.payload)
    assert r.approved and r.violations == []


def test_security_blocked() -> None:
    p = _sec(approved=False)
    e = security_blocked("security_service", p)
    assert e.event_type == EventType.SECURITY_BLOCKED
    r = SecurityResultPayload.model_validate(e.payload)
    assert not r.approved
    assert r.violations == ["secret in code"]
    assert r.pr_context["repo_url"] == "https://example/r"


def test_qa_rejects_missing_task_id() -> None:
    with pytest.raises(ValidationError) as exc:
        QAResultPayload.model_validate(
            {
                "plan_id": "p",
                "passed": True,
                "issues": [],
                "code": "",
                "file_path": "a.py",
                "qa_attempt": 0,
            }
        )
    assert "task_id" in str(exc.value).lower()


def test_sec_rejects_missing_violations() -> None:
    with pytest.raises(ValidationError) as exc:
        SecurityResultPayload.model_validate(
            {
                "plan_id": "p",
                "branch_name": "b",
                "approved": True,
                "files_scanned": 0,
            }
        )
    assert "violations" in str(exc.value).lower()
