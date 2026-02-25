from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DevConfig:
    rabbitmq_url: str
    memory_service_url: str
    llm_provider: str
    log_level: str
    redis_url: str
    step_delay: str
    agent_name: str
    agent_goal: str
    token_budget_per_task: int
    strategy: str

    @classmethod
    def from_env(cls) -> DevConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            step_delay=os.environ.get("AGENT_STEP_DELAY", "0"),
            agent_name=os.environ.get("AGENT_NAME", "dev_agent"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Escribir código de producción fiel al plan y fácil de mantener.",
            ),
            token_budget_per_task=int(os.environ.get("TOKEN_BUDGET_PER_TASK", "20000")),
            strategy=os.environ.get("AGENT_STRATEGY", "implementation"),
        )
