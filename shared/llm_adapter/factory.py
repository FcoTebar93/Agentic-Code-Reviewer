"""
Provider factory -- single entry point for the entire system.

Reads LLM_PROVIDER from env (default: 'mock') and returns a
CachedLLMProvider wrapping the chosen backend.

Supported providers:

  mock        Built-in contextual mock, no API key needed (default)
  openai      OpenAI API  -- needs OPENAI_API_KEY or LLM_API_KEY
  groq        Groq API    -- free tier, needs LLM_API_KEY
                            https://console.groq.com/keys
                            Default model: llama-3.3-70b-versatile
  gemini      Google AI   -- free tier, needs LLM_API_KEY
                            https://aistudio.google.com/apikey
                            Default model: gemini-2.0-flash
  openrouter  OpenRouter  -- free models available, needs LLM_API_KEY
                            https://openrouter.ai/keys
                            Default model: meta-llama/llama-3.3-70b-instruct:free
  local       Any OpenAI-compatible local server
                            e.g. Ollama / LM Studio (no key required)

All providers enforce temperature=0 for determinism.
Model can be overridden globally with the LLM_MODEL env var.
"""

from __future__ import annotations

import os
import logging

from shared.llm_adapter.base import LLMProvider
from shared.llm_adapter.cache import CachedLLMProvider
from shared.llm_adapter.mock_provider import MockProvider

logger = logging.getLogger(__name__)

_OPENAI_COMPATIBLE = {"openai", "groq", "gemini", "openrouter", "local"}

_PROVIDERS: dict[str, type] = {
    "mock": MockProvider,
}

_instance: LLMProvider | None = None


def _register_openai_compatible(name: str) -> None:
    """Lazy-register any OpenAI-compatible provider."""
    from shared.llm_adapter.openai_provider import OpenAIProvider

    def _factory() -> OpenAIProvider:
        return OpenAIProvider(provider_name=name)

    _PROVIDERS[name] = _factory


def get_llm_provider(
    provider_name: str | None = None,
    redis_url: str | None = None,
) -> LLMProvider:
    """
    Return a singleton CachedLLMProvider for the configured backend.

    Args:
        provider_name: Override for LLM_PROVIDER env var.
        redis_url:     If given, use Redis as the cache backend.
    """
    global _instance
    if _instance is not None:
        return _instance

    name = (provider_name or os.environ.get("LLM_PROVIDER", "mock")).lower()

    if name in _OPENAI_COMPATIBLE and name not in _PROVIDERS:
        _register_openai_compatible(name)

    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown LLM provider '{name}'. "
            f"Available: mock, openai, groq, gemini, openrouter, local"
        )

    inner = provider_cls()
    cache_url = redis_url or os.environ.get("REDIS_URL")

    _instance = CachedLLMProvider(inner=inner, redis_url=cache_url)
    logger.info(
        "LLM provider initialized: %s (model=%s, cached=%s)",
        name,
        os.environ.get("LLM_MODEL", "provider-default"),
        bool(cache_url),
    )
    return _instance


def reset_provider() -> None:
    """Reset the singleton (for testing)."""
    global _instance
    _instance = None
