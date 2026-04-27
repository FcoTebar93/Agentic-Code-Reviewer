from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Type

from pydantic import BaseModel


class ToolInput(BaseModel):
    """Base class for tool input models."""


    ToolFunc = Callable[[Any], Awaitable[Any]] | Callable[[Any], Any]


@dataclass
class ToolDefinition:
    """Runtime description of a tool available to agents."""

    name: str
    description: str
    input_model: Type[ToolInput]
    func: ToolFunc
    timeout_s: float = 30.0
    max_retries: int = 0
    sandboxed: bool = True
    tags: list[str] = field(default_factory=list)

    def json_schema(self) -> dict[str, Any]:
        """Return the JSON schema for the tool's input model."""
        return self.input_model.model_json_schema()


@dataclass
class ToolExecutionResult:
    """Normalised result of executing a tool."""

    success: bool
    output: Any = None
    error: str | None = None
    retries: int = 0
    duration_s: float | None = None
