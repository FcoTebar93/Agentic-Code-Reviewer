"""Agregación de métricas/detalle de plan en gateway (helpers + Memory simulado)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse

from services.gateway_service.config import GatewayConfig
from services.gateway_service.plan_aggregate import (
    _aggregate_token_usage,
    _build_plan_detail_json,
    _compute_pipeline_health,
    _count_replans_for_plan,
    aggregate_plan_metrics,
)
from services.gateway_service.runtime import GatewayRuntime
from shared.contracts.events import EventType

pytestmark = [pytest.mark.integration]


def _gateway_cfg(*, prompt_usd: float = 0.01, completion_usd: float = 0.02) -> GatewayConfig:
    return GatewayConfig(
        rabbitmq_url="amqp://unused",
        memory_service_url="http://memory.test",
        meta_planner_url="http://planner.test",
        log_level="INFO",
        llm_prompt_price_per_1k=prompt_usd,
        llm_completion_price_per_1k=completion_usd,
        cors_allow_origins=["http://localhost:3001"],
        cors_allow_methods=["GET", "POST"],
        cors_allow_headers=["Content-Type"],
        approvals_auth_enabled=False,
        approvals_auth_token="",
        approvals_rate_limit_enabled=False,
        approvals_rate_limit_window_seconds=60,
        approvals_rate_limit_max_requests=20,
        approvals_audit_summary_enabled=False,
    )


def test_aggregate_token_usage_sums_by_service_and_cost() -> None:
    events = [
        {
            "payload": {
                "service": "dev_service",
                "prompt_tokens": 100,
                "completion_tokens": 50,
            }
        },
        {
            "payload": {
                "service": "meta_planner",
                "prompt_tokens": 200,
                "completion_tokens": 0,
            }
        },
    ]
    out = _aggregate_token_usage(events, prompt_price=1.0, completion_price=2.0)
    assert out["total_prompt_tokens"] == 300
    assert out["total_completion_tokens"] == 50
    assert out["total_tokens"] == 350
    assert out["estimated_cost_prompt_usd"] == pytest.approx(0.3)
    assert out["estimated_cost_completion_usd"] == pytest.approx(0.1)
    assert len(out["by_service"]) == 2


def test_compute_pipeline_health_counters_and_status() -> None:
    pid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    evs: list[dict[str, Any]] = [
        {
            "event_type": EventType.TASK_ASSIGNED.value,
            "payload": {"qa_feedback": "fix lint"},
            "created_at": "2025-03-01T10:00:00+00:00",
        },
        {
            "event_type": EventType.QA_FAILED.value,
            "payload": {},
            "created_at": "2025-03-01T10:05:00+00:00",
        },
        {
            "event_type": EventType.SECURITY_BLOCKED.value,
            "payload": {},
            "created_at": "2025-03-01T10:06:00+00:00",
        },
    ]
    h = _compute_pipeline_health(evs, pid)
    assert h["qa_retry_count"] == 1
    assert h["qa_failed_count"] == 1
    assert h["security_blocked_count"] == 1
    assert h["pipeline_status"] == "security_blocked"
    assert h["duration_seconds"] == 360


def test_compute_pipeline_health_approved_over_security_counter() -> None:
    """Si hay conclusión aprobada, el estado final debe ser approved."""
    evs: list[dict[str, Any]] = [
        {
            "event_type": EventType.SECURITY_BLOCKED.value,
            "payload": {},
            "created_at": "2025-03-01T10:00:00+00:00",
        },
        {
            "event_type": EventType.PIPELINE_CONCLUSION.value,
            "payload": {"approved": True},
            "created_at": "2025-03-01T10:10:00+00:00",
        },
    ]
    h = _compute_pipeline_health(evs, "p1")
    assert h["pipeline_status"] == "approved"


def test_count_replans_for_plan() -> None:
    events = [
        {"payload": {"original_plan_id": "plan-a", "new_plan_id": "plan-b"}},
        {"payload": {"original_plan_id": "other", "new_plan_id": "x"}},
        {"payload": {"original_plan_id": "plan-a", "new_plan_id": "plan-c"}},
    ]
    assert _count_replans_for_plan(events, "plan-a") == 2


def test_build_plan_detail_extracts_plan_created_and_code_history() -> None:
    plan_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    metrics = {"pipeline_status": "in_progress", "mode": "normal"}
    tasks = [
        {
            "task_id": "t1",
            "file_path": "src/a.py",
            "language": "python",
            "group_id": "g1",
            "status": "in_progress",
            "qa_attempt": 1,
        }
    ]
    events = [
        {
            "event_type": "plan.created",
            "created_at": "2025-03-02T12:00:00+00:00",
            "payload": {
                "original_prompt": "hello",
                "reasoning": "because",
            },
        },
        {
            "event_type": "code.generated",
            "payload": {
                "task_id": "t1",
                "qa_attempt": 0,
                "code": "x=1",
                "reasoning": "first",
                "file_path": "src/a.py",
                "language": "python",
            },
        },
        {
            "event_type": "code.generated",
            "payload": {
                "task_id": "t1",
                "qa_attempt": 1,
                "code": "x=2",
                "reasoning": "retry",
                "file_path": "src/a.py",
                "language": "python",
            },
        },
    ]
    detail = _build_plan_detail_json(plan_id, metrics, tasks, events)
    assert detail["plan_id"] == plan_id
    assert detail["original_prompt"] == "hello"
    assert detail["planner_reasoning"] == "because"
    assert len(detail["tasks"]) == 1
    assert len(detail["tasks"][0]["code_history"]) == 2
    assert detail["tasks"][0]["code_history"][-1]["code"] == "x=2"


class _FakeResp:
    __slots__ = ("status_code", "_data")

    def __init__(self, status_code: int, data: Any) -> None:
        self.status_code = status_code
        self._data = data

    def json(self) -> Any:
        return self._data


class _FakeAsyncClient:
    """Cola FIFO de respuestas para `aggregate_plan_metrics`."""

    __slots__ = ("_queue",)

    def __init__(self, queue: list[_FakeResp]) -> None:
        self._queue = queue

    async def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResp:
        assert url.endswith("/events"), url
        if not self._queue:
            raise AssertionError("unexpected GET /events — cola vacía")
        return self._queue.pop(0)


def test_aggregate_plan_metrics_end_to_end_with_fake_memory() -> None:
    plan_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    token_rows = [
        {
            "event_type": EventType.METRICS_TOKENS_USED.value,
            "payload": {"service": "meta_planner", "prompt_tokens": 10, "completion_tokens": 5},
            "created_at": "2025-03-03T08:00:00+00:00",
        }
    ]
    health_rows = [
        {
            "event_type": EventType.PLAN_CREATED.value,
            "payload": {},
            "created_at": "2025-03-03T08:01:00+00:00",
        },
        {
            "event_type": EventType.PIPELINE_CONCLUSION.value,
            "payload": {"approved": False},
            "created_at": "2025-03-03T08:02:00+00:00",
        },
    ]
    suggested = [
        {
            "event_type": EventType.PLAN_REVISION_SUGGESTED.value,
            "payload": {"original_plan_id": plan_id},
        }
    ]
    confirmed = [
        {
            "event_type": EventType.PLAN_REVISION_CONFIRMED.value,
            "payload": {"original_plan_id": plan_id},
        }
    ]
    client = _FakeAsyncClient(
        [
            _FakeResp(200, token_rows),
            _FakeResp(200, health_rows),
            _FakeResp(200, suggested),
            _FakeResp(200, confirmed),
        ]
    )
    rt = GatewayRuntime(
        event_bus=MagicMock(),
        http_client=client,  # type: ignore[arg-type]
        cfg=_gateway_cfg(prompt_usd=0.0, completion_usd=0.0),
        manager=MagicMock(),
    )

    out = asyncio.run(aggregate_plan_metrics(rt, plan_id))
    assert isinstance(out, dict)
    assert out["plan_id"] == plan_id
    assert out["total_tokens"] == 15
    assert out["pipeline_status"] == "in_progress"
    assert out["replan_suggestions_count"] == 1
    assert out["replan_confirmed_count"] == 1


def test_aggregate_plan_metrics_returns_502_when_token_fetch_fails() -> None:
    client = _FakeAsyncClient([_FakeResp(503, {"error": "db down"})])
    rt = GatewayRuntime(
        event_bus=MagicMock(),
        http_client=client,  # type: ignore[arg-type]
        cfg=_gateway_cfg(),
        manager=MagicMock(),
    )
    out = asyncio.run(aggregate_plan_metrics(rt, "any-plan-id"))
    assert isinstance(out, JSONResponse)
    assert out.status_code == 502
