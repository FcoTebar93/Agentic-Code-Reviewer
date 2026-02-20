"""
Provider factory -- single entry point for the entire system.

Reads LLM_PROVIDER from env (default: 'mock') and returns a
CachedLLMProvider wrapping the chosen backend.
"""

from __future__ import annotations

import os
import logging

from shared.llm_adapter.base import LLMProvider
from shared.llm_adapter.cache import CachedLLMProvider
from shared.llm_adapter.mock_provider import MockProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type] = {
    "mock": MockProvider,
}

_instance: LLMProvider | None = None


def _register_openai() -> None:
    """Lazy-register OpenAI only when selected, avoiding hard dependency."""
    from shared.llm_adapter.openai_provider import OpenAIProvider

    _PROVIDERS["openai"] = OpenAIProvider


def get_llm_provider(
    provider_name: str | None = None,
    redis_url: str | None = None,
) -> LLMProvider:
    """
    Return a singleton CachedLLMProvider for the configured backend.

    Args:
        provider_name: Override for LLM_PROVIDER env var.
        redis_url: If given, use Redis as the cache backend.

    Returns:
        A CachedLLMProvider wrapping the selected provider.
    """
    global _instance
    if _instance is not None:
        return _instance

    name = (provider_name or os.environ.get("LLM_PROVIDER", "mock")).lower()

    if name == "openai":
        _register_openai()

    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown LLM provider '{name}'. "
            f"Available: {list(_PROVIDERS.keys())}"
        )

    inner = provider_cls()
    cache_url = redis_url or os.environ.get("REDIS_URL")

    _instance = CachedLLMProvider(inner=inner, redis_url=cache_url)
    logger.info("LLM provider initialized: %s (cached=%s)", name, bool(cache_url))
    return _instance


def reset_provider() -> None:
    """Reset the singleton (for testing)."""
    global _instance
    _instance = None
