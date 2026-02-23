"""
Gateway Service -- single entry point for the React frontend.

Responsibilities:
1. WebSocket /ws  -- subscribe to ALL RabbitMQ events and broadcast to clients
2. POST /api/plan -- proxy to meta_planner
3. GET  /api/events -- proxy to memory_service
4. GET  /api/tasks/{plan_id} -- proxy to memory_service
5. GET  /api/status -- current pipeline state (connections + recent events)

Design: the gateway never processes events, only forwards them.
This keeps it stateless and easy to scale horizontally.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response
from shared.contracts.events import BaseEvent
from shared.utils.rabbitmq import EventBus
from services.gateway_service.config import GatewayConfig
from services.gateway_service.ws_manager import ConnectionManager

SERVICE_NAME = "gateway_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: GatewayConfig | None = None
manager = ConnectionManager()


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = GatewayConfig.from_env()
    http_client = httpx.AsyncClient(timeout=30.0)

    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_all_events())
    logger.info("Gateway Service ready — WebSocket broadcast active")
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Gateway Service",
    version="0.1.0",
    description="WebSocket gateway and HTTP proxy for the React frontend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(SERVICE_NAME)


# ---------------------------------------------------------------------------
# Health & metrics
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "ws_connections": manager.connection_count,
    }


@app.get("/metrics")
async def metrics():
    return metrics_response()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send last 20 events so the client has context on connect
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

        # Keep the connection alive; events arrive via broadcast() from _consume_all_events
        while True:
            # Wait for any incoming message (ping/pong or client disconnect)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket error")
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# HTTP API proxy endpoints
# ---------------------------------------------------------------------------


@app.post("/api/plan")
async def create_plan(request_body: dict[str, Any]):
    """Proxy POST /plan to meta_planner."""
    try:
        resp = await http_client.post(
            f"{cfg.meta_planner_url}/plan",
            json=request_body,
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
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
        "service": SERVICE_NAME,
    }


# ---------------------------------------------------------------------------
# RabbitMQ consumer — broadcast all events to WebSocket clients
# ---------------------------------------------------------------------------


async def _consume_all_events() -> None:
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
