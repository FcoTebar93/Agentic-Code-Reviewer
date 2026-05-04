"""
E2E: mock QA fuerza FAIL hasta agotar reintentos → `qa.failed`.

Requiere en **qa_service**: `ADMADC_MOCK_QA_FORCE_FAIL=true`.
Al ejecutar pytest: `ADMADC_E2E_SCENARIO_QA_FAIL=1`.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.conftest import (
    e2e_timeout_seconds,
    event_types,
    fetch_plan_events,
    poll_until,
    unique_plan_body,
)

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_qa_fail]


@pytest.mark.usefixtures("e2e_qa_fail_scenario")
def test_qa_exhausted_emits_qa_failed(e2e_client: httpx.Client) -> None:
    body = unique_plan_body("QA exhaust fail E2E")
    pr = e2e_client.post("/api/plan", json=body)
    assert pr.status_code == 200, pr.text
    plan_id = str(pr.json()["plan_id"])
    timeout = e2e_timeout_seconds()

    def _failed() -> bool | None:
        types = event_types(fetch_plan_events(e2e_client, plan_id))
        if "qa.failed" in types:
            return True
        return None

    poll_until(_failed, timeout_s=timeout, description=f"qa.failed plan {plan_id[:8]}")

    final_t = event_types(fetch_plan_events(e2e_client, plan_id))
    assert "qa.failed" in final_t
    assert "qa.passed" not in final_t
    assert "pr.requested" not in final_t
