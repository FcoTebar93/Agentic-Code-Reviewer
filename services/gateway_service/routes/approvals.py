from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

from services.gateway_service.constants import SERVICE_NAME
from services.gateway_service.deps import get_gateway_runtime
from services.gateway_service.http_helpers import error_response
from services.gateway_service.runtime import GatewayRuntime
from shared.contracts.events import pr_human_approved, pr_human_rejected
from shared.observability.metrics import approvals_access_denied

router = APIRouter(prefix="/api", tags=["approvals"])
logger = logging.getLogger(SERVICE_NAME)


def _require_approvals_auth(
    rt: GatewayRuntime,
    provided_token: str | None,
    *,
    action: str,
) -> None:
    if not rt.cfg.approvals_auth_enabled:
        return
    expected = (rt.cfg.approvals_auth_token or "").strip()
    if not expected:
        logger.warning(
            "Approvals auth misconfigured (enabled without token) action=%s",
            action,
        )
        approvals_access_denied.labels(
            service=SERVICE_NAME,
            reason="auth_misconfigured",
            action=action,
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Approvals auth enabled but token is not configured",
        )
    if provided_token != expected:
        logger.warning("Forbidden approvals access action=%s", action)
        approvals_access_denied.labels(
            service=SERVICE_NAME,
            reason="auth_forbidden",
            action=action,
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


def _enforce_approvals_rate_limit(
    rt: GatewayRuntime,
    key: str,
    *,
    action: str,
) -> None:
    if not rt.cfg.approvals_rate_limit_enabled:
        return
    now = time.monotonic()
    window = float(rt.cfg.approvals_rate_limit_window_seconds)
    max_requests = rt.cfg.approvals_rate_limit_max_requests
    bucket = rt.approvals_rate_limit_counters.get(key, [])
    bucket = [ts for ts in bucket if now - ts <= window]
    if len(bucket) >= max_requests:
        logger.warning(
            "Approvals rate limit exceeded action=%s key=%s window_s=%d max=%d",
            action,
            key,
            rt.cfg.approvals_rate_limit_window_seconds,
            max_requests,
        )
        approvals_access_denied.labels(
            service=SERVICE_NAME,
            reason="rate_limited",
            action=action,
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many approval requests",
        )
    bucket.append(now)
    rt.approvals_rate_limit_counters[key] = bucket


def _approvals_rate_limit_snapshot(rt: GatewayRuntime) -> dict:
    """In-window counts per rate-limit key (monotonic clock), for ops diagnostics."""
    now = time.monotonic()
    window = float(rt.cfg.approvals_rate_limit_window_seconds)
    buckets: list[dict[str, str | int | float]] = []
    for key, stamps in list(rt.approvals_rate_limit_counters.items()):
        in_window = [ts for ts in stamps if now - ts <= window]
        if in_window:
            rt.approvals_rate_limit_counters[key] = in_window
        else:
            rt.approvals_rate_limit_counters.pop(key, None)
            continue
        oldest = min(in_window)
        buckets.append(
            {
                "key": key,
                "count_in_window": len(in_window),
                "oldest_age_seconds": round(now - oldest, 3),
            }
        )
    buckets.sort(key=lambda b: str(b["key"]))
    return {
        "tracked_keys": len(buckets),
        "buckets": buckets,
    }


async def _decide_approval(
    approval_id: str,
    rt: GatewayRuntime,
    *,
    action: str,
    decision: str,
) -> dict | JSONResponse:
    _enforce_approvals_rate_limit(rt, f"{action}:{approval_id}", action=action)
    approval = rt.pending_approvals.get(approval_id)
    if not approval:
        return error_response(
            f"Approval {approval_id} not found or already decided",
            status_code=404,
        )

    approval.decision = decision
    rt.pending_approvals.pop(approval_id, None)

    event_builder = pr_human_approved if decision == "approved" else pr_human_rejected
    event = event_builder(SERVICE_NAME, approval)
    await rt.event_bus.publish(event)
    await rt.manager.broadcast(
        json.dumps({"type": "approval_decided", "approval": approval.model_dump()})
    )
    await rt.manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )
    logger.info(
        "Human %s PR for plan %s (approval %s)",
        decision.upper(),
        approval.plan_id[:8],
        approval_id[:8],
    )
    return {"status": decision, "plan_id": approval.plan_id}


@router.get("/approvals/audit_summary")
async def approvals_audit_summary(
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    x_approval_token: str | None = Header(default=None),
):
    if not rt.cfg.approvals_audit_summary_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    _require_approvals_auth(rt, x_approval_token, action="audit_summary")
    snap = _approvals_rate_limit_snapshot(rt)
    return {
        "service": SERVICE_NAME,
        "rate_limit": {
            "enabled": rt.cfg.approvals_rate_limit_enabled,
            "window_seconds": rt.cfg.approvals_rate_limit_window_seconds,
            "max_requests": rt.cfg.approvals_rate_limit_max_requests,
        },
        "pending_approvals_count": len(rt.pending_approvals),
        **snap,
    }


@router.get("/approvals")
async def list_approvals(
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    x_approval_token: str | None = Header(default=None),
):
    _require_approvals_auth(rt, x_approval_token, action="list")
    return {
        "pending": [a.model_dump() for a in rt.pending_approvals.values()],
        "count": len(rt.pending_approvals),
    }


@router.post("/approvals/{approval_id}/approve")
async def approve_pr(
    approval_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    x_approval_token: str | None = Header(default=None),
):
    _require_approvals_auth(rt, x_approval_token, action="approve")
    return await _decide_approval(
        approval_id,
        rt,
        action="approve",
        decision="approved",
    )


@router.post("/approvals/{approval_id}/reject")
async def reject_pr(
    approval_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    x_approval_token: str | None = Header(default=None),
):
    _require_approvals_auth(rt, x_approval_token, action="reject")
    return await _decide_approval(
        approval_id,
        rt,
        action="reject",
        decision="rejected",
    )
