from fastapi import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

tasks_completed = Counter(
    "tasks_completed_total",
    "Total tasks completed by service",
    ["service"],
)

agent_execution_time = Histogram(
    "agent_execution_time_seconds",
    "Time spent executing agent tasks",
    ["service", "operation"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

llm_tokens = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["service", "direction"],
)

llm_requests = Counter(
    "llm_requests_total",
    "Total LLM requests by provider/model/service and outcome",
    ["provider", "model", "service", "outcome"],
)

llm_latency = Histogram(
    "llm_latency_seconds",
    "Latency of LLM calls by service",
    ["service"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

pr_creation_latency = Histogram(
    "pr_creation_latency_seconds",
    "Latency of pull request creation",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

agent_tool_calls_total = Counter(
    "agent_tool_calls_total",
    "Tool invocations from LLM agent tool loops",
    ["service", "tool_name", "result"],
)

agent_tool_loop_llm_rounds = Histogram(
    "agent_tool_loop_llm_rounds",
    "LLM rounds per finished tool loop (each API call is one observation)",
    ["service"],
    buckets=(1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0),
)

agent_tool_loop_outcomes_total = Counter(
    "agent_tool_loop_outcomes_total",
    "Terminal outcomes for agent tool loops",
    ["service", "outcome"],
)


def metrics_response() -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
