"""Fixtures y utilidades para E2E (requieren `ADMADC_E2E=1` y stack en ejecución)."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable, Generator
from typing import Any, TypeVar

import httpx
import pytest


def e2e_enabled() -> bool:
    raw = os.environ.get("ADMADC_E2E", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def scenario_flag_enabled(env_var: str) -> bool:
    return os.environ.get(env_var, "").strip().lower() in ("1", "true", "yes", "on")


def unique_plan_body(prompt_suffix: str = "") -> dict[str, Any]:
    token = str(uuid.uuid4())
    suffix = prompt_suffix.strip()
    prompt = f"E2E {token[:8]} {suffix}".strip()
    return {
        "prompt": prompt,
        "project_name": f"e2e-{token[:8]}",
        "repo_url": "",
        "mode": "normal",
        "user_locale": "en",
    }


def gateway_base_url() -> str:
    return os.environ.get("ADMADC_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")


def e2e_timeout_seconds() -> float:
    return float(os.environ.get("ADMADC_E2E_TIMEOUT", "180"))


def approval_headers() -> dict[str, str]:
    token = os.environ.get("ADMADC_E2E_APPROVAL_TOKEN", "").strip()
    if token:
        return {"X-Approval-Token": token}
    return {}


@pytest.fixture(scope="module")
def gateway_url() -> str:
    return gateway_base_url()


@pytest.fixture
def e2e_client(gateway_url: str) -> Generator[httpx.Client, None, None]:
    if not e2e_enabled():
        pytest.skip("Define ADMADC_E2E=1 y levanta el stack (docker compose up).")
    ping_timeout = httpx.Timeout(8.0, connect=3.0)
    try:
        with httpx.Client(base_url=gateway_url, timeout=ping_timeout) as ping:
            r = ping.get("/health")
        if r.status_code != 200:
            pytest.fail(
                f"Gateway no saludable en {gateway_url}: HTTP {r.status_code}"
            )
    except httpx.RequestError as exc:
        pytest.fail(
            f"No se pudo conectar al Gateway en {gateway_url}: {exc}. "
            "¿Está `docker compose up` y el puerto 8080 expuesto?"
        )
    timeout = httpx.Timeout(e2e_timeout_seconds(), connect=15.0)
    with httpx.Client(base_url=gateway_url, timeout=timeout) as client:
        yield client


@pytest.fixture
def e2e_security_block_scenario() -> None:
    """Requiere `ADMADC_MOCK_CODEGEN_INJECT_EVAL=true` en el contenedor dev_service."""
    if not scenario_flag_enabled("ADMADC_E2E_SCENARIO_SECURITY_BLOCK"):
        pytest.skip(
            "ADMADC_E2E_SCENARIO_SECURITY_BLOCK=1 y dev_service con "
            "ADMADC_MOCK_CODEGEN_INJECT_EVAL=true (p. ej. compose override)."
        )


@pytest.fixture
def e2e_qa_fail_scenario() -> None:
    """Requiere `ADMADC_MOCK_QA_FORCE_FAIL=true` en el contenedor qa_service."""
    if not scenario_flag_enabled("ADMADC_E2E_SCENARIO_QA_FAIL"):
        pytest.skip(
            "ADMADC_E2E_SCENARIO_QA_FAIL=1 y qa_service con "
            "ADMADC_MOCK_QA_FORCE_FAIL=true (p. ej. compose override)."
        )


_T = TypeVar("_T")


def fetch_plan_events(
    client: httpx.Client, plan_id: str, *, limit: int = 200
) -> list[dict[str, Any]]:
    r = client.get("/api/events", params={"plan_id": plan_id, "limit": limit})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list), body
    return body


def event_types(events: list[dict[str, Any]]) -> set[str]:
    return {str(e.get("event_type", "")) for e in events}


def poll_until(
    fn: Callable[[], _T | None],
    *,
    timeout_s: float,
    interval_s: float = 0.5,
    description: str = "condición",
) -> _T:
    deadline = time.monotonic() + timeout_s
    last_exc: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            value = fn()
            if value is not None:
                return value
        except BaseException as exc:
            last_exc = exc
        time.sleep(interval_s)
    msg = f"Timeout esperando {description} ({timeout_s}s)"
    if last_exc:
        msg += f"; último error: {last_exc}"
    pytest.fail(msg)
