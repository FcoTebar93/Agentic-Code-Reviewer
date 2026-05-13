from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from services.gateway_service.constants import PLAN_IDEM_TTL_SECONDS, SERVICE_NAME
from services.gateway_service.deps import get_gateway_runtime
from services.gateway_service.http_helpers import (
    error_response,
    parse_json_response,
    proxy_json_request,
)
from services.gateway_service.i18n import resolve_request_locale
from services.gateway_service.plan_aggregate import (
    aggregate_plan_metrics,
    build_plan_detail_json_response,
)
from services.gateway_service.runtime import GatewayRuntime
from shared.contracts.events import (
    PlanRevisionPayload,
    plan_revision_confirmed,
)
from shared.plan_idempotency import plan_idempotency_key_gateway

router = APIRouter(prefix="/api", tags=["proxy"])
logger = logging.getLogger(SERVICE_NAME)


@router.post("/plan")
async def create_plan(
    request_body: dict[str, Any],
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    accept_language: str | None = Header(default=None),
):
    locale = resolve_request_locale(accept_language)
    try:
        request_payload = dict(request_body)
        request_payload.setdefault("user_locale", locale)
        key = plan_idempotency_key_gateway(request_payload)
        now = time.monotonic()
        cached = rt.plan_idem_cache.get(key)
        if cached:
            cached_content, cached_at = cached
            if now - cached_at < PLAN_IDEM_TTL_SECONDS:
                logger.info(
                    "Plan idempotent (same request within %ds), returning cached response",
                    PLAN_IDEM_TTL_SECONDS,
                )
                return JSONResponse(content=cached_content, status_code=200)
            del rt.plan_idem_cache[key]

        resp = await rt.http_client.post(
            f"{rt.cfg.meta_planner_url}/plan",
            json=request_payload,
        )
        content = parse_json_response(resp, locale=locale)
        if resp.status_code == 200 and isinstance(content, dict) and "plan_id" in content:
            rt.plan_idem_cache[key] = (content, now)
        return JSONResponse(content=content, status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/plan")
        return error_response(
            str(exc),
            status_code=502,
            code="gateway_proxy_failed",
            locale=locale,
        )


@router.post("/agent_ask")
async def agent_ask(
    request_body: dict[str, Any],
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    accept_language: str | None = Header(default=None),
):
    """Q&A over pipeline semantic memory (and optional plan events)."""
    locale = resolve_request_locale(accept_language)
    request_payload = dict(request_body)
    request_payload.setdefault("user_locale", locale)
    return await proxy_json_request(
        logger=logger,
        log_context="/api/agent_ask",
        locale=locale,
        request_call=lambda: rt.http_client.post(
            f"{rt.cfg.meta_planner_url}/ask",
            json=request_payload,
        ),
    )


@router.post("/replan")
async def confirm_replan(
    request_body: dict[str, Any],
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    accept_language: str | None = Header(default=None),
):
    locale = resolve_request_locale(accept_language)
    try:
        payload = PlanRevisionPayload.model_validate(request_body)
    except Exception as exc:
        return error_response(
            f"Invalid PlanRevisionPayload: {exc}",
            status_code=400,
            code="invalid_plan_revision_payload",
            locale=locale,
        )

    event = plan_revision_confirmed(SERVICE_NAME, payload)
    await rt.event_bus.publish(event)
    await rt.manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )

    return {
        "status": "ok",
        "original_plan_id": payload.original_plan_id,
        "new_plan_id": payload.new_plan_id,
    }


@router.get("/events")
async def get_events(
    limit: int = 50,
    event_type: str | None = None,
    plan_id: str | None = None,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    accept_language: str | None = Header(default=None),
):
    locale = resolve_request_locale(accept_language)
    params: dict[str, str | int] = {"limit": limit}
    if event_type is not None:
        params["event_type"] = event_type
    if plan_id is not None:
        params["plan_id"] = plan_id
    return await proxy_json_request(
        logger=logger,
        log_context="/api/events",
        locale=locale,
        request_call=lambda: rt.http_client.get(
            f"{rt.cfg.memory_service_url}/events",
            params=params,
        ),
    )


@router.get("/tasks/{plan_id}")
async def get_tasks(
    plan_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    accept_language: str | None = Header(default=None),
):
    locale = resolve_request_locale(accept_language)
    return await proxy_json_request(
        logger=logger,
        log_context=f"/api/tasks/{plan_id}",
        locale=locale,
        request_call=lambda: rt.http_client.get(
            f"{rt.cfg.memory_service_url}/tasks/{plan_id}"
        ),
    )


@router.get("/plan_metrics/{plan_id}")
async def get_plan_metrics(
    plan_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    accept_language: str | None = Header(default=None),
):
    return await aggregate_plan_metrics(
        rt,
        plan_id,
        locale=resolve_request_locale(accept_language),
    )


@router.get("/plan_detail/{plan_id}")
async def get_plan_detail(
    plan_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
    accept_language: str | None = Header(default=None),
):
    return await build_plan_detail_json_response(
        rt,
        plan_id,
        locale=resolve_request_locale(accept_language),
    )
