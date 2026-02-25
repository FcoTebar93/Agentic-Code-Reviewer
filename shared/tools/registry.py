from __future__ import annotations

import threading
from typing import Dict, Iterable, Optional

from shared.tools.models import ToolDefinition


class ToolRegistry:
    """
    In-memory registry of tools available to an agent or service.

    Each service typically maintains its own registry and registers tools
    during startup. The registry is designed to be simple and threadsafe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register or overwrite a tool by name."""
        with self._lock:
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry if it exists."""
        with self._lock:
            self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Look up a tool by name."""
        with self._lock:
            return self._tools.get(name)

    def list(self) -> Iterable[ToolDefinition]:
        """Return a snapshot list of all registered tools."""
        with self._lock:
            return list(self._tools.values())

