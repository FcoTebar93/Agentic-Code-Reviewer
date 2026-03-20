"""Factory for `httpx.AsyncClient` with consistent timeout handling across services."""

from __future__ import annotations

import os
from typing import Any

import httpx


def create_async_http_client(*,base_url: str | None = None,default_timeout: float = 120.0,timeout_env_var: str | None = None,**kwargs: Any) -> httpx.AsyncClient:
    """
    Build an AsyncClient. If `timeout_env_var` is set, read timeout from that env
    (fallback `default_timeout`). Otherwise use `default_timeout`.
    """
    if timeout_env_var:
        timeout = float(os.environ.get(timeout_env_var, str(default_timeout)))
    else:
        timeout = default_timeout
    client_kw: dict[str, Any] = {"timeout": timeout, **kwargs}
    if base_url:
        client_kw["base_url"] = base_url
    return httpx.AsyncClient(**client_kw)
