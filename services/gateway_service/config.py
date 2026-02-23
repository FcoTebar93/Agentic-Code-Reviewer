from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayConfig:
    rabbitmq_url: str
    memory_service_url: str
    meta_planner_url: str
    log_level: str

    @classmethod
    def from_env(cls) -> GatewayConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            meta_planner_url=os.environ.get("META_PLANNER_URL", "http://meta_planner:8000"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
