from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PlannerConfig:
    rabbitmq_url: str
    memory_service_url: str
    llm_provider: str
    log_level: str

    @classmethod
    def from_env(cls) -> PlannerConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
