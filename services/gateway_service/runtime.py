from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from shared.contracts.events import PrApprovalPayload
from shared.utils import EventBus
from services.gateway_service.config import GatewayConfig
from services.gateway_service.ws_manager import ConnectionManager


@dataclass
class GatewayRuntime:
    """Mutable app-owned state: HTTP, bus, WebSocket manager, HITL queue, idempotency cache."""

    event_bus: EventBus
    http_client: httpx.AsyncClient
    cfg: GatewayConfig
    manager: ConnectionManager
    pending_approvals: dict[str, PrApprovalPayload] = field(default_factory=dict)
    plan_idem_cache: dict[str, tuple[dict, float]] = field(default_factory=dict)
