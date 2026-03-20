from __future__ import annotations

from fastapi import APIRouter, Depends

from shared.observability.metrics import metrics_response
from services.gateway_service.constants import SERVICE_NAME
from services.gateway_service.deps import get_gateway_runtime
from services.gateway_service.runtime import GatewayRuntime

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(rt: GatewayRuntime = Depends(get_gateway_runtime)):
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "ws_connections": rt.manager.connection_count,
        "pending_approvals": len(rt.pending_approvals),
    }


@router.get("/metrics")
async def metrics():
    return metrics_response()


@router.get("/api/status")
async def get_status(rt: GatewayRuntime = Depends(get_gateway_runtime)):
    return {
        "ws_connections": rt.manager.connection_count,
        "pending_approvals": len(rt.pending_approvals),
        "service": SERVICE_NAME,
    }
