from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import Response


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

pr_creation_latency = Histogram(
    "pr_creation_latency_seconds",
    "Latency of pull request creation",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)


def metrics_response() -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
