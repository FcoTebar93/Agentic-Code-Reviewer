"""
Request-scoped correlation IDs for logs, HTTP, and RabbitMQ.

Uses contextvars so concurrent asyncio tasks stay isolated. Set from:
- HTTP middleware (incoming X-ADMADC-* headers)
- RabbitMQ consumer (message headers + event payload)
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, Mapping

HTTP_TRACE_HEADER = "X-ADMADC-Trace-Id"
HTTP_PLAN_HEADER = "X-ADMADC-Plan-Id"
HTTP_TASK_HEADER = "X-ADMADC-Task-Id"

AMQP_TRACE_KEY = "x-admadc-trace-id"
AMQP_PLAN_KEY = "x-admadc-plan-id"
AMQP_TASK_KEY = "x-admadc-task-id"

trace_id_var: ContextVar[str | None] = ContextVar("admadc_trace_id", default=None)
plan_id_var: ContextVar[str | None] = ContextVar("admadc_plan_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("admadc_task_id", default=None)


def plan_task_from_payload(payload: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    """Best-effort plan_id / task_id from an event payload dict."""
    if not payload:
        return None, None
    raw_plan = payload.get("plan_id")
    plan_id = str(raw_plan) if raw_plan is not None and raw_plan != "" else None

    task_id: str | None
    raw_task = payload.get("task_id")
    if raw_task is not None and raw_task != "":
        task_id = str(raw_task)
    else:
        task_obj = payload.get("task")
        if isinstance(task_obj, dict):
            tid = task_obj.get("task_id")
            task_id = str(tid) if tid is not None and tid != "" else None
        else:
            task_id = None
    return plan_id, task_id


def correlation_http_headers() -> dict[str, str]:
    """Headers to send on outbound HTTP requests (from current context)."""
    out: dict[str, str] = {}
    tid = trace_id_var.get()
    if tid:
        out[HTTP_TRACE_HEADER] = tid
    pid = plan_id_var.get()
    if pid:
        out[HTTP_PLAN_HEADER] = pid
    tk = task_id_var.get()
    if tk:
        out[HTTP_TASK_HEADER] = tk
    return out


def correlation_amqp_headers_for_publish(
    existing: Mapping[str, Any] | None = None,
    *,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Merge correlation into AMQP headers. Always sets trace id (new UUID if absent).
    plan/task from contextvars, else from payload.
    """
    h: dict[str, Any] = dict(existing or {})
    trace = trace_id_var.get() or str(uuid.uuid4())
    p_plan, p_task = plan_task_from_payload(dict(payload) if payload else None)
    plan = plan_id_var.get() or p_plan
    task = task_id_var.get() or p_task

    h[AMQP_TRACE_KEY] = trace
    if plan:
        h[AMQP_PLAN_KEY] = plan
    else:
        h.pop(AMQP_PLAN_KEY, None)
    if task:
        h[AMQP_TASK_KEY] = task
    else:
        h.pop(AMQP_TASK_KEY, None)
    return h


def _header_ci(headers: Mapping[str, str], name_lower: str) -> str | None:
    for k, v in headers.items():
        if k.lower() == name_lower and v and str(v).strip():
            return str(v).strip()
    return None


def bind_correlation_from_http_headers(headers: Mapping[str, str]) -> list[Any]:
    """
    Bind context from incoming HTTP headers. Generates trace_id if missing.
    Returns tokens for reset_correlation_tokens().
    """
    trace = _header_ci(headers, "x-admadc-trace-id") or str(uuid.uuid4())
    plan = _header_ci(headers, "x-admadc-plan-id")
    task = _header_ci(headers, "x-admadc-task-id")
    return bind_correlation(trace_id=trace, plan_id=plan, task_id=task)


def bind_correlation_from_amqp_and_event(
    amqp_headers: Mapping[str, Any] | None,
    payload: Mapping[str, Any] | None,
) -> list[Any]:
    """
    Bind context for a consumed message. Trace defaults to new UUID if absent.
    """
    hdr = dict(amqp_headers or {})
    trace_raw = hdr.get(AMQP_TRACE_KEY) or hdr.get("X-ADMADC-Trace-Id")
    trace = str(trace_raw).strip() if trace_raw else str(uuid.uuid4())

    p_plan, p_task = plan_task_from_payload(dict(payload) if payload else None)
    plan_raw = hdr.get(AMQP_PLAN_KEY) or hdr.get("X-ADMADC-Plan-Id")
    task_raw = hdr.get(AMQP_TASK_KEY) or hdr.get("X-ADMADC-Task-Id")

    plan = (str(plan_raw).strip() if plan_raw else None) or p_plan
    task = (str(task_raw).strip() if task_raw else None) or p_task

    return bind_correlation(trace_id=trace, plan_id=plan, task_id=task)


def bind_correlation(
    *,
    trace_id: str,
    plan_id: str | None = None,
    task_id: str | None = None,
) -> list[Any]:
    """Set correlation context; returns opaque tokens for reset_correlation_tokens()."""
    tokens: list[Any] = [
        (trace_id_var, trace_id_var.set(trace_id)),
        (plan_id_var, plan_id_var.set(plan_id)),
        (task_id_var, task_id_var.set(task_id)),
    ]
    return tokens


def reset_correlation_tokens(tokens: list[Any]) -> None:
    for var, tok in reversed(tokens):
        var.reset(tok)