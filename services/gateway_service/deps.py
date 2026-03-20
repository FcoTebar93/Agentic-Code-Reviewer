from __future__ import annotations

from fastapi import Request

from services.gateway_service.runtime import GatewayRuntime


def get_gateway_runtime(request: Request) -> GatewayRuntime:
    return request.app.state.gateway_runtime
