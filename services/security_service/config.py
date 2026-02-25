from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


SECURITY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("hardcoded_api_key", re.compile(r'(?i)(api_key|apikey)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']')),
    ("hardcoded_password", re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']')),
    ("hardcoded_token", re.compile(r'(?i)(token|secret)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']')),
    ("dangerous_eval", re.compile(r'\beval\s*\(')),
    ("dangerous_exec", re.compile(r'\bexec\s*\(')),
    ("pickle_deserialize", re.compile(r'\bpickle\.loads\s*\(')),
    ("marshal_deserialize", re.compile(r'\bmarshal\.loads\s*\(')),
    ("path_traversal", re.compile(r'\.\./')),
    ("shell_injection_os", re.compile(r'\bos\.system\s*\(')),
    ("shell_injection_subprocess", re.compile(r'\bsubprocess\.(call|Popen|run)\s*\(.*shell\s*=\s*True')),
    ("sql_injection_risk", re.compile(r'(?i)(execute|executemany)\s*\(\s*["\'].*%s')),
]


@dataclass(frozen=True)
class SecurityConfig:
    rabbitmq_url: str
    memory_service_url: str
    log_level: str
    redis_url: str
    agent_name: str
    agent_goal: str
    strategy: str

    @classmethod
    def from_env(cls) -> SecurityConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            agent_name=os.environ.get("AGENT_NAME", "security_agent"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Bloquear cambios con patrones de seguridad peligrosos antes de que lleguen a GitHub.",
            ),
            strategy=os.environ.get("AGENT_STRATEGY", "deterministic_static_scan"),
        )
