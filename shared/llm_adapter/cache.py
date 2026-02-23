"""
LLM response caching layer.

Wraps any LLMProvider with a prompt-hash-based cache. Identical prompts
return cached responses without calling the underlying provider, guaranteeing
determinism and saving tokens.

Two backends:
- In-memory dict (default, for dev/testing)
- Redis (for production across service restarts)
"""

from __future__ import annotations

import hashlib
import json
import logging

from shared.llm_adapter.base import LLMProvider
from shared.llm_adapter.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class CachedLLMProvider(LLMProvider):
    """Decorator that adds caching around any LLMProvider."""

    def __init__(
        self,
        inner: LLMProvider,
        redis_url: str | None = None,
    ) -> None:
        self._inner = inner
        self._local_cache: dict[str, str] = {}
        self._redis = None

        if redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    redis_url, decode_responses=True
                )
            except ImportError:
                logger.warning(
                    "redis package not available; falling back to in-memory cache"
                )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        cache_key = self._make_key(request)

        cached = await self._get(cache_key)
        if cached:
            logger.debug("LLM cache HIT for key %s", cache_key[:16])
            response = LLMResponse.model_validate_json(cached)
            response.cached = True
            return response

        logger.debug("LLM cache MISS for key %s", cache_key[:16])
        response = await self._inner.generate(request)

        await self._set(cache_key, response.model_dump_json())
        return response

    @staticmethod
    def _make_key(request: LLMRequest) -> str:
        raw = json.dumps(
            {
                "prompt": request.prompt,
                "model": request.model,
                "max_tokens": request.max_tokens,
            },
            sort_keys=True,
        )
        return f"llm_cache:{hashlib.sha256(raw.encode()).hexdigest()}"

    async def _get(self, key: str) -> str | None:
        if self._redis:
            return await self._redis.get(key)
        return self._local_cache.get(key)

    async def _set(self, key: str, value: str) -> None:
        if self._redis:
            await self._redis.set(key, value, ex=86400)
        else:
            self._local_cache[key] = value
