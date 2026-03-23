"""Factory for `httpx.AsyncClient` with consistent timeout handling across services."""

from __future__ import annotations

import os
from typing import Any

import httpx

from shared.correlation import correlation_http_headers


def _inject_correlation_request_header(request: httpx.Request) -> None:
    for name, value in correlation_http_headers().items():
        if name not in request.headers:
            request.headers[name] = value


def create_async_http_client(
    *,
    base_url: str | None = None,
    default_timeout: float = 120.0,
    timeout_env_var: str | None = None,
    inject_correlation_headers: bool = True,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """
    Build an AsyncClient. If `timeout_env_var` is set, read timeout from that env
    (fallback `default_timeout`). Otherwise use `default_timeout`.

    When `inject_correlation_headers` is True (default), merges X-ADMADC-* from
    contextvars into each outgoing request (see shared.correlation).
    Disable with inject_correlation_headers=False or ADMADC_HTTP_CORRELATION=false.
    """
    if timeout_env_var:
        timeout = float(os.environ.get(timeout_env_var, str(default_timeout)))
    else:
        timeout = default_timeout

    hooks_in: dict[str, list] = dict(kwargs.pop("event_hooks", None) or {})
    client_kw: dict[str, Any] = {"timeout": timeout, **kwargs}
    if base_url:
        client_kw["base_url"] = base_url

    corr_on = inject_correlation_headers and os.environ.get(
        "ADMADC_HTTP_CORRELATION", "true"
    ).lower() in ("1", "true", "yes")
    if corr_on:
        req_hooks = list(hooks_in.get("request", []))
        req_hooks.append(_inject_correlation_request_header)
        hooks_in["request"] = req_hooks
    if hooks_in:
        client_kw["event_hooks"] = hooks_in

    return httpx.AsyncClient(**client_kw)
