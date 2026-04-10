"""Service dependencies for spec pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from services.spec_service.config import SpecConfig
from shared.tools import ToolRegistry
from shared.utils import EventBus


@dataclass(frozen=True)
class SpecPipelineDeps:
    http_client: httpx.AsyncClient
    cfg: SpecConfig
    event_bus: EventBus
    tool_registry: ToolRegistry
