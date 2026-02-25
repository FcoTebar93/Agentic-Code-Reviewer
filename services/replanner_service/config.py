from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplannerConfig:
    rabbitmq_url: str
    memory_service_url: str
    llm_provider: str
    log_level: str
    agent_name: str
    agent_goal: str
    token_budget_per_plan: int
    strategy: str

    @classmethod
    def from_env(cls) -> "ReplannerConfig":
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            agent_name=os.environ.get("AGENT_NAME", "replanner_agent"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Revisar planes existentes a la luz de fallos de QA y seguridad, proponiendo ajustes mínimos y seguros.",
            ),
            token_budget_per_plan=int(os.environ.get("TOKEN_BUDGET_PER_PLAN", "30000")),
            strategy=os.environ.get("AGENT_STRATEGY", "critic_replanning"),
        )

