from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from pydantic import ValidationError

from shared.tools.models import ToolDefinition, ToolExecutionResult, ToolInput
from shared.tools.registry import ToolRegistry

# Segundos a esperar entre reintentos (backoff simple para fallos transitorios)
_TOOL_RETRY_DELAY_S = 1.0


class ToolExecutionError(Exception):
    """Raised when a tool cannot be executed successfully."""


async def _maybe_await(func, arg: ToolInput) -> Any:
    result = func(arg)
    if asyncio.iscoroutine(result):
        return await result
    return result


async def execute_tool(
    registry: ToolRegistry,
    name: str,
    raw_args: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Execute a tool by name with raw dict arguments.

    Responsibilities:
    - Look up the tool definition in the registry
    - Validate input arguments using the tool's Pydantic model
    - Enforce timeouts and retries
    - Return a structured ToolExecutionResult
    """
    tool = registry.get(name)
    if tool is None:
        return ToolExecutionResult(
            success=False,
            error=f"Unknown tool: {name}",
        )

    try:
        args = tool.input_model.model_validate(raw_args)
    except ValidationError as exc:
        return ToolExecutionResult(
            success=False,
            error=f"Invalid arguments for tool {name}: {exc}",
        )

    retries = 0
    start = time.monotonic()
    last_error: str | None = None

    while True:
        try:
            result = await asyncio.wait_for(
                _maybe_await(tool.func, args),
                timeout=tool.timeout_s if tool.timeout_s > 0 else None,
            )
            duration = time.monotonic() - start
            return ToolExecutionResult(
                success=True,
                output=result,
                error=None,
                retries=retries,
                duration_s=duration,
            )
        except Exception as exc:
            last_error = str(exc)
            if retries >= tool.max_retries:
                duration = time.monotonic() - start
                return ToolExecutionResult(
                    success=False,
                    output=None,
                    error=f"Tool {name} failed after {retries + 1} attempt(s): {last_error}",
                    retries=retries,
                    duration_s=duration,
                )
            retries += 1
            await asyncio.sleep(_TOOL_RETRY_DELAY_S)

