"""FastAPI middleware: HTTP correlation headers → contextvars + echo trace on response."""

from __future__ import annotations

from fastapi import FastAPI, Request, Response

from shared.correlation import (
    HTTP_TRACE_HEADER,
    bind_correlation_from_http_headers,
    reset_correlation_tokens,
    trace_id_var,
)


def install_correlation_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _admadc_correlation(request: Request, call_next) -> Response:
        tokens = bind_correlation_from_http_headers(request.headers)
        try:
            response: Response = await call_next(request)
            tid = trace_id_var.get()
            if tid:
                response.headers[HTTP_TRACE_HEADER] = tid
            return response
        finally:
            reset_correlation_tokens(tokens)
