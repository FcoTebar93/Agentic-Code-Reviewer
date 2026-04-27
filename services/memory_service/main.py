"""Memory Service -- unified facade over PostgreSQL, Qdrant, and Redis."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from services.memory_service.config import MemoryConfig
from services.memory_service.database import close_db, init_db
from services.memory_service.store import MemoryStore
from shared.logging.logger import setup_logging
from shared.middleware.correlation import install_correlation_middleware
from shared.observability.metrics import metrics_response

SERVICE_NAME = "memory_service"
store: MemoryStore | None = None

_STARTUP_RETRIES = int(__import__("os").environ.get("MEMORY_STARTUP_RETRIES", "10"))
_STARTUP_DELAY_SEC = float(__import__("os").environ.get("MEMORY_STARTUP_DELAY_SEC", "3"))


@asynccontextmanager
async def lifespan(application: FastAPI):
    global store
    logger = setup_logging(SERVICE_NAME)
    cfg = MemoryConfig.from_env()

    last_error: Exception | None = None
    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            logger.info("Initializing database (attempt %d/%d)", attempt, _STARTUP_RETRIES)
            await init_db(cfg.database_url)
            store = MemoryStore(qdrant_url=cfg.qdrant_url, redis_url=cfg.redis_url)
            await store.initialize()
            logger.info("Memory store ready")
            last_error = None
            break
        except Exception as e:
            last_error = e
            logger.warning(
                "Startup attempt %d/%d failed: %s. Retrying in %.1fs.",
                attempt,
                _STARTUP_RETRIES,
                e,
                _STARTUP_DELAY_SEC,
            )
            if attempt < _STARTUP_RETRIES:
                await asyncio.sleep(_STARTUP_DELAY_SEC)
            else:
                logger.exception("Memory service failed to start after %d attempts", _STARTUP_RETRIES)
                raise last_error from last_error

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
install_correlation_middleware(app)


def _get_store() -> MemoryStore:
    if store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")
    return store

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()

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
async def list_events(
    event_type: str | None = None,
    plan_id: str | None = None,
    limit: int = 50,
):
    s = _get_store()
    return await s.get_events(event_type=event_type, plan_id=plan_id, limit=limit)

class UpdateTaskRequest(BaseModel):
    task_id: str
    plan_id: str
    status: str = "pending"
    file_path: str = ""
    code: str = ""
    repo_url: str = ""
    qa_attempt: int | None = None


@app.post("/tasks")
async def update_task(req: UpdateTaskRequest):
    s = _get_store()
    await s.update_task(
        task_id=req.task_id,
        plan_id=req.plan_id,
        status=req.status,
        file_path=req.file_path,
        code=req.code,
        repo_url=req.repo_url,
        qa_attempt=req.qa_attempt,
    )
    return {"updated": True, "task_id": req.task_id}


@app.get("/tasks/{plan_id}")
async def get_tasks(plan_id: str):
    s = _get_store()
    return await s.get_tasks(plan_id)

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


class SemanticSearchRequest(BaseModel):
    query: str
    plan_id: str | None = None
    event_types: list[str] = []
    limit: int = 5


class FailurePatternsResponse(BaseModel):
    module: str
    qa_failed: int = 0
    security_blocked: int = 0
    sample_issues: list[str] = []


@app.post("/semantic/search")
async def semantic_search(req: SemanticSearchRequest):
    """Semantic retrieval over the unified memory store."""
    s = _get_store()
    results = await s.semantic_search(
        query=req.query,
        plan_id=req.plan_id,
        event_types=req.event_types,
        limit=req.limit,
    )
    return {"results": results}


@app.get("/patterns/failures")
async def failure_patterns(limit: int = 200):
    """Devuelve patrones agregados de fallos históricos (qa.failed, security.blocked)."""
    s = _get_store()
    raw = await s.get_failure_patterns(limit_per_kind=limit)
    patterns = [FailurePatternsResponse(**p) for p in raw]
    return {"patterns": [p.model_dump() for p in patterns]}
