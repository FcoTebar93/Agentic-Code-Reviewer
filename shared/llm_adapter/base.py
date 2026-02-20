"""Abstract base class that all LLM providers must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.llm_adapter.models import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """
    Contract for LLM providers.

    Every implementation MUST:
    - Honour temperature=0 for determinism (enforced in generate wrapper)
    - Return a fully populated LLMResponse including token counts
    """

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a prompt and return the model's response."""

    async def generate_text(self, prompt: str, **kwargs) -> LLMResponse:
        """Convenience wrapper: accepts a plain string prompt."""
        request = LLMRequest(prompt=prompt, temperature=0.0, **kwargs)
        return await self.generate(request)
