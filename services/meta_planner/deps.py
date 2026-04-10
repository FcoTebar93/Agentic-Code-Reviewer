"""Service dependencies for planner HTTP and Rabbit consumers."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from services.meta_planner.config import PlannerConfig
from shared.tools import ToolRegistry
from shared.utils import EventBus


@dataclass(frozen=True)
class MetaPlannerDeps:
    http_client: httpx.AsyncClient
    cfg: PlannerConfig
    event_bus: EventBus
    tool_registry: ToolRegistry
