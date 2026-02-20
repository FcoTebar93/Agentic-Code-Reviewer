"""
SQLAlchemy async engine & session factory for structured memory.

Creates the event_log and task_state tables on startup.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    producer: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class TaskState(Base):
    __tablename__ = "task_state"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    code: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    global _engine, _session_factory
    _engine = create_async_engine(database_url, echo=False, pool_size=5)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()


def get_session() -> AsyncSession:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory()
