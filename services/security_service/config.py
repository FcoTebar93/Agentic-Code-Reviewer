from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


SECURITY_RULES: list[tuple[str, re.Pattern[str]]] = [
    # Hardcoded secrets / credentials
    ("hardcoded_api_key", re.compile(r'(?i)(api_key|apikey)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']')),
    ("hardcoded_password", re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']')),
    ("hardcoded_token", re.compile(r'(?i)(token|secret)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']')),

    # Dangerous dynamic code execution
    ("dangerous_eval", re.compile(r'\beval\s*\(')),
    ("dangerous_exec", re.compile(r'\bexec\s*\(')),

    # Unsafe (de)serialization
    ("pickle_deserialize", re.compile(r'\bpickle\.loads\s*\(')),
    ("marshal_deserialize", re.compile(r'\bmarshal\.loads\s*\(')),

    # Path traversal-style patterns
    ("path_traversal", re.compile(r'\.\./')),

    # Shell injection via Python
    ("shell_injection_os", re.compile(r'\bos\.system\s*\(')),
    ("shell_injection_subprocess", re.compile(r'\bsubprocess\.(call|Popen|run)\s*\(.*shell\s*=\s*True')),

    # Basic SQL injection risk (Python DB-API style)
    ("sql_injection_risk", re.compile(r'(?i)(execute|executemany)\s*\(\s*["\'].*%s')),

    # Java / Node shell execution
    ("java_runtime_exec", re.compile(r'Runtime\.getRuntime\(\)\.exec\s*\(')),
    ("java_processbuilder_exec", re.compile(r'new\s+ProcessBuilder\s*\(')),
    ("node_child_process_exec", re.compile(r'child_process\.(exec|execSync)\s*\(')),

    # Very rough SQL concatenation for Java / JS
    ("sql_concat_plus", re.compile(r'(?i)("(SELECT|UPDATE|DELETE|INSERT)[^"]*"\s*\+\s*\w+)')),

    # Debug / development modes left enabled
    ("flask_debug_true", re.compile(r'\bapp\.run\([^)]*debug\s*=\s*True')),
    ("django_debug_true", re.compile(r'\bDEBUG\s*=\s*True')),

    # Overly permissive CORS
    ("cors_allow_all_header", re.compile(r'Access-Control-Allow-Origin["\']?\s*[:=]\s*["\*]["\']')),
    ("express_cors_all", re.compile(r'cors\(\s*\{\s*origin\s*:\s*["\']\*["\']')),
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
