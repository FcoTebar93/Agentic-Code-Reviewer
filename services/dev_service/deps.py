"""Service dependencies (HTTP, bus, tools) for tests and future handler extraction."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from shared.tools import ToolRegistry
from shared.utils import EventBus
from services.dev_service.config import DevConfig


@dataclass(frozen=True)
class DevPipelineDeps:
    http_client: httpx.AsyncClient
    cfg: DevConfig
    event_bus: EventBus
    tool_registry: ToolRegistry
