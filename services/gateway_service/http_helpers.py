from __future__ import annotations

import logging
from typing import Any

from fastapi.responses import JSONResponse


def parse_json_response(resp: Any) -> Any:
    text = (resp.text or "").strip()
    if not text:
        return {"error": "Upstream returned empty response", "status": resp.status_code}
    try:
        return resp.json()
    except Exception as exc:
        return {"error": f"Invalid upstream response: {exc}", "body_preview": text[:200]}


async def proxy_json_request(
    *,
    logger: logging.Logger,
    log_context: str,
    request_call,
) -> JSONResponse:
    try:
        resp = await request_call()
        return JSONResponse(content=parse_json_response(resp), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy %s", log_context)
        return JSONResponse(content={"error": str(exc)}, status_code=502)
