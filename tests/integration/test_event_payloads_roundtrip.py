"""Roundtrip JSON de payloads adicionales (no cubiertos en test_event_contracts)."""

from __future__ import annotations

import json

import pytest

from shared.contracts.events import (
    BaseEvent,
    PlanRevisionPayload,
    PipelineConclusionPayload,
    PrApprovalPayload,
    SpecGeneratedPayload,
    TokensUsedPayload,
    metrics_tokens_used,
    pipeline_conclusion,
    plan_revision_confirmed,
    spec_generated,
)

pytestmark = [pytest.mark.integration]


def test_plan_revision_roundtrip_via_event_json() -> None:
    p = PlanRevisionPayload(
        original_plan_id="11111111-1111-1111-1111-111111111111",
        new_plan_id="22222222-2222-2222-2222-222222222222",
        reason="qa noise",
        suggestions=["split tasks"],
        severity="high",
        target_group_ids=["g1"],
    )
    ev = plan_revision_confirmed("gateway_service", p)
    raw = json.dumps(ev.payload)
    restored = PlanRevisionPayload.model_validate(json.loads(raw))
    assert restored.original_plan_id == p.original_plan_id
    assert restored.new_plan_id == p.new_plan_id
    assert restored.suggestions == ["split tasks"]


def test_pipeline_conclusion_roundtrip() -> None:
    p = PipelineConclusionPayload(
        plan_id="aaaaaaaa-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        branch_name="feat/x",
        conclusion_text="done",
        files_changed=["a.py"],
        approved=True,
    )
    ev = pipeline_conclusion("gateway_service", p)
    r = PipelineConclusionPayload.model_validate(ev.payload)
    assert r.approved is True
    assert r.files_changed == ["a.py"]


def test_pr_approval_payload_roundtrip() -> None:
    p = PrApprovalPayload(
        approval_id="ap-1",
        plan_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        branch_name="feat/y",
        files_count=2,
        security_reasoning="ok",
        pr_context={"repo_url": "https://example/r"},
    )
    dumped = p.model_dump()
    r = PrApprovalPayload.model_validate(dumped)
    assert r.plan_id == p.plan_id
    assert r.pr_context["repo_url"] == "https://example/r"


def test_tokens_used_and_spec_generated_events_validate() -> None:
    tok = TokensUsedPayload(
        plan_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        service="dev_service",
        prompt_tokens=40,
        completion_tokens=60,
    )
    ev_t = metrics_tokens_used("dev_service", tok)
    BaseEvent.model_validate(ev_t.model_dump())

    spec = SpecGeneratedPayload(
        plan_id=tok.plan_id,
        task_id="task-1",
        file_path="x.py",
        language="python",
        spec_text="must pass",
        test_suggestions="- pytest",
    )
    ev_s = spec_generated("spec_service", spec)
    r = SpecGeneratedPayload.model_validate(ev_s.payload)
    assert r.spec_text == "must pass"
