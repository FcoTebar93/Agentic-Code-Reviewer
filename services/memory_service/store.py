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
import os
from datetime import datetime, timezone
from math import log1p
from typing import Any

import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from sqlalchemy import select

from services.memory_service.database import (
    EventLog,
    TaskState,
    get_session,
)
from shared.contracts.events import BaseEvent, EventType

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "admadc_code_memory"
# Dimensión por defecto alineada con la colección existente en Qdrant.
# Se puede sobreescribir vía EMBEDDING_DIM si se recrea la colección con otro tamaño.
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))


class MemoryStore:

    def __init__(self, qdrant_url: str, redis_url: str) -> None:
        self._qdrant = AsyncQdrantClient(url=qdrant_url)
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._embed_model = os.environ.get(
            "EMBEDDING_MODEL", "text-embedding-3-small"
        )
        self._embed_api_key = (
            os.environ.get("EMBEDDING_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        self._embed_client = None

    async def initialize(self) -> None:
        collections = await self._qdrant.get_collections()
        names = [c.name for c in collections.collections]
        if QDRANT_COLLECTION not in names:
            await self._qdrant.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
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
                plan_id=str(event.payload.get("plan_id", "")),
            )
            session.add(row)
            await session.commit()
        try:
            await self._index_event_for_search(event)
        except Exception:
            logger.exception(
                "Failed to index event %s for semantic search",
                event.event_id[:8],
            )
        return True

    async def get_events(
        self,
        event_type: str | None = None,
        plan_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
            if event_type:
                stmt = stmt.where(EventLog.event_type == event_type)
            if plan_id:
                stmt = stmt.where(EventLog.plan_id == plan_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "event_id": r.event_id,
                    "event_type": r.event_type,
                    "producer": r.producer,
                    "payload": json.loads(r.payload),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "plan_id": r.plan_id,
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

    async def semantic_search(
        self,
        query: str,
        plan_id: str | None = None,
        event_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        High-level semantic search entry point.

        - Encodes the query into a vector.
        - Runs a Qdrant similarity search with optional filters.
        - Applies heuristic scoring (importance, recency, frequency, impact).
        """
        vector = await self._embed_text(query)
        qdrant_filter = self._build_qdrant_filter(plan_id=plan_id, event_types=event_types or [])
        results = await self._qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vector,
            limit=limit,
            query_filter=qdrant_filter,
        )

        now = datetime.now(timezone.utc)
        scored: list[dict[str, Any]] = []
        for point in results.points:
            payload = point.payload or {}
            base_score = float(point.score or 0.0)
            heuristic = self._compute_heuristic_score(
                base_score=base_score,
                payload=payload,
                now=now,
            )
            scored.append(
                {
                    "id": str(point.id),
                    "score": base_score,
                    "heuristic_score": heuristic,
                    "payload": payload,
                }
            )

        scored.sort(key=lambda x: x["heuristic_score"], reverse=True)
        return scored

    async def _embed_text(self, text: str) -> list[float]:
        """
        Encode text into an embedding vector compatible with Qdrant.

        Prefers an OpenAI-compatible embeddings API when configured, and falls
        back to a deterministic hash-based pseudo-embedding otherwise.
        """
        if not text.strip():
            return [0.0] * EMBEDDING_DIM

        if not self._embed_api_key:
            return self._hash_to_vector(text, EMBEDDING_DIM)

        try:
            from openai import AsyncOpenAI  # type: ignore
        except Exception:
            logger.warning(
                "openai package not available, falling back to hash-based embeddings"
            )
            return self._hash_to_vector(text, EMBEDDING_DIM)

        if self._embed_client is None:
            self._embed_client = AsyncOpenAI(api_key=self._embed_api_key)

        try:
            resp = await self._embed_client.embeddings.create(
                model=self._embed_model,
                input=[text],
            )
            embedding = resp.data[0].embedding
            if len(embedding) != EMBEDDING_DIM:
                return self._resize_vector(embedding, EMBEDDING_DIM)
            return embedding
        except Exception:
            logger.exception("Embedding API call failed, using hash-based embedding")
            return self._hash_to_vector(text, EMBEDDING_DIM)

    async def _index_event_for_search(self, event: BaseEvent) -> None:
        """
        Automatically index selected events into the semantic vector store.

        This focuses on architecturally important events such as plan.created
        and pipeline.conclusion, assigning higher heuristic importance.
        """
        text, importance, impact, extra_payload = self._event_to_index_text(event)
        if not text.strip():
            return

        vector = await self._embed_text(text)
        payload: dict[str, Any] = {
            "text": text,
            "event_type": event.event_type.value,
            "producer": event.producer,
            "plan_id": event.payload.get("plan_id", ""),
            "created_at": event.timestamp,
            "importance": importance,
            "impact": impact,
            "access_count": 0,
        }
        payload.update(extra_payload)

        await self.store_embedding(event.event_id, vector, payload)

    def _event_to_index_text(
        self,
        event: BaseEvent,
    ) -> tuple[str, float, float, dict[str, Any]]:
        """
        Map an event into (text, importance, impact, extra_payload) for indexing.
        Only a subset of events are indexed to keep the vector DB focused.
        """
        etype = event.event_type
        payload = event.payload or {}

        if etype == EventType.PLAN_CREATED:
            original = str(payload.get("original_prompt", "")).strip()
            reasoning = str(payload.get("reasoning", "")).strip()
            text_parts = [
                "PLAN_CREATED",
                f"Original prompt: {original}",
                f"Planner reasoning: {reasoning}",
            ]
            return "\n".join(text_parts), 0.9, 0.7, {}

        if etype == EventType.PIPELINE_CONCLUSION:
            conclusion = str(payload.get("conclusion_text", "")).strip()
            files_changed = payload.get("files_changed") or []
            text_parts = [
                "PIPELINE_CONCLUSION",
                f"Conclusion: {conclusion}",
                f"Files changed: {', '.join(files_changed)}",
            ]
            return "\n".join(text_parts), 0.95, 1.0, {
                "approved": bool(payload.get("approved", True)),
            }

        if etype in (EventType.QA_FAILED, EventType.SECURITY_BLOCKED):
            reasoning = str(payload.get("reasoning", "")).strip()
            issues = payload.get("issues") or payload.get("violations") or []
            text_parts = [
                etype.value,
                f"Reasoning: {reasoning}",
                f"Issues: {', '.join(issues)}",
            ]
            return "\n".join(text_parts), 0.8, 0.9, {}

        if etype in (EventType.QA_PASSED, EventType.SECURITY_APPROVED):
            reasoning = str(payload.get("reasoning", "")).strip()
            text_parts = [
                etype.value,
                f"Reasoning: {reasoning}",
            ]
            return "\n".join(text_parts), 0.7, 0.8, {}

        return "", 0.0, 0.0, {}

    def _build_qdrant_filter(
        self,
        plan_id: str | None,
        event_types: list[str],
    ) -> Filter | None:
        conditions: list[FieldCondition] = []
        if plan_id:
            conditions.append(
                FieldCondition(
                    key="plan_id",
                    match=MatchValue(value=plan_id),
                )
            )
        if event_types:
            if len(event_types) == 1:
                conditions.append(
                    FieldCondition(
                        key="event_type",
                        match=MatchValue(value=event_types[0]),
                    )
                )
            else:
                conditions.append(
                    FieldCondition(
                        key="event_type",
                        match=MatchValue(value=event_types[0]),
                    )
                )

        if not conditions:
            return None
        return Filter(must=conditions)

    def _compute_heuristic_score(
        self,
        base_score: float,
        payload: dict[str, Any],
        now: datetime,
    ) -> float:
        """
        Combine vector similarity with simple heuristics:
        - importance: manual weighting of how semantically important a memory is
        - impact: how much it influenced decisions (e.g. conclusions, blocks)
        - recency: newer memories get a small boost
        - frequency: frequently retrieved memories get a small boost
        """
        importance = float(payload.get("importance", 0.5))
        impact = float(payload.get("impact", 0.0))
        access_count = int(payload.get("access_count", 0))

        created_at_str = payload.get("created_at") or ""
        last_used_str = payload.get("last_used_at") or created_at_str

        recency_boost = 0.0
        if last_used_str:
            try:
                last_used = datetime.fromisoformat(
                    last_used_str.replace("Z", "+00:00")
                )
                age_seconds = max((now - last_used).total_seconds(), 0.0)
                recency_boost = 1.0 / (1.0 + age_seconds / 3600.0)
            except Exception:
                recency_boost = 0.0

        freq_boost = min(1.0, log1p(max(access_count, 0)) / 3.0)

        return (
            base_score * (1.0 + 0.4 * importance + 0.3 * impact)
            + 0.2 * recency_boost
            + 0.1 * freq_boost
        )

    @staticmethod
    def _hash_to_vector(text: str, dim: int) -> list[float]:
        """
        Deterministic pseudo-embedding based on hashing.

        This is only used as a fallback when a real embedding model is not
        available; it still enables approximate clustering and experimentation.
        """
        import hashlib

        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = (h * ((dim // len(h)) + 1))[:dim]
        return [b / 255.0 for b in raw]

    @staticmethod
    def _resize_vector(vec: list[float], dim: int) -> list[float]:
        """
        Resize a vector to the desired dimensionality in a deterministic way.
        """
        if not vec:
            return [0.0] * dim
        if len(vec) == dim:
            return vec
        if len(vec) > dim:
            stride = len(vec) / dim
            return [vec[int(i * stride)] for i in range(dim)]
        out: list[float] = []
        while len(out) < dim:
            out.extend(vec)
        return out[:dim]
