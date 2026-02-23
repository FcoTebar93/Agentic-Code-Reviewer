"""
Unified memory store -- facade over PostgreSQL, Qdrant, and Redis.

Provides a clean API for the rest of the system:
- store_event / get_events  -> PostgreSQL (structured)
- store_embedding / search  -> Qdrant (semantic)
- cache_set / cache_get     -> Redis (operational)
- update_task / get_tasks   -> PostgreSQL (task state)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sqlalchemy import select

from services.memory_service.database import (
    EventLog,
    TaskState,
    get_session,
)
from shared.contracts.events import BaseEvent

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "admadc_code_memory"
EMBEDDING_DIM = 384


class MemoryStore:

    def __init__(self, qdrant_url: str, redis_url: str) -> None:
        self._qdrant = AsyncQdrantClient(url=qdrant_url)
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def initialize(self) -> None:
        collections = await self._qdrant.get_collections()
        names = [c.name for c in collections.collections]
        if QDRANT_COLLECTION not in names:
            await self._qdrant.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM, distance=Distance.COSINE
                ),
            )
            logger.info("Created Qdrant collection %s", QDRANT_COLLECTION)

    async def close(self) -> None:
        await self._qdrant.close()
        await self._redis.close()

    async def store_event(self, event: BaseEvent) -> bool:
        """Persist an event. Returns False if duplicate (idempotency)."""
        async with get_session() as session:
            existing = await session.execute(
                select(EventLog).where(EventLog.event_id == event.event_id)
            )
            if existing.scalar_one_or_none():
                return False

            row = EventLog(
                event_id=event.event_id,
                event_type=event.event_type.value,
                producer=event.producer,
                idempotency_key=event.idempotency_key,
                payload=json.dumps(event.payload),
            )
            session.add(row)
            await session.commit()
            return True

    async def get_events(
        self, event_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
            if event_type:
                stmt = stmt.where(EventLog.event_type == event_type)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "event_id": r.event_id,
                    "event_type": r.event_type,
                    "producer": r.producer,
                    "payload": json.loads(r.payload),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    async def update_task(
        self,
        task_id: str,
        plan_id: str,
        status: str = "pending",
        file_path: str = "",
        code: str = "",
        repo_url: str = "",
        qa_attempt: int | None = None,
    ) -> None:
        async with get_session() as session:
            existing = await session.get(TaskState, task_id)
            if existing:
                existing.status = status
                existing.file_path = file_path or existing.file_path
                existing.code = code or existing.code
                existing.repo_url = repo_url or existing.repo_url
                if qa_attempt is not None:
                    existing.qa_attempt = qa_attempt
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(
                    TaskState(
                        task_id=task_id,
                        plan_id=plan_id,
                        status=status,
                        file_path=file_path,
                        code=code,
                        repo_url=repo_url,
                        qa_attempt=qa_attempt if qa_attempt is not None else 0,
                    )
                )
            await session.commit()

    async def get_tasks(self, plan_id: str) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                select(TaskState).where(TaskState.plan_id == plan_id)
            )
            rows = result.scalars().all()
            return [
                {
                    "task_id": r.task_id,
                    "plan_id": r.plan_id,
                    "status": r.status,
                    "file_path": r.file_path,
                    "code": r.code,
                    "repo_url": r.repo_url,
                    "qa_attempt": getattr(r, "qa_attempt", 0),
                }
                for r in rows
            ]

    async def store_embedding(
        self, point_id: str, vector: list[float], payload: dict[str, Any]
    ) -> None:
        await self._qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    async def search_similar(
        self, vector: list[float], limit: int = 5
    ) -> list[dict[str, Any]]:
        results = await self._qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vector,
            limit=limit,
        )
        return [
            {"id": str(r.id), "score": r.score, "payload": r.payload}
            for r in results.points
        ]

    async def cache_set(self, key: str, value: str, ttl: int = 3600) -> None:
        await self._redis.set(key, value, ex=ttl)

    async def cache_get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def idempotency_check(self, key: str) -> bool:
        """Returns True if the key was already seen (duplicate)."""
        result = await self._redis.set(
            f"idem:{key}", "1", nx=True, ex=86400
        )
        return result is None
