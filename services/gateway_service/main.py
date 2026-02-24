"""
Gateway Service -- single entry point for the React frontend.

Responsibilities:
1. WebSocket /ws  -- subscribe to ALL RabbitMQ events and broadcast to clients
2. POST /api/plan -- proxy to meta_planner
3. GET  /api/events -- proxy to memory_service
4. GET  /api/tasks/{plan_id} -- proxy to memory_service
5. GET  /api/status -- current pipeline state (connections + recent events)
6. HITL approval endpoints:
   GET  /api/approvals          -- list pending human approvals
   POST /api/approvals/{id}/approve -- approve a PR (publishes pr.human_approved)
   POST /api/approvals/{id}/reject  -- reject a PR (publishes pr.human_rejected)

Design: the gateway intercepts security.approved events and holds them for
human review before forwarding to github_service via pr.human_approved.
All other events are forwarded transparently.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response
from shared.contracts.events import (
    BaseEvent,
    EventType,
    SecurityResultPayload,
    PrApprovalPayload,
    PipelineConclusionPayload,
    pr_pending_approval,
    pr_human_approved,
    pr_human_rejected,
    pipeline_conclusion,
)
from shared.utils.rabbitmq import EventBus
from services.gateway_service.config import GatewayConfig
from services.gateway_service.ws_manager import ConnectionManager

SERVICE_NAME = "gateway_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: GatewayConfig | None = None
manager = ConnectionManager()

_pending_approvals: dict[str, PrApprovalPayload] = {}


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = GatewayConfig.from_env()
    http_client = httpx.AsyncClient(timeout=30.0)

    event_bus = EventBus(cfg.rabbitmq_url)

    async def _connect_and_consume():
        await event_bus.connect()
        asyncio.create_task(_consume_all_events())
        asyncio.create_task(_consume_security_approved())
        logger.info("Gateway RabbitMQ consumers active")

    asyncio.create_task(_connect_and_consume())
    logger.info("Gateway Service ready — WebSocket broadcast + HITL approval active")
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Gateway Service",
    version="0.2.0",
    description="WebSocket gateway, HTTP proxy, and Human-in-the-Loop approval system",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "ws_connections": manager.connection_count,
        "pending_approvals": len(_pending_approvals),
    }


@app.get("/metrics")
async def metrics():
    return metrics_response()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        if http_client and cfg:
            try:
                resp = await http_client.get(
                    f"{cfg.memory_service_url}/events",
                    params={"limit": 20},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("value", data) if isinstance(data, dict) else data
                    for evt in reversed(events[:20]):
                        await websocket.send_text(
                            json.dumps({"type": "history", "event": evt})
                        )
            except Exception:
                logger.warning("Could not fetch history for new WebSocket client")

        for approval in _pending_approvals.values():
            await websocket.send_text(
                json.dumps({"type": "approval", "approval": approval.model_dump()})
            )

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket error")
        manager.disconnect(websocket)

def _proxy_json(resp: Any) -> dict[str, Any]:
    """Parse JSON response; avoid 'Expecting value' when upstream returns empty/non-JSON."""
    text = (resp.text or "").strip()
    if not text:
        return {"error": "Upstream returned empty response", "status": resp.status_code}
    try:
        return resp.json()
    except Exception as e:
        return {"error": f"Invalid upstream response: {e}", "body_preview": text[:200]}


@app.post("/api/plan")
async def create_plan(request_body: dict[str, Any]):
    """Proxy POST /plan to meta_planner."""
    try:
        resp = await http_client.post(
            f"{cfg.meta_planner_url}/plan",
            json=request_body,
        )
        return JSONResponse(content=_proxy_json(resp), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/plan")
        return JSONResponse(
            content={"error": str(exc)}, status_code=502
        )


@app.get("/api/events")
async def get_events():
    """Proxy GET /events to memory_service."""
    try:
        resp = await http_client.get(f"{cfg.memory_service_url}/events")
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/events")
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@app.get("/api/tasks/{plan_id}")
async def get_tasks(plan_id: str):
    """Proxy GET /tasks/{plan_id} to memory_service."""
    try:
        resp = await http_client.get(
            f"{cfg.memory_service_url}/tasks/{plan_id}"
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/tasks/%s", plan_id)
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@app.get("/api/status")
async def get_status():
    return {
        "ws_connections": manager.connection_count,
        "pending_approvals": len(_pending_approvals),
        "service": SERVICE_NAME,
    }

@app.get("/api/approvals")
async def list_approvals():
    """Return all pending human approvals."""
    return {
        "pending": [a.model_dump() for a in _pending_approvals.values()],
        "count": len(_pending_approvals),
    }


@app.post("/api/approvals/{approval_id}/approve")
async def approve_pr(approval_id: str):
    """
    Human approves a PR.
    Publishes pr.human_approved and forwards to github_service via RabbitMQ.
    """
    approval = _pending_approvals.get(approval_id)
    if not approval:
        return JSONResponse(
            content={"error": f"Approval {approval_id} not found or already decided"},
            status_code=404,
        )

    approval.decision = "approved"
    _pending_approvals.pop(approval_id, None)

    event = pr_human_approved(SERVICE_NAME, approval)
    await event_bus.publish(event)

    await manager.broadcast(
        json.dumps({"type": "approval_decided", "approval": approval.model_dump()})
    )
    await manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )

    logger.info(
        "Human APPROVED PR for plan %s (approval %s)",
        approval.plan_id[:8],
        approval_id[:8],
    )
    return {"status": "approved", "plan_id": approval.plan_id}


@app.post("/api/approvals/{approval_id}/reject")
async def reject_pr(approval_id: str):
    """
    Human rejects a PR.
    Publishes pr.human_rejected and removes the pending approval.
    """
    approval = _pending_approvals.get(approval_id)
    if not approval:
        return JSONResponse(
            content={"error": f"Approval {approval_id} not found or already decided"},
            status_code=404,
        )

    approval.decision = "rejected"
    _pending_approvals.pop(approval_id, None)

    event = pr_human_rejected(SERVICE_NAME, approval)
    await event_bus.publish(event)

    await manager.broadcast(
        json.dumps({"type": "approval_decided", "approval": approval.model_dump()})
    )
    await manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )

    logger.info(
        "Human REJECTED PR for plan %s (approval %s)",
        approval.plan_id[:8],
        approval_id[:8],
    )
    return {"status": "rejected", "plan_id": approval.plan_id}

async def _consume_all_events() -> None:
    """Broadcast every event on the bus to connected WebSocket clients."""

    async def handler(event: BaseEvent) -> None:
        payload = json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
        await manager.broadcast(payload)
        logger.debug(
            "Broadcast %s to %d clients",
            event.event_type.value,
            manager.connection_count,
        )

    await event_bus.subscribe(
        queue_name="gateway_service.broadcast",
        routing_keys=["#"],
        handler=handler,
        max_retries=1,
    )


async def _consume_security_approved() -> None:
    """
    Intercept security.approved events to create pending human approvals.

    Instead of letting github_service react directly to security.approved,
    the gateway holds the approval request until a human reviews it
    via the frontend and clicks Approve or Reject.
    """

    async def handler(event: BaseEvent) -> None:
        sec = SecurityResultPayload.model_validate(event.payload)
        if not sec.approved or not sec.pr_context:
            return

        files_changed: list[str] = []
        pr_files = sec.pr_context.get("files")
        if isinstance(pr_files, list):
            for f in pr_files:
                if isinstance(f, dict) and "file_path" in f:
                    files_changed.append(str(f["file_path"]))

        conclusion_payload = PipelineConclusionPayload(
            plan_id=sec.plan_id,
            branch_name=sec.branch_name,
            conclusion_text=sec.reasoning,
            files_changed=files_changed,
            approved=sec.approved,
        )
        conclusion_event = pipeline_conclusion(SERVICE_NAME, conclusion_payload)
        await event_bus.publish(conclusion_event)
        try:
            await http_client.post(
                f"{cfg.memory_service_url}/events",
                json=json.loads(conclusion_event.model_dump_json()),
            )
        except Exception:
            logger.warning("Could not store pipeline.conclusion in memory_service")

        approval = PrApprovalPayload(
            plan_id=sec.plan_id,
            branch_name=sec.branch_name,
            files_count=sec.files_scanned,
            security_reasoning=sec.reasoning,
            pr_context=sec.pr_context,
        )
        _pending_approvals[approval.approval_id] = approval

        pending_event = pr_pending_approval(SERVICE_NAME, approval)
        await event_bus.publish(pending_event)

        await manager.broadcast(
            json.dumps({"type": "approval", "approval": approval.model_dump()})
        )

        logger.info(
            "PR approval pending for plan %s (approval_id %s). "
            "Waiting for human decision.",
            sec.plan_id[:8],
            approval.approval_id[:8],
        )

    await event_bus.subscribe(
        queue_name="gateway_service.hitl_approvals",
        routing_keys=[EventType.SECURITY_APPROVED.value],
        handler=handler,
        max_retries=1,
    )
