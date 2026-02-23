"""
OpenAI LLM provider.

Enforces temperature=0 at the adapter level regardless of what the caller
passes, ensuring system-wide determinism.
"""

from __future__ import annotations

import hashlib
import os

from shared.llm_adapter.base import LLMProvider
from shared.llm_adapter.models import LLMRequest, LLMResponse


class OpenAIProvider(LLMProvider):

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OPENAI_API_KEY must be set when using OpenAIProvider"
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAIProvider. "
                "Install it with: pip install openai"
            ) from exc

        self._client = AsyncOpenAI(api_key=self._api_key)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt_hash = hashlib.sha256(request.prompt.encode()).hexdigest()

        response = await self._client.chat.completions.create(
            model=request.model,
            temperature=0.0,
            max_tokens=request.max_tokens,
            messages=[{"role": "user", "content": request.prompt}],
        )

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            cached=False,
            prompt_hash=prompt_hash,
        )
