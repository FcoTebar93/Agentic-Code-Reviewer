from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Type

from pydantic import BaseModel


class ToolInput(BaseModel):
    """
    Base class for tool input models.

    Each concrete tool should define its own subclass that describes and
    validates the input parameters. This gives us strong typing and schema
    validation "for free" via Pydantic.
    """


ToolFunc = Callable[[ToolInput], Awaitable[Any]] | Callable[[ToolInput], Any]


@dataclass
class ToolDefinition:
    """
    Runtime description of a tool available to agents.

    - name: unique identifier, referenced in prompts and tool calls
    - description: short natural language description shown to the LLM/agents
    - input_model: Pydantic model used for validation and JSON-schema export
    - func: async or sync callable implementing the tool
    - timeout_s: max wall-clock time for a single execution
    - max_retries: how many times to retry on failure
    - sandboxed: whether this tool is expected to be side-effect-safe
    - tags: free-form labels (e.g. ["filesystem", "git", "tests"])
    """

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
    """
    Normalised result of executing a tool.

    - success: whether the tool completed without raising
    - output: raw value returned by the tool (if any)
    - error: error message when success is False
    - retries: how many retry attempts were used
    - duration_s: approximate wall-clock time in seconds
    """

    success: bool
    output: Any = None
    error: str | None = None
    retries: int = 0
    duration_s: float | None = None