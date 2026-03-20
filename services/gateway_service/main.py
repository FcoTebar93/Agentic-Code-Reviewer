"""
Gateway Service -- single entry point for the React frontend.

Composition root: FastAPI app, CORS, lifespan, routers, WebSocket /ws.
Domain logic lives in plan_aggregate, consumers, and route modules.
"""

from __future__ import annotations

import asyncio
import json
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from shared.http.client import create_async_http_client
from shared.logging.logger import setup_logging
from shared.utils import EventBus
from services.gateway_service.config import GatewayConfig
from services.gateway_service.constants import SERVICE_NAME
from services.gateway_service.consumers import consume_all_events, consume_security_approved
from services.gateway_service.runtime import GatewayRuntime
from services.gateway_service.routes import (
    approvals_router,
    health_router,
    proxy_router,
)
from services.gateway_service.ws_manager import ConnectionManager

logger = logging.getLogger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(application: FastAPI):
    log = setup_logging(SERVICE_NAME)
    cfg = GatewayConfig.from_env()
    http_client = create_async_http_client(
        timeout_env_var="GATEWAY_HTTP_TIMEOUT",
        default_timeout=120.0,
    )
    event_bus = EventBus(cfg.rabbitmq_url)
    runtime = GatewayRuntime(
        event_bus=event_bus,
        http_client=http_client,
        cfg=cfg,
        manager=ConnectionManager(),
    )
    application.state.gateway_runtime = runtime

    async def _connect_and_consume() -> None:
        await runtime.event_bus.connect()
        asyncio.create_task(consume_all_events(runtime, log))
        asyncio.create_task(consume_security_approved(runtime, log))
        log.info("Gateway RabbitMQ consumers active")

    asyncio.create_task(_connect_and_consume())
    log.info("Gateway Service ready — WebSocket broadcast + HITL approval active")
    yield
    log.info("Shutting down")
    await runtime.event_bus.close()
    await runtime.http_client.aclose()


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

app.include_router(health_router)
app.include_router(proxy_router)
app.include_router(approvals_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    rt: GatewayRuntime = websocket.app.state.gateway_runtime
    await rt.manager.connect(websocket)
    try:
        if rt.http_client and rt.cfg:
            try:
                resp = await rt.http_client.get(
                    f"{rt.cfg.memory_service_url}/events",
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

        for approval in rt.pending_approvals.values():
            await websocket.send_text(
                json.dumps({"type": "approval", "approval": approval.model_dump()})
            )

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        rt.manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket error")
        rt.manager.disconnect(websocket)
