"""
LLM provider.

Works with any API that speaks the OpenAI Chat Completions protocol:
  - OpenAI      (base_url=https://api.openai.com/v1)
  - Groq        (base_url=https://api.groq.com/openai/v1)         -- free tier
  - Google      (base_url=https://generativelanguage.googleapis.com/v1beta/openai)  -- free tier
  - OpenRouter  (base_url=https://openrouter.ai/api/v1)           -- free models

Temperature is forced to 0 at the adapter level for system-wide determinism.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

import httpx

from shared.llm_adapter.base import LLMProvider
from shared.llm_adapter.models import LLMRequest, LLMResponse
from shared.observability.metrics import llm_latency, llm_requests

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


def _chat_messages(request: LLMRequest) -> list[dict[str, Any]]:
    if request.messages is not None:
        return list(request.messages)
    return [{"role": "user", "content": request.prompt}]


def _normalize_tool_calls_from_json(
    raw: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not raw:
        return None
    out: list[dict[str, Any]] = []
    for tc in raw:
        fn = tc.get("function") or {}
        out.append(
            {
                "id": tc.get("id", ""),
                "type": tc.get("type") or "function",
                "function": {
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments") or "",
                },
            }
        )
    return out or None


def _normalize_tool_calls_from_sdk(raw: Any) -> list[dict[str, Any]] | None:
    if not raw:
        return None
    out: list[dict[str, Any]] = []
    for tc in raw:
        out.append(
            {
                "id": tc.id,
                "type": getattr(tc, "type", None) or "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "",
                },
            }
        )
    return out or None


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

        timeout = float(os.environ.get("LLM_REQUEST_TIMEOUT", "120"))

        if provider_name == "local":
            self._use_raw_http = True
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
            )
        else:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise ImportError(
                    "openai package is required. Install it with: pip install openai"
                ) from exc

            self._use_raw_http = False
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=timeout,
            )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate a completion with basic retry/backoff and outcome metrics.

        Outcomes:
        - ok:      request succeeded
        - timeout: HTTP/transport timeout
        - error:   non-timeout error (4xx/5xx or client error)
        """
        messages = _chat_messages(request)
        key_material = request.prompt.encode()
        if request.messages is not None:
            key_material = json.dumps(messages, sort_keys=True).encode()
        prompt_hash = hashlib.sha256(key_material).hexdigest()
        model = self._model if request.model in ("", "gpt-4o") else request.model
        provider = self._provider_name

        max_retries = int(os.environ.get("LLM_MAX_RETRIES", "2"))
        base_delay = float(os.environ.get("LLM_RETRY_DELAY_S", "1.0"))

        attempt = 0
        last_exc: Optional[Exception] = None

        with llm_latency.labels(service=provider).time():
            while attempt <= max_retries:
                try:
                    if getattr(self, "_use_raw_http", False):
                        payload: dict[str, Any] = {
                            "model": model,
                            "temperature": 0.0,
                            "max_tokens": request.max_tokens,
                            "messages": messages,
                        }
                        if request.tools:
                            payload["tools"] = request.tools
                            payload["tool_choice"] = (
                                request.tool_choice
                                if request.tool_choice is not None
                                else "auto"
                            )
                        if request.response_format is not None:
                            payload["response_format"] = request.response_format

                        resp = await self._http_client.post(
                            "/chat/completions",
                            json=payload,
                        )
                        resp.raise_for_status()
                        data = resp.json()

                        choice = data["choices"][0]
                        usage = data.get("usage") or {}
                        msg = choice.get("message") or {}
                        raw_tcs = msg.get("tool_calls")
                        tool_calls = _normalize_tool_calls_from_json(raw_tcs)

                        llm_requests.labels(
                            provider=provider,
                            model=model,
                            service=provider,
                            outcome="ok",
                        ).inc()

                        return LLMResponse(
                            content=(msg.get("content") or "") or "",
                            model=data.get("model", model),
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            total_tokens=usage.get("total_tokens", 0),
                            cached=False,
                            prompt_hash=prompt_hash,
                            tool_calls=tool_calls,
                        )

                    kwargs: dict[str, Any] = {
                        "model": model,
                        "temperature": 0.0,
                        "max_tokens": request.max_tokens,
                        "messages": messages,
                    }
                    if request.tools:
                        kwargs["tools"] = request.tools
                        kwargs["tool_choice"] = (
                            request.tool_choice
                            if request.tool_choice is not None
                            else "auto"
                        )
                    if request.response_format is not None:
                        kwargs["response_format"] = request.response_format

                    response = await self._client.chat.completions.create(**kwargs)

                    choice = response.choices[0]
                    usage = response.usage
                    msg = choice.message
                    tool_calls = _normalize_tool_calls_from_sdk(
                        getattr(msg, "tool_calls", None)
                    )

                    llm_requests.labels(
                        provider=provider,
                        model=model,
                        service=provider,
                        outcome="ok",
                    ).inc()

                    return LLMResponse(
                        content=msg.content or "",
                        model=response.model,
                        prompt_tokens=usage.prompt_tokens if usage else 0,
                        completion_tokens=usage.completion_tokens if usage else 0,
                        total_tokens=usage.total_tokens if usage else 0,
                        cached=False,
                        prompt_hash=prompt_hash,
                        tool_calls=tool_calls,
                    )
                except (httpx.TimeoutException, TimeoutError) as exc:
                    last_exc = exc
                    llm_requests.labels(
                        provider=provider,
                        model=model,
                        service=provider,
                        outcome="timeout",
                    ).inc()
                    if attempt >= max_retries:
                        raise
                except Exception as exc:
                    last_exc = exc
                    llm_requests.labels(
                        provider=provider,
                        model=model,
                        service=provider,
                        outcome="error",
                    ).inc()
                    if attempt >= max_retries:
                        raise

                attempt += 1
                delay = base_delay * attempt
                try:
                    import asyncio

                    await asyncio.sleep(delay)
                except Exception:
                    pass

        if last_exc:
            raise last_exc
        raise RuntimeError("LLM generate failed without explicit error")
