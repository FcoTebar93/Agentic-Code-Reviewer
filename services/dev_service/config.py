from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DevConfig:
    rabbitmq_url: str
    memory_service_url: str
    llm_provider: str
    log_level: str
    redis_url: str
    step_delay: str
    agent_name: str
    agent_goal: str
    token_budget_per_task: int
    strategy: str
    enable_auto_tests: bool
    enable_auto_lints: bool
    test_command_python: str
    test_command_javascript: str
    test_command_typescript: str
    test_command_java: str
    enable_tool_loop: bool
    tool_loop_max_steps: int
    tool_loop_include_ci_tools: bool
    large_diff_warn_enabled: bool
    large_diff_soft_lines: int
    large_diff_similarity: float
    spec_wait_max_seconds: float
    spec_wait_interval_seconds: float
    spec_context_max_chars: int
    dev_context_max_chars: int
    auto_gates_scoped: bool
    lint_python_scoped_template: str
    lint_python_wide_template: str
    test_python_template: str
    enable_auto_typecheck: bool
    typecheck_python_template: str
    auto_gates_timeout_seconds: float

    @classmethod
    def from_env(cls) -> DevConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            memory_service_url=os.environ["MEMORY_SERVICE_URL"],
            llm_provider=os.environ.get("DEV_LLM_PROVIDER", os.environ.get("LLM_PROVIDER", "mock")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            step_delay=os.environ.get("AGENT_STEP_DELAY", "0"),
            agent_name=os.environ.get("AGENT_NAME", "dev_agent"),
            agent_goal=os.environ.get(
                "AGENT_GOAL",
                "Escribir código de producción fiel al plan y fácil de mantener.",
            ),
            token_budget_per_task=int(os.environ.get("TOKEN_BUDGET_PER_TASK", "20000")),
            strategy=os.environ.get("AGENT_STRATEGY", "implementation"),
            enable_auto_tests=os.environ.get("DEV_ENABLE_AUTO_TESTS", "false").lower()
            in ("1", "true", "yes"),
            enable_auto_lints=os.environ.get("DEV_ENABLE_AUTO_LINTS", "false").lower()
            in ("1", "true", "yes"),
            test_command_python=os.environ.get("DEV_TEST_COMMAND_PYTHON", "pytest"),
            test_command_javascript=os.environ.get("DEV_TEST_COMMAND_JAVASCRIPT", ""),
            test_command_typescript=os.environ.get("DEV_TEST_COMMAND_TYPESCRIPT", ""),
            test_command_java=os.environ.get("DEV_TEST_COMMAND_JAVA", ""),
            enable_tool_loop=os.environ.get("DEV_ENABLE_TOOL_LOOP", "false").lower()
            in ("1", "true", "yes"),
            tool_loop_max_steps=int(os.environ.get("DEV_TOOL_LOOP_MAX_STEPS", "8")),
            tool_loop_include_ci_tools=os.environ.get(
                "DEV_TOOL_LOOP_INCLUDE_CI_TOOLS", "false"
            ).lower()
            in ("1", "true", "yes"),
            large_diff_warn_enabled=os.environ.get("DEV_LARGE_DIFF_WARN", "true").lower()
            in ("1", "true", "yes"),
            large_diff_soft_lines=int(os.environ.get("DEV_LARGE_DIFF_LINE_SOFT", "120")),
            large_diff_similarity=float(
                os.environ.get("DEV_LARGE_DIFF_SIMILARITY", "0.52")
            ),
            spec_wait_max_seconds=float(
                os.environ.get("DEV_SPEC_WAIT_MAX_SECONDS", "10") or 0
            ),
            spec_wait_interval_seconds=max(
                0.05,
                float(os.environ.get("DEV_SPEC_WAIT_INTERVAL_SECONDS", "0.2") or 0.2),
            ),
            spec_context_max_chars=max(
                400,
                int(os.environ.get("DEV_SPEC_CONTEXT_MAX_CHARS", "3000")),
            ),
            dev_context_max_chars=max(
                2000,
                int(os.environ.get("DEV_CONTEXT_MAX_CHARS", "5600")),
            ),
            auto_gates_scoped=os.environ.get("DEV_AUTO_GATES_SCOPED", "true").lower()
            in ("1", "true", "yes"),
            lint_python_scoped_template=os.environ.get(
                "DEV_LINT_PYTHON_SCOPED", "ruff check {file}"
            ),
            lint_python_wide_template=os.environ.get(
                "DEV_LINT_PYTHON_WIDE", "ruff check ."
            ),
            test_python_template=os.environ.get("DEV_TEST_COMMAND_PYTHON", "pytest -q"),
            enable_auto_typecheck=os.environ.get(
                "DEV_ENABLE_AUTO_TYPECHECK", "false"
            ).lower()
            in ("1", "true", "yes"),
            typecheck_python_template=os.environ.get(
                "DEV_TYPECHECK_COMMAND_PYTHON", ""
            ),
            auto_gates_timeout_seconds=max(
                15.0,
                float(os.environ.get("DEV_AUTO_GATES_TIMEOUT_SECONDS", "180") or 180),
            ),
        )
