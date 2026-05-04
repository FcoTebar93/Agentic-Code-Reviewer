"""Registro estándar `/health` y `/metrics` (sin lifespan de servicios)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.observability.routing import register_health_metrics_routes


def test_register_health_metrics_exposes_ok_and_metrics() -> None:
    app = FastAPI()
    register_health_metrics_routes(app, "unit_test_service")
    with TestClient(app) as client:
        h = client.get("/health")
        assert h.status_code == 200
        body = h.json()
        assert body["status"] == "ok"
        assert body["service"] == "unit_test_service"

        m = client.get("/metrics")
        assert m.status_code == 200
        assert "text/plain" in (m.headers.get("content-type") or "").lower()
