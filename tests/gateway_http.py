"""Helpers HTTP del gateway (parseo de respuestas upstream)."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from services.gateway_service.http_helpers import (
    error_response,
    parse_json_response,
)


class _FakeResp:
    __slots__ = ("status_code", "text", "_parsed", "_json_raises")

    def __init__(
        self,
        *,
        text: str = "",
        status_code: int = 200,
        parsed: Any | None = None,
        json_raises: bool = False,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._parsed = parsed
        self._json_raises = json_raises

    def json(self) -> Any:
        if self._json_raises:
            raise ValueError("bad json")
        if self._parsed is not None:
            return self._parsed
        raise ValueError("no parsed")


def test_parse_json_response_invalid_json_calls_json() -> None:
    out = parse_json_response(
        _FakeResp(text="{not-json", status_code=200, json_raises=True),
        locale="en",
    )
    assert out["code"] == "invalid_upstream_response"
    assert out["error"] == "The upstream service returned an invalid response."


def test_parse_json_response_empty_body() -> None:
    out = parse_json_response(_FakeResp(text="", status_code=504), locale="es")
    assert out["status"] == 504
    assert out["code"] == "upstream_empty_response"


def test_parse_json_response_valid_json() -> None:
    out = parse_json_response(
        _FakeResp(text='{"x": 1}', status_code=200, parsed={"x": 1})
    )
    assert out == {"x": 1}


def test_error_response_default_status() -> None:
    r = error_response("boom", locale="en")
    assert isinstance(r, JSONResponse)
    assert r.status_code == 502


def test_error_response_custom_status() -> None:
    r = error_response(
        "Forbidden",
        status_code=400,
        locale="es",
        code="forbidden",
    )
    assert r.status_code == 400
    assert b"No tienes permisos" in r.body


def test_parse_json_response_normalizes_known_upstream_detail() -> None:
    out = parse_json_response(
        _FakeResp(
            text='{"detail":"question must be non-empty"}',
            status_code=400,
            parsed={"detail": "question must be non-empty"},
        ),
        locale="es",
    )
    assert out["code"] == "question_required"
    assert out["detail"] == "La pregunta no puede estar vacía."
