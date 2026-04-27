from __future__ import annotations

import os
from dataclasses import dataclass

from shared.utils.env import env_bool, env_int, env_str


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
            llm_provider=env_str(
                "SPEC_LLM_PROVIDER",
                env_str("LLM_PROVIDER", "mock"),
            ),
            log_level=env_str("LOG_LEVEL", "INFO"),
            redis_url=env_str("REDIS_URL", "redis://redis:6379/0"),
            agent_name=env_str("AGENT_NAME", "spec_agent"),
            agent_goal=env_str(
                "AGENT_GOAL",
                "Enriquecer las tareas con especificaciones claras y tests sugeridos antes de que el dev_service genere código.",
            ),
            token_budget_per_task=env_int("SPEC_TOKEN_BUDGET_PER_TASK", 8000),
            strategy=env_str("AGENT_STRATEGY", "spec_and_tests"),
            enable_tool_loop=env_bool("SPEC_ENABLE_TOOL_LOOP"),
            tool_loop_max_steps=env_int("SPEC_TOOL_LOOP_MAX_STEPS", 8),
        )

