from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from shared.contracts.events import pr_human_approved, pr_human_rejected
from services.gateway_service.constants import SERVICE_NAME
from services.gateway_service.deps import get_gateway_runtime
from services.gateway_service.runtime import GatewayRuntime

router = APIRouter(prefix="/api", tags=["approvals"])
logger = logging.getLogger(SERVICE_NAME)


@router.get("/approvals")
async def list_approvals(rt: GatewayRuntime = Depends(get_gateway_runtime)):
    return {
        "pending": [a.model_dump() for a in rt.pending_approvals.values()],
        "count": len(rt.pending_approvals),
    }


@router.post("/approvals/{approval_id}/approve")
async def approve_pr(
    approval_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    approval = rt.pending_approvals.get(approval_id)
    if not approval:
        return JSONResponse(
            content={"error": f"Approval {approval_id} not found or already decided"},
            status_code=404,
        )

    approval.decision = "approved"
    rt.pending_approvals.pop(approval_id, None)

    event = pr_human_approved(SERVICE_NAME, approval)
    await rt.event_bus.publish(event)

    await rt.manager.broadcast(
        json.dumps({"type": "approval_decided", "approval": approval.model_dump()})
    )
    await rt.manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )

    logger.info(
        "Human APPROVED PR for plan %s (approval %s)",
        approval.plan_id[:8],
        approval_id[:8],
    )
    return {"status": "approved", "plan_id": approval.plan_id}


@router.post("/approvals/{approval_id}/reject")
async def reject_pr(
    approval_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    approval = rt.pending_approvals.get(approval_id)
    if not approval:
        return JSONResponse(
            content={"error": f"Approval {approval_id} not found or already decided"},
            status_code=404,
        )

    approval.decision = "rejected"
    rt.pending_approvals.pop(approval_id, None)

    event = pr_human_rejected(SERVICE_NAME, approval)
    await rt.event_bus.publish(event)

    await rt.manager.broadcast(
        json.dumps({"type": "approval_decided", "approval": approval.model_dump()})
    )
    await rt.manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )

    logger.info(
        "Human REJECTED PR for plan %s (approval %s)",
        approval.plan_id[:8],
        approval_id[:8],
    )
    return {"status": "rejected", "plan_id": approval.plan_id}
