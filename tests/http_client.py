"""Factoría `create_async_http_client` (timeouts y hooks opcionales)."""

from __future__ import annotations

import asyncio

import pytest

from shared.http.client import create_async_http_client


async def _async_timeout_case(
    monkeypatch: pytest.MonkeyPatch,
    *,
    env_name: str,
    env_value: str | None,
    default_timeout: float,
    expected: float,
) -> None:
    if env_value is None:
        monkeypatch.delenv(env_name, raising=False)
    else:
        monkeypatch.setenv(env_name, env_value)
    async with create_async_http_client(
        timeout_env_var=env_name,
        default_timeout=default_timeout,
        inject_correlation_headers=False,
    ) as client:
        assert float(client.timeout.connect) == pytest.approx(expected)


def test_create_async_http_client_uses_timeout_env(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(
        _async_timeout_case(
            monkeypatch,
            env_name="ADMADC_UNIT_HTTP_TIMEOUT",
            env_value="77",
            default_timeout=3.0,
            expected=77.0,
        )
    )


def test_create_async_http_client_fallback_default(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(
        _async_timeout_case(
            monkeypatch,
            env_name="ADMADC_UNIT_HTTP_TIMEOUT_UNUSED",
            env_value=None,
            default_timeout=12.5,
            expected=12.5,
        )
    )
