"""
Smoke E2E: plan → agentes (mock) → HITL → PR materializado.

Requisitos:
  - Stack completo: `docker compose up --build` con `LLM_PROVIDER=mock` (valor por defecto en `.env.example`).
  - Puerto del Gateway expuesto (8080 por defecto).
  - Ejecutar: `ADMADC_E2E=1 pytest tests/e2e/pipeline_smoke.py -q`

Opcional: si el gateway tiene `GATEWAY_APPROVALS_AUTH_ENABLED=true`, pasá el mismo token en
`ADMADC_E2E_APPROVAL_TOKEN`.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.conftest import (
    approval_headers,
    e2e_timeout_seconds,
    event_types,
    fetch_plan_events,
    poll_until,
    unique_plan_body,
)

pytestmark = pytest.mark.e2e


def test_full_pipeline_mock_llm_hitl_approve(e2e_client: httpx.Client) -> None:
    body = unique_plan_body("add a tiny hello helper in Python (smoke approve)")
    hdrs = approval_headers()

    pr = e2e_client.post("/api/plan", json=body)
    assert pr.status_code == 200, pr.text
    plan_payload = pr.json()
    assert "plan_id" in plan_payload, plan_payload
    plan_id = str(plan_payload["plan_id"])

    timeout = e2e_timeout_seconds()

    def _pending_approval() -> dict | None:
        ar = e2e_client.get("/api/approvals", headers=hdrs)
        assert ar.status_code == 200, ar.text
        data = ar.json()
        pending = data.get("pending") or []
        for item in pending:
            if isinstance(item, dict) and item.get("plan_id") == plan_id:
                return item
        return None

    pending = poll_until(
        _pending_approval,
        timeout_s=timeout,
        description=f"aprobación pendiente para plan {plan_id[:8]}",
    )
    approval_id = str(pending["approval_id"])

    ap = e2e_client.post(
        f"/api/approvals/{approval_id}/approve",
        headers=hdrs,
    )
    assert ap.status_code == 200, ap.text
    assert ap.json().get("status") == "approved"

    def _pr_created() -> bool | None:
        evs = fetch_plan_events(e2e_client, plan_id)
        return True if "pr.created" in event_types(evs) else None

    poll_until(
        _pr_created,
        timeout_s=timeout,
        description=f"evento pr.created para plan {plan_id[:8]}",
    )

    final_events = fetch_plan_events(e2e_client, plan_id)
    types = event_types(final_events)

    assert "plan.created" in types
    assert "qa.passed" in types
    assert "security.approved" in types
    assert "pipeline.conclusion" in types
    assert "pr.created" in types
