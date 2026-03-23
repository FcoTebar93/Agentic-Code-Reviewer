"""
Map ToolRegistry entries to OpenAI Chat Completions `tools` JSON.

Used by agent loops that call `LLMRequest(tools=..., messages=...)`.
"""

from __future__ import annotations

from collections.abc import Iterable

from shared.tools.registry import ToolRegistry


def tools_openai_from_registry(
    registry: ToolRegistry,
    include_names: Iterable[str],
) -> list[dict]:
    """Build `tools` list preserving the order of `include_names`."""
    by_name = {t.name: t for t in registry.list()}
    out: list[dict] = []
    for name in include_names:
        tool = by_name.get(name)
        if tool is None:
            continue
        schema = tool.input_model.model_json_schema()
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (tool.description or "")[:2048],
                    "parameters": schema,
                },
            }
        )
    return out
