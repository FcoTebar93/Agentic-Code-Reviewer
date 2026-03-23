"""Data models for the LLM adapter layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class LLMRequest(BaseModel):
    """
    Single-turn: set `prompt` (default) and leave `messages` unset.

    Multi-turn / tools: set `messages` to a Chat Completions–style list
    (`role` / `content` / optional `tool_calls` / `tool_call_id`).
    When `messages` is set, `prompt` may be empty.
    """

    prompt: str = ""
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    model: str = "gpt-4o"
    messages: list[dict[str, Any]] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _require_prompt_or_messages(self) -> LLMRequest:
        has_prompt = bool(self.prompt and self.prompt.strip())
        has_messages = bool(self.messages)
        if not has_prompt and not has_messages:
            raise ValueError("LLMRequest requires non-empty prompt or messages")
        return self


class LLMResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached: bool = False
    prompt_hash: str = ""
    tool_calls: list[dict[str, Any]] | None = None
