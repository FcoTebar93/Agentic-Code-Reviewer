"""Idempotency keys for POST /plan (gateway vs meta_planner)."""

from __future__ import annotations

from shared.plan_idempotency import (
    plan_idempotency_key_gateway,
    plan_idempotency_key_meta_planner,
)


def test_meta_planner_key_differs_by_locale() -> None:
    base = {
        "prompt": "hello",
        "project_name": "p",
        "repo_url": "",
        "mode": "normal",
        "user_locale": "en",
    }
    a = plan_idempotency_key_meta_planner(base)
    b = plan_idempotency_key_meta_planner({**base, "user_locale": "es"})
    assert a != b


def test_meta_planner_key_differs_by_mode() -> None:
    base = {
        "prompt": "hello",
        "project_name": "p",
        "repo_url": "",
        "mode": "normal",
        "user_locale": "en",
    }
    a = plan_idempotency_key_meta_planner(base)
    b = plan_idempotency_key_meta_planner({**base, "mode": "save"})
    assert a != b


def test_gateway_key_includes_optional_client_fields() -> None:
    core = {
        "prompt": "x",
        "project_name": "p",
        "repo_url": "",
        "mode": "normal",
        "user_locale": "en",
    }
    a = plan_idempotency_key_gateway({**core, "replanner_aggressiveness": "1"})
    b = plan_idempotency_key_gateway({**core, "replanner_aggressiveness": "2"})
    assert a != b

    c = plan_idempotency_key_gateway({**core, "llm_provider": "default"})
    d = plan_idempotency_key_gateway({**core, "llm_provider": "groq"})
    assert c != d


def test_mode_ahorro_normalized_like_save_meta() -> None:
    a = plan_idempotency_key_meta_planner(
        {
            "prompt": "x",
            "project_name": "p",
            "repo_url": "",
            "mode": "ahorro",
            "user_locale": "en",
        }
    )
    b = plan_idempotency_key_meta_planner(
        {
            "prompt": "x",
            "project_name": "p",
            "repo_url": "",
            "mode": "save",
            "user_locale": "en",
        }
    )
    assert a == b
