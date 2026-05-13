from __future__ import annotations

import logging
from typing import Any

from fastapi.responses import JSONResponse

from services.gateway_service.i18n import (
    build_localized_error_payload,
    normalize_error_content,
)


def parse_json_response(resp: Any, *, locale: str = "es") -> Any:
    text = (resp.text or "").strip()
    if not text:
        return build_localized_error_payload(
            locale=locale,
            code="upstream_empty_response",
            status=resp.status_code,
        )
    try:
        return normalize_error_content(resp.json(), locale)
    except Exception:
        return build_localized_error_payload(
            locale=locale,
            code="invalid_upstream_response",
            body_preview=text[:200],
        )


async def proxy_json_request(
    *,
    logger: logging.Logger,
    log_context: str,
    request_call,
    locale: str = "es",
) -> JSONResponse:
    try:
        resp = await request_call()
        return JSONResponse(
            content=parse_json_response(resp, locale=locale),
            status_code=resp.status_code,
        )
    except Exception as exc:
        logger.exception("Failed to proxy %s", log_context)
        return error_response(
            str(exc),
            status_code=502,
            code="gateway_proxy_failed",
            locale=locale,
        )


def error_response(
    message: str | None = None,
    *,
    status_code: int = 502,
    code: str | None = None,
    locale: str = "es",
    params: dict[str, Any] | None = None,
    field: str = "error",
    **extra: Any,
) -> JSONResponse:
    """Build a standard JSON error payload."""
    return JSONResponse(
        content=build_localized_error_payload(
            locale=locale,
            code=code,
            message=message,
            status=status_code,
            params=params,
            field=field,
            **extra,
        ),
        status_code=status_code,
    )
