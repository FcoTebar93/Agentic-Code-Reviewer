from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PlannerConfig:
    rabbitmq_url: str
    memory_service_url: str
    llm_provider: str
    log_level: str
    agent_name: str
    agent_goal: str
    token_budget_per_plan: int
    strategy: str

    @classmethod
    def from_env(cls) -> PlannerConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            agent_name=os.environ.get("AGENT_NAME", "meta_planner"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Decomponer peticiones de usuario en planes de desarrollo claros y ejecutables.",
            ),
            token_budget_per_plan=int(os.environ.get("TOKEN_BUDGET_PER_PLAN", "60000")),
            strategy=os.environ.get("AGENT_STRATEGY", "architectural_planning"),
        )
