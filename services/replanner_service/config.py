from __future__ import annotations

import os
from dataclasses import dataclass

from shared.utils.env import env_bool, env_int, env_str


@dataclass(frozen=True)
class ReplannerConfig:
    rabbitmq_url: str
    memory_service_url: str
    redis_url: str
    llm_provider: str
    log_level: str
    agent_name: str
    agent_goal: str
    token_budget_per_plan: int
    strategy: str
    enable_tool_loop: bool
    tool_loop_max_steps: int

    @classmethod
    def from_env(cls) -> "ReplannerConfig":
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            redis_url=env_str("REDIS_URL", "redis://redis:6379/0"),
            llm_provider=env_str(
                "REPLANNER_LLM_PROVIDER",
                env_str("LLM_PROVIDER", "mock"),
            ),
            log_level=env_str("LOG_LEVEL", "INFO"),
            agent_name=env_str("AGENT_NAME", "replanner_agent"),
            agent_goal=env_str(
                "AGENT_GOAL",
                "Revisar planes existentes a la luz de fallos de QA y seguridad, proponiendo ajustes mínimos y seguros.",
            ),
            token_budget_per_plan=env_int("TOKEN_BUDGET_PER_PLAN", 30000),
            strategy=env_str("AGENT_STRATEGY", "critic_replanning"),
            enable_tool_loop=env_bool("REPLANNER_ENABLE_TOOL_LOOP"),
            tool_loop_max_steps=env_int("REPLANNER_TOOL_LOOP_MAX_STEPS", 8),
        )

