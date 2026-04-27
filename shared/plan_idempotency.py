"""Stable idempotency keys for POST /plan (gateway vs meta_planner)."""

from __future__ import annotations

import hashlib
from typing import Any


def _norm_mode(raw: str) -> str:
    x = (raw or "normal").strip().lower()
    if x == "ahorro":
        return "save"
    if x in ("normal", "save"):
        return x
    return "normal"


def plan_idempotency_key_gateway(body: dict[str, Any]) -> str:
    """Key from the full client body proxied to meta_planner."""
    from shared.prompt_locale import normalize_user_locale

    parts = [
        (str(body.get("prompt") or "")).strip(),
        (str(body.get("project_name") or "default")).strip(),
        (str(body.get("repo_url") or "")).strip(),
        _norm_mode(str(body.get("mode") or "normal")),
        normalize_user_locale(str(body.get("user_locale") or "") or None),
        (str(body.get("replanner_aggressiveness") or "1")).strip(),
        (str(body.get("llm_provider") or "default")).strip().lower(),
    ]
    material = "|".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def plan_idempotency_key_meta_planner(body: dict[str, Any]) -> str:
    """Key from fields that affect planner output (PlanRequest / model_dump)."""
    from shared.prompt_locale import normalize_user_locale

    parts = [
        (str(body.get("prompt") or "")).strip(),
        (str(body.get("project_name") or "default")).strip(),
        (str(body.get("repo_url") or "")).strip(),
        _norm_mode(str(body.get("mode") or "normal")),
        normalize_user_locale(str(body.get("user_locale") or "") or None),
    ]
    material = "|".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
