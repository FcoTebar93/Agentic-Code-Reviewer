"""Gateway: rutas de salud con TestClient y runtime en memoria (sin RabbitMQ)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.gateway_service.routes.health import router as gateway_health_router


def _make_minimal_gateway_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.gateway_runtime = SimpleNamespace(
            manager=SimpleNamespace(connection_count=7),
            pending_approvals={"approval-1": object()},
        )
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(gateway_health_router)
    return app


def test_gateway_health_and_status_reflect_runtime() -> None:
    app = _make_minimal_gateway_app()
    with TestClient(app) as client:
        h = client.get("/health")
        assert h.status_code == 200
        data = h.json()
        assert data["status"] == "ok"
        assert data["service"] == "gateway_service"
        assert data["ws_connections"] == 7
        assert data["pending_approvals"] == 1

        s = client.get("/api/status")
        assert s.status_code == 200
        st = s.json()
        assert st["ws_connections"] == 7
        assert st["pending_approvals"] == 1


def test_gateway_metrics_endpoint_returns_plaintext() -> None:
    app = _make_minimal_gateway_app()
    with TestClient(app) as client:
        m = client.get("/metrics")
        assert m.status_code == 200
        assert "text/plain" in (m.headers.get("content-type") or "").lower()
