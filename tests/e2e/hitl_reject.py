"""E2E: HITL rechaza → no debe haber `pr.created`."""

from __future__ import annotations

import time

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


def test_hitl_reject_no_pr_created(e2e_client: httpx.Client) -> None:
    body = unique_plan_body("HITL reject E2E")
    hdrs = approval_headers()

    pr = e2e_client.post("/api/plan", json=body)
    assert pr.status_code == 200, pr.text
    plan_id = str(pr.json()["plan_id"])
    timeout = e2e_timeout_seconds()

    def _pending() -> dict | None:
        ar = e2e_client.get("/api/approvals", headers=hdrs)
        assert ar.status_code == 200, ar.text
        for item in ar.json().get("pending") or []:
            if isinstance(item, dict) and item.get("plan_id") == plan_id:
                return item
        return None

    pending = poll_until(
        _pending,
        timeout_s=timeout,
        description=f"aprobación pendiente (reject) plan {plan_id[:8]}",
    )
    approval_id = str(pending["approval_id"])

    rv = e2e_client.post(f"/api/approvals/{approval_id}/reject", headers=hdrs)
    assert rv.status_code == 200, rv.text
    assert rv.json().get("status") == "rejected"

    grace = min(60.0, max(25.0, timeout * 0.25))
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if "pr.created" in event_types(fetch_plan_events(e2e_client, plan_id)):
            pytest.fail("No se esperaba pr.created tras rechazo HITL")
        time.sleep(1.5)
