"""Data models for the LLM adapter layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    prompt: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    model: str = "gpt-4o"


class LLMResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached: bool = False
    prompt_hash: str = ""
