"""
Deterministic mock LLM provider for testing and development.

Always returns the same output for the same prompt hash,
making the entire pipeline reproducible without network calls.
"""

from __future__ import annotations

import hashlib

from shared.llm_adapter.base import LLMProvider
from shared.llm_adapter.models import LLMRequest, LLMResponse

_MOCK_PREFIX = "[MOCK] "


class MockProvider(LLMProvider):

    def __init__(self) -> None:
        self._call_count = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self._call_count += 1
        prompt_hash = hashlib.sha256(request.prompt.encode()).hexdigest()

        content = (
            f"{_MOCK_PREFIX}Deterministic response for prompt hash "
            f"{prompt_hash[:12]}. Call #{self._call_count}."
        )

        fake_prompt_tokens = len(request.prompt.split())
        fake_completion_tokens = len(content.split())

        return LLMResponse(
            content=content,
            model="mock-deterministic",
            prompt_tokens=fake_prompt_tokens,
            completion_tokens=fake_completion_tokens,
            total_tokens=fake_prompt_tokens + fake_completion_tokens,
            cached=False,
            prompt_hash=prompt_hash,
        )
