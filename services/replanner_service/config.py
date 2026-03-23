from __future__ import annotations

import os
from dataclasses import dataclass


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
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            llm_provider=os.environ.get(
                "REPLANNER_LLM_PROVIDER",
                os.environ.get("LLM_PROVIDER", "mock"),
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            agent_name=os.environ.get("AGENT_NAME", "replanner_agent"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Revisar planes existentes a la luz de fallos de QA y seguridad, proponiendo ajustes mínimos y seguros.",
            ),
            token_budget_per_plan=int(os.environ.get("TOKEN_BUDGET_PER_PLAN", "30000")),
            strategy=os.environ.get("AGENT_STRATEGY", "critic_replanning"),
            enable_tool_loop=os.environ.get(
                "REPLANNER_ENABLE_TOOL_LOOP", "false"
            ).lower()
            in ("1", "true", "yes"),
            tool_loop_max_steps=int(
                os.environ.get("REPLANNER_TOOL_LOOP_MAX_STEPS", "8")
            ),
        )

