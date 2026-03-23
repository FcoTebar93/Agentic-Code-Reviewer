from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SpecConfig:
    rabbitmq_url: str
    memory_service_url: str
    llm_provider: str
    log_level: str
    redis_url: str
    agent_name: str
    agent_goal: str
    token_budget_per_task: int
    strategy: str
    enable_tool_loop: bool
    tool_loop_max_steps: int

    @classmethod
    def from_env(cls) -> "SpecConfig":
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=os.environ.get(
                "SPEC_LLM_PROVIDER",
                os.environ.get("LLM_PROVIDER", "mock"),
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            agent_name=os.environ.get("AGENT_NAME", "spec_agent"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Enriquecer las tareas con especificaciones claras y tests sugeridos antes de que el dev_service genere código.",
            ),
            token_budget_per_task=int(
                os.environ.get("SPEC_TOKEN_BUDGET_PER_TASK", "8000")
            ),
            strategy=os.environ.get("AGENT_STRATEGY", "spec_and_tests"),
            enable_tool_loop=os.environ.get("SPEC_ENABLE_TOOL_LOOP", "false").lower()
            in ("1", "true", "yes"),
            tool_loop_max_steps=int(
                os.environ.get("SPEC_TOOL_LOOP_MAX_STEPS", "8")
            ),
        )

