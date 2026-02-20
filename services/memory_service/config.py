from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryConfig:
    database_url: str
    qdrant_url: str
    redis_url: str
    rabbitmq_url: str
    log_level: str

    @classmethod
    def from_env(cls) -> MemoryConfig:
        return cls(
            database_url=os.environ["DATABASE_URL"],
            qdrant_url=os.environ["QDRANT_URL"],
            redis_url=os.environ["REDIS_URL"],
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
