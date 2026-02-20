"""
Memory Service -- unified facade over PostgreSQL, Qdrant, and Redis.

Other services interact with memory exclusively through this service's
HTTP API. No direct database access from outside.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response
from services.memory_service.config import MemoryConfig
from services.memory_service.database import init_db, close_db
from services.memory_service.store import MemoryStore

SERVICE_NAME = "memory_service"
store: MemoryStore | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global store
    logger = setup_logging(SERVICE_NAME)

    cfg = MemoryConfig.from_env()
    logger.info("Initializing database")
    await init_db(cfg.database_url)

    store = MemoryStore(qdrant_url=cfg.qdrant_url, redis_url=cfg.redis_url)
    await store.initialize()
    logger.info("Memory store ready")

    yield

    logger.info("Shutting down")
    if store:
        await store.close()
    await close_db()


app = FastAPI(
    title="ADMADC - Memory Service",
    version="0.1.0",
    description="Facade over PostgreSQL, Qdrant, and Redis",
    lifespan=lifespan,
)


def _get_store() -> MemoryStore:
    if store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")
    return store


# ---------------------------------------------------------------------------
# Health & metrics
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()


# ---------------------------------------------------------------------------
# Event log endpoints
# ---------------------------------------------------------------------------

class StoreEventRequest(BaseModel):
    event_id: str
    event_type: str
    producer: str
    idempotency_key: str
    payload: dict[str, Any]


@app.post("/events")
async def store_event(req: StoreEventRequest):
    from shared.contracts.events import BaseEvent, EventType

    event = BaseEvent(
        event_id=req.event_id,
        event_type=EventType(req.event_type),
        producer=req.producer,
        idempotency_key=req.idempotency_key,
        payload=req.payload,
    )
    s = _get_store()
    stored = await s.store_event(event)
    return {"stored": stored, "event_id": req.event_id}


@app.get("/events")
async def list_events(event_type: str | None = None, limit: int = 50):
    s = _get_store()
    return await s.get_events(event_type=event_type, limit=limit)


# ---------------------------------------------------------------------------
# Task state endpoints
# ---------------------------------------------------------------------------

class UpdateTaskRequest(BaseModel):
    task_id: str
    plan_id: str
    status: str = "pending"
    file_path: str = ""
    code: str = ""


@app.post("/tasks")
async def update_task(req: UpdateTaskRequest):
    s = _get_store()
    await s.update_task(
        task_id=req.task_id,
        plan_id=req.plan_id,
        status=req.status,
        file_path=req.file_path,
        code=req.code,
    )
    return {"updated": True, "task_id": req.task_id}


@app.get("/tasks/{plan_id}")
async def get_tasks(plan_id: str):
    s = _get_store()
    return await s.get_tasks(plan_id)


# ---------------------------------------------------------------------------
# Cache endpoints (operational memory)
# ---------------------------------------------------------------------------

class CacheSetRequest(BaseModel):
    key: str
    value: str
    ttl: int = 3600


@app.post("/cache")
async def cache_set(req: CacheSetRequest):
    s = _get_store()
    await s.cache_set(req.key, req.value, req.ttl)
    return {"cached": True}


@app.get("/cache/{key}")
async def cache_get(key: str):
    s = _get_store()
    value = await s.cache_get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": key, "value": value}
