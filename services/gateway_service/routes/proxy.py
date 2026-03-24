from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from shared.plan_idempotency import plan_idempotency_key_gateway
from shared.contracts.events import (
    PlanRevisionPayload,
    plan_revision_confirmed,
)
from services.gateway_service.constants import PLAN_IDEM_TTL_SECONDS, SERVICE_NAME
from services.gateway_service.deps import get_gateway_runtime
from services.gateway_service.plan_aggregate import (
    aggregate_plan_metrics,
    build_plan_detail_json_response,
)
from services.gateway_service.runtime import GatewayRuntime

router = APIRouter(prefix="/api", tags=["proxy"])
logger = logging.getLogger(SERVICE_NAME)


def _proxy_json(resp: Any) -> dict[str, Any]:
    text = (resp.text or "").strip()
    if not text:
        return {"error": "Upstream returned empty response", "status": resp.status_code}
    try:
        return resp.json()
    except Exception as e:
        return {"error": f"Invalid upstream response: {e}", "body_preview": text[:200]}


@router.post("/plan")
async def create_plan(
    request_body: dict[str, Any],
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    try:
        key = plan_idempotency_key_gateway(request_body)
        now = time.monotonic()
        if key in rt.plan_idem_cache:
            cached_content, cached_at = rt.plan_idem_cache[key]
            if now - cached_at < PLAN_IDEM_TTL_SECONDS:
                logger.info(
                    "Plan idempotent (same request within %ds), returning cached response",
                    PLAN_IDEM_TTL_SECONDS,
                )
                return JSONResponse(content=cached_content, status_code=200)
            del rt.plan_idem_cache[key]

        resp = await rt.http_client.post(
            f"{rt.cfg.meta_planner_url}/plan",
            json=request_body,
        )
        content = _proxy_json(resp)
        if resp.status_code == 200 and isinstance(content, dict) and "plan_id" in content:
            rt.plan_idem_cache[key] = (content, now)
        return JSONResponse(content=content, status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/plan")
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@router.post("/agent_ask")
async def agent_ask(
    request_body: dict[str, Any],
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    """
    Q&A over pipeline semantic memory (and optional plan events).
    Body: { "question": str, "plan_id"?: str, "user_locale"?: str }
    """
    try:
        resp = await rt.http_client.post(
            f"{rt.cfg.meta_planner_url}/ask",
            json=request_body,
        )
        content = _proxy_json(resp)
        return JSONResponse(content=content, status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/agent_ask")
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@router.post("/replan")
async def confirm_replan(
    request_body: dict[str, Any],
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    try:
        payload = PlanRevisionPayload.model_validate(request_body)
    except Exception as exc:
        return JSONResponse(
            content={"error": f"Invalid PlanRevisionPayload: {exc}"},
            status_code=400,
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
):
    try:
        params: dict[str, str | int] = {"limit": limit}
        if event_type:
            params["event_type"] = event_type
        if plan_id:
            params["plan_id"] = plan_id
        resp = await rt.http_client.get(
            f"{rt.cfg.memory_service_url}/events",
            params=params,
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/events")
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@router.get("/tasks/{plan_id}")
async def get_tasks(
    plan_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    try:
        resp = await rt.http_client.get(
            f"{rt.cfg.memory_service_url}/tasks/{plan_id}"
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/tasks/%s", plan_id)
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@router.get("/plan_metrics/{plan_id}")
async def get_plan_metrics(
    plan_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    return await aggregate_plan_metrics(rt, plan_id)


@router.get("/plan_detail/{plan_id}")
async def get_plan_detail(
    plan_id: str,
    rt: GatewayRuntime = Depends(get_gateway_runtime),
):
    return await build_plan_detail_json_response(rt, plan_id)
