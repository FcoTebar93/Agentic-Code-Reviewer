from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException

from services.gateway_service.routes.approvals import (
    approve_pr,
    list_approvals,
    reject_pr,
)
from services.gateway_service.routes.health import get_status, health
from services.gateway_service.routes.proxy import _proxy_json
from shared.contracts.events import PrApprovalPayload


@dataclass
class _FakeManager:
    connection_count: int = 0
    messages: list[str] = field(default_factory=list)

    async def broadcast(self, message: str) -> None:
        self.messages.append(message)


@dataclass
class _FakeEventBus:
    events: list[Any] = field(default_factory=list)

    async def publish(self, event: Any) -> None:
        self.events.append(event)


def _build_runtime() -> Any:
    payload = PrApprovalPayload(
        approval_id="approval-1",
        plan_id="11111111-1111-1111-1111-111111111111",
        branch_name="feat/test",
        files_count=2,
        security_reasoning="ok",
        pr_context={"repo_url": "https://example/repo"},
    )
    return SimpleNamespace(
        pending_approvals={payload.approval_id: payload},
        manager=_FakeManager(connection_count=3),
        event_bus=_FakeEventBus(),
        approvals_rate_limit_counters={},
        cfg=SimpleNamespace(
            approvals_auth_enabled=False,
            approvals_auth_token="",
            approvals_rate_limit_enabled=False,
            approvals_rate_limit_window_seconds=60,
            approvals_rate_limit_max_requests=20,
        ),
    )


def test_health_and_status_report_gateway_runtime_state() -> None:
    async def _run() -> None:
        rt = _build_runtime()
        h = await health(rt)
        s = await get_status(rt)
        assert h["status"] == "ok"
        assert h["ws_connections"] == 3
        assert h["pending_approvals"] == 1
        assert s["ws_connections"] == 3
        assert s["pending_approvals"] == 1

    asyncio.run(_run())


def test_list_approvals_returns_pending_items() -> None:
    async def _run() -> None:
        rt = _build_runtime()
        out = await list_approvals(rt)
        assert out["count"] == 1
        assert out["pending"][0]["approval_id"] == "approval-1"

    asyncio.run(_run())


def test_approve_pr_publishes_event_and_removes_pending_approval() -> None:
    async def _run() -> None:
        rt = _build_runtime()
        result = await approve_pr("approval-1", rt)
        assert result["status"] == "approved"
        assert "approval-1" not in rt.pending_approvals
        assert len(rt.event_bus.events) == 1
        assert len(rt.manager.messages) == 2
        decided_msg = json.loads(rt.manager.messages[0])
        assert decided_msg["type"] == "approval_decided"

    asyncio.run(_run())


def test_reject_pr_returns_404_for_unknown_approval() -> None:
    async def _run() -> None:
        rt = _build_runtime()
        response = await reject_pr("unknown", rt)
        assert response.status_code == 404
        body = json.loads(response.body.decode("utf-8"))
        assert "not found" in body["error"]

    asyncio.run(_run())


def test_proxy_json_handles_empty_and_invalid_payloads() -> None:
    class _Resp:
        def __init__(self, text: str, status_code: int, parsed: Any = None):
            self.text = text
            self.status_code = status_code
            self._parsed = parsed

        def json(self) -> Any:
            if self._parsed == "raise":
                raise ValueError("bad json")
            return self._parsed

    empty = _proxy_json(_Resp("", 502))
    assert empty["status"] == 502

    invalid = _proxy_json(_Resp("{bad", 200, "raise"))
    assert "Invalid upstream response" in invalid["error"]


def test_list_approvals_requires_token_when_auth_enabled() -> None:
    async def _run() -> None:
        rt = _build_runtime()
        rt.cfg.approvals_auth_enabled = True
        rt.cfg.approvals_auth_token = "secret-approval-token"
        try:
            await list_approvals(rt, x_approval_token="wrong-token")
            raise AssertionError("Expected HTTPException 403")
        except HTTPException as exc:
            assert exc.status_code == 403

    asyncio.run(_run())


def test_approve_pr_rate_limited_when_enabled() -> None:
    async def _run() -> None:
        rt = _build_runtime()
        rt.cfg.approvals_rate_limit_enabled = True
        rt.cfg.approvals_rate_limit_window_seconds = 60
        rt.cfg.approvals_rate_limit_max_requests = 1

        first = await approve_pr("approval-1", rt)
        assert first["status"] == "approved"

        try:
            await approve_pr("approval-1", rt)
            raise AssertionError("Expected HTTPException 429")
        except HTTPException as exc:
            assert exc.status_code == 429

    asyncio.run(_run())

