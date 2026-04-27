from __future__ import annotations

from fastapi import FastAPI

from shared.observability.metrics import metrics_response


def register_health_metrics_routes(app: FastAPI, service_name: str) -> None:
    """Register standard /health and /metrics routes for a service."""

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    @app.get("/metrics")
    async def metrics():
        return metrics_response()
