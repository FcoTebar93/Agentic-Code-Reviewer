from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PlannerConfig:
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
    def from_env(cls) -> PlannerConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            llm_provider=os.environ.get(
                "META_PLANNER_LLM_PROVIDER",
                os.environ.get("LLM_PROVIDER", "mock"),
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            agent_name=os.environ.get("AGENT_NAME", "meta_planner"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Decomponer peticiones de usuario en planes de desarrollo claros y ejecutables.",
            ),
            token_budget_per_plan=int(os.environ.get("TOKEN_BUDGET_PER_PLAN", "60000")),
            strategy=os.environ.get("AGENT_STRATEGY", "architectural_planning"),
            enable_tool_loop=os.environ.get(
                "META_PLANNER_ENABLE_TOOL_LOOP", "false"
            ).lower()
            in ("1", "true", "yes"),
            tool_loop_max_steps=int(
                os.environ.get("META_PLANNER_TOOL_LOOP_MAX_STEPS", "8")
            ),
        )
