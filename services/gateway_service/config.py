from __future__ import annotations

import os
from dataclasses import dataclass


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

    @classmethod
    def from_env(cls) -> GatewayConfig:
        raw_origins = os.environ.get(
            "GATEWAY_CORS_ALLOW_ORIGINS", "http://localhost:3001"
        )
        raw_methods = os.environ.get(
            "GATEWAY_CORS_ALLOW_METHODS", "GET,POST,PUT,DELETE,OPTIONS"
        )
        raw_headers = os.environ.get(
            "GATEWAY_CORS_ALLOW_HEADERS",
            "Authorization,Content-Type,X-Requested-With",
        )
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            meta_planner_url=os.environ.get("META_PLANNER_URL", "http://meta_planner:8000"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            llm_prompt_price_per_1k=float(os.environ.get("LLM_PROMPT_PRICE_PER_1K", "0") or 0),
            llm_completion_price_per_1k=float(os.environ.get("LLM_COMPLETION_PRICE_PER_1K", "0") or 0),
            cors_allow_origins=[v.strip() for v in raw_origins.split(",") if v.strip()],
            cors_allow_methods=[v.strip().upper() for v in raw_methods.split(",") if v.strip()],
            cors_allow_headers=[v.strip() for v in raw_headers.split(",") if v.strip()],
            approvals_auth_enabled=os.environ.get(
                "GATEWAY_APPROVALS_AUTH_ENABLED", "false"
            ).lower()
            in ("1", "true", "yes"),
            approvals_auth_token=os.environ.get("GATEWAY_APPROVALS_AUTH_TOKEN", ""),
            approvals_rate_limit_enabled=os.environ.get(
                "GATEWAY_APPROVALS_RATE_LIMIT_ENABLED", "false"
            ).lower()
            in ("1", "true", "yes"),
            approvals_rate_limit_window_seconds=max(
                1, int(os.environ.get("GATEWAY_APPROVALS_RATE_LIMIT_WINDOW_SECONDS", "60"))
            ),
            approvals_rate_limit_max_requests=max(
                1, int(os.environ.get("GATEWAY_APPROVALS_RATE_LIMIT_MAX_REQUESTS", "20"))
            ),
        )
