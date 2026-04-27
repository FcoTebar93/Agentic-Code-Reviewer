from __future__ import annotations

import os
from dataclasses import dataclass

from shared.utils.env import env_bool, env_float, env_int, env_str


@dataclass(frozen=True)
class GatewayConfig:
    rabbitmq_url: str
    memory_service_url: str
    meta_planner_url: str
    log_level: str
    llm_prompt_price_per_1k: float
    llm_completion_price_per_1k: float
    cors_allow_origins: list[str]
    cors_allow_methods: list[str]
    cors_allow_headers: list[str]
    approvals_auth_enabled: bool
    approvals_auth_token: str
    approvals_rate_limit_enabled: bool
    approvals_rate_limit_window_seconds: int
    approvals_rate_limit_max_requests: int
    approvals_audit_summary_enabled: bool

    @classmethod
    def from_env(cls) -> GatewayConfig:
        raw_origins = env_str("GATEWAY_CORS_ALLOW_ORIGINS", "http://localhost:3001")
        raw_methods = env_str("GATEWAY_CORS_ALLOW_METHODS", "GET,POST,PUT,DELETE,OPTIONS")
        raw_headers = env_str(
            "GATEWAY_CORS_ALLOW_HEADERS",
            "Authorization,Content-Type,X-Requested-With",
        )
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            meta_planner_url=env_str("META_PLANNER_URL", "http://meta_planner:8000"),
            log_level=env_str("LOG_LEVEL", "INFO"),
            llm_prompt_price_per_1k=env_float("LLM_PROMPT_PRICE_PER_1K", 0.0),
            llm_completion_price_per_1k=env_float("LLM_COMPLETION_PRICE_PER_1K", 0.0),
            cors_allow_origins=[v.strip() for v in raw_origins.split(",") if v.strip()],
            cors_allow_methods=[v.strip().upper() for v in raw_methods.split(",") if v.strip()],
            cors_allow_headers=[v.strip() for v in raw_headers.split(",") if v.strip()],
            approvals_auth_enabled=env_bool("GATEWAY_APPROVALS_AUTH_ENABLED"),
            approvals_auth_token=env_str("GATEWAY_APPROVALS_AUTH_TOKEN", ""),
            approvals_rate_limit_enabled=env_bool("GATEWAY_APPROVALS_RATE_LIMIT_ENABLED"),
            approvals_rate_limit_window_seconds=max(
                1, env_int("GATEWAY_APPROVALS_RATE_LIMIT_WINDOW_SECONDS", 60)
            ),
            approvals_rate_limit_max_requests=max(
                1, env_int("GATEWAY_APPROVALS_RATE_LIMIT_MAX_REQUESTS", 20)
            ),
            approvals_audit_summary_enabled=env_bool(
                "GATEWAY_APPROVALS_AUDIT_SUMMARY_ENABLED"
            ),
        )
