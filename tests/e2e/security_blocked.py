"""
E2E: código con `eval` bloqueado por security_service.

Requiere en **dev_service**: `ADMADC_MOCK_CODEGEN_INJECT_EVAL=true`.
Al ejecutar pytest: `ADMADC_E2E_SCENARIO_SECURITY_BLOCK=1`.
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

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_security_block]


@pytest.mark.usefixtures("e2e_security_block_scenario")
def test_security_blocked_no_hitl_pending(e2e_client: httpx.Client) -> None:
    body = unique_plan_body("security blocked E2E (inject eval)")
    hdrs = approval_headers()

    pr = e2e_client.post("/api/plan", json=body)
    assert pr.status_code == 200, pr.text
    plan_id = str(pr.json()["plan_id"])
    timeout = e2e_timeout_seconds()

    def _blocked() -> bool | None:
        types = event_types(fetch_plan_events(e2e_client, plan_id))
        if "security.blocked" in types:
            return True
        return None

    poll_until(
        _blocked,
        timeout_s=timeout,
        description=f"security.blocked plan {plan_id[:8]}",
    )

    final_t = event_types(fetch_plan_events(e2e_client, plan_id))
    assert "security.blocked" in final_t
    assert "security.approved" not in final_t

    ar = e2e_client.get("/api/approvals", headers=hdrs)
    assert ar.status_code == 200, ar.text
    for item in ar.json().get("pending") or []:
        if isinstance(item, dict) and item.get("plan_id") == plan_id:
            pytest.fail("No debería haber aprobación HITL si security bloqueó")
