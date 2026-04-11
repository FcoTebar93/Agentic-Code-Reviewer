"""Regression: Dev prompt security block stays aligned with SECURITY_RULES."""

from __future__ import annotations

from services.dev_service.security_gate_brief import security_gate_brief
from services.security_service.config import SECURITY_RULES


def test_security_gate_brief_lists_all_rule_ids() -> None:
    text = security_gate_brief()
    for rule_id, _ in SECURITY_RULES:
        assert f"- {rule_id}" in text


def test_security_gate_brief_mentions_pipeline() -> None:
    assert "security_service" in security_gate_brief()
