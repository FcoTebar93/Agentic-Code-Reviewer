from __future__ import annotations

import os
from dataclasses import dataclass

from shared.utils.env import env_bool, env_int, env_str

DANGEROUS_PATTERNS: list[str] = [
    "eval(",
    "exec(",
    "__import__(",
    "os.system(",
    "subprocess.call(",
    "subprocess.Popen(",
    "pickle.loads(",
    "marshal.loads(",
]


@dataclass(frozen=True)
class QAConfig:
    rabbitmq_url: str
    memory_service_url: str
    llm_provider: str
    log_level: str
    max_qa_retries: int
    redis_url: str
    step_delay: str
    agent_name: str
    agent_goal: str
    token_budget_per_review: int
    strategy: str
    enable_semgrep: bool
    enable_js_lint: bool
    enable_java_lint: bool
    enable_tool_loop: bool
    tool_loop_max_steps: int

    @classmethod
    def from_env(cls) -> QAConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=env_str("QA_LLM_PROVIDER", env_str("LLM_PROVIDER", "mock")),
            log_level=env_str("LOG_LEVEL", "INFO"),
            max_qa_retries=env_int("MAX_QA_RETRIES", 2),
            redis_url=env_str("REDIS_URL", "redis://redis:6379/0"),
            step_delay=env_str("AGENT_STEP_DELAY", "0"),
            agent_name=env_str("AGENT_NAME", "qa_agent"),
            agent_goal=env_str(
                "AGENT_GOAL",
                "Asegurar que el código generado es correcto, seguro y mantenible.",
            ),
            token_budget_per_review=env_int("TOKEN_BUDGET_PER_REVIEW", 15000),
            strategy=env_str("AGENT_STRATEGY", "strict_review"),
            enable_semgrep=env_bool("QA_ENABLE_SEMGREP", True),
            enable_js_lint=env_bool("QA_ENABLE_JS_LINT"),
            enable_java_lint=env_bool("QA_ENABLE_JAVA_LINT"),
            enable_tool_loop=env_bool("QA_ENABLE_TOOL_LOOP"),
            tool_loop_max_steps=env_int("QA_TOOL_LOOP_MAX_STEPS", 8),
        )
