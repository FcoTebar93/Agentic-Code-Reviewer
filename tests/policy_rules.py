"""Políticas por repo (`policies.json`) y reglas QA/security por lenguaje."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import shared.policies as policies_mod
from shared.policies import (
    ProjectPolicy,
    effective_mode,
    load_project_policy,
    policy_for_path,
    rules_for_language,
)


@pytest.fixture(autouse=True)
def clear_project_policy_cache() -> None:
    """`load_project_policy` memoiza en proceso; limpiar entre tests."""
    policies_mod._CACHED_POLICY = None
    yield
    policies_mod._CACHED_POLICY = None


def test_rules_for_language_filters_category() -> None:
    qa_py = rules_for_language("python", category="qa")
    sec_py = rules_for_language("python", category="security")
    assert qa_py and sec_py
    assert all(r.category == "qa" for r in qa_py)
    assert all(r.category == "security" for r in sec_py)


def test_rules_for_language_any_matches_empty_lang() -> None:
    rules = rules_for_language("", category="qa")
    assert any("any" in r.languages for r in rules)


def test_policy_for_path_longest_prefix_wins() -> None:
    policy: ProjectPolicy = {
        "default_mode": "normal",
        "paths": {
            "services/": {"forced_mode": "save"},
            "services/gateway_service/": {"security_strict": True},
        },
    }
    shallow = policy_for_path(policy, "services/foo.py")
    deep = policy_for_path(policy, "services/gateway_service/routes/x.py")
    assert shallow.get("forced_mode") == "save"
    assert deep.get("security_strict") is True
    assert "forced_mode" not in deep or deep.get("forced_mode") is None


def test_policy_for_path_empty_file_returns_empty() -> None:
    policy: ProjectPolicy = {"default_mode": "normal", "paths": {"src/": {}}}
    assert policy_for_path(policy, "") == {}


def test_effective_mode_forced_overrides_plan() -> None:
    path_pol = {"forced_mode": "strict"}
    assert effective_mode("normal", path_pol, "normal") == "strict"


def test_effective_mode_plan_when_no_force() -> None:
    assert effective_mode("save", {}, "normal") == "save"


def test_effective_mode_fallback_default() -> None:
    assert effective_mode(None, {}, "save") == "save"


def test_load_project_policy_from_json(tmp_path: Path) -> None:
    payload = {
        "default_mode": "save",
        "paths": {"frontend/": {"forced_mode": "normal", "security_strict": True}},
    }
    (tmp_path / "policies.json").write_text(json.dumps(payload), encoding="utf-8")
    pol = load_project_policy(tmp_path)
    assert pol["default_mode"] == "save"
    assert pol["paths"]["frontend/"]["security_strict"] is True


def test_load_project_policy_invalid_json_falls_back(tmp_path: Path) -> None:
    (tmp_path / "policies.json").write_text("{not-json", encoding="utf-8")
    pol = load_project_policy(tmp_path)
    assert pol["default_mode"] == "normal"
    assert pol["paths"] == {}
