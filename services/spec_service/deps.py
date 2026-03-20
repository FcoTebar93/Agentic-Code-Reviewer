"""Service dependencies for spec pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from shared.tools import ToolRegistry
from shared.utils import EventBus
from services.spec_service.config import SpecConfig


@dataclass(frozen=True)
class SpecPipelineDeps:
    http_client: httpx.AsyncClient
    cfg: SpecConfig
    event_bus: EventBus
    tool_registry: ToolRegistry
