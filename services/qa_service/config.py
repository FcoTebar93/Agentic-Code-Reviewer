from __future__ import annotations

import os
from dataclasses import dataclass, field


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

    @classmethod
    def from_env(cls) -> QAConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            max_qa_retries=int(os.environ.get("MAX_QA_RETRIES", "2")),
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        )
