"""
OpenAI-compatible LLM provider.

Works with any API that speaks the OpenAI Chat Completions protocol:
  - OpenAI      (base_url=https://api.openai.com/v1)
  - Groq        (base_url=https://api.groq.com/openai/v1)         -- free tier
  - Google      (base_url=https://generativelanguage.googleapis.com/v1beta/openai)  -- free tier
  - OpenRouter  (base_url=https://openrouter.ai/api/v1)           -- free models

Temperature is forced to 0 at the adapter level for system-wide determinism.
"""

from __future__ import annotations

import hashlib
import os

from shared.llm_adapter.base import LLMProvider
from shared.llm_adapter.models import LLMRequest, LLMResponse

_BASE_URLS: dict[str, str] = {
    "openai":     "https://api.openai.com/v1",
    "groq":       "https://api.groq.com/openai/v1",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
}

_DEFAULT_MODELS: dict[str, str] = {
    "openai":     "gpt-4o-mini",
    "groq":       "llama-3.3-70b-versatile",
    "gemini":     "gemini-2.0-flash",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
}


class OpenAIProvider(LLMProvider):
    """
    OpenAI Chat Completions adapter.

    Reads from env:
      LLM_PROVIDER  -- selects base_url and default model
      LLM_API_KEY   -- API key (also checked as OPENAI_API_KEY for compatibility)
      LLM_MODEL     -- override the default model for the provider
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider_name: str = "openai",
    ) -> None:
        self._provider_name = provider_name

        self._api_key = (
            api_key
            or os.environ.get("LLM_API_KEY", "")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        # Local providers (e.g. Ollama / LM Studio) often don't require a key.
        # In that case we generate a dummy one so the OpenAI client is happy.
        if not self._api_key and provider_name == "local":
            self._api_key = "local-placeholder-key"
        elif not self._api_key:
            raise ValueError(
                f"An API key is required for provider '{provider_name}'. "
                "Set LLM_API_KEY (or OPENAI_API_KEY) in your environment."
            )

        self._base_url = (
            base_url
            or os.environ.get("LLM_BASE_URL", "")
            or _BASE_URLS.get(provider_name, _BASE_URLS["openai"])
        )

        self._model = (
            model
            or os.environ.get("LLM_MODEL", "")
            or _DEFAULT_MODELS.get(provider_name, "gpt-4o-mini")
        )

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package is required. Install it with: pip install openai"
            ) from exc

        timeout = float(os.environ.get("LLM_REQUEST_TIMEOUT", "120"))
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=timeout,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt_hash = hashlib.sha256(request.prompt.encode()).hexdigest()

        model = self._model if request.model in ("", "gpt-4o") else request.model

        response = await self._client.chat.completions.create(
            model=model,
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
