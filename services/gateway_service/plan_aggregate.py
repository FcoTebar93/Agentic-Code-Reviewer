"""Plan metrics and plan_detail aggregation for the gateway."""

from __future__ import annotations

import json as json_lib
import logging
from datetime import datetime
from typing import Any

from fastapi.responses import JSONResponse

from services.gateway_service.constants import SERVICE_NAME
from services.gateway_service.runtime import GatewayRuntime
from shared.contracts.events import EventType

logger = logging.getLogger(SERVICE_NAME)


async def aggregate_plan_metrics(
    runtime: GatewayRuntime, plan_id: str,
) -> dict[str, Any] | JSONResponse:
    http_client = runtime.http_client
    cfg = runtime.cfg
    try:
        resp = await http_client.get(
            f"{cfg.memory_service_url}/events",
            params={
                "plan_id": plan_id,
                "event_type": EventType.METRICS_TOKENS_USED.value,
                "limit": 500,
            },
        )
        if resp.status_code != 200:
            return JSONResponse(
                content={"error": "Failed to fetch events", "status": resp.status_code},
                status_code=502,
            )
        token_events = resp.json()
        if not isinstance(token_events, list):
            token_events = []

        prompt_price = cfg.llm_prompt_price_per_1k if cfg else 0.0
        completion_price = cfg.llm_completion_price_per_1k if cfg else 0.0

        token_summary = _aggregate_token_usage(
            token_events,
            prompt_price=prompt_price,
            completion_price=completion_price,
        )

        health_events: list[dict[str, Any]] = []
        try:
            resp_all = await http_client.get(
                f"{cfg.memory_service_url}/events",
                params={"plan_id": plan_id, "limit": 500},
            )
            if resp_all.status_code == 200:
                data_all = resp_all.json()
                if isinstance(data_all, list):
                    health_events = data_all
        except Exception:
            logger.warning("Failed to fetch health events for plan %s", plan_id[:8])

        health_summary = _compute_pipeline_health(health_events, plan_id)

        replan_suggestions_count = 0
        replan_confirmed_count = 0
        try:
            resp_suggested = await http_client.get(
                f"{cfg.memory_service_url}/events",
                params={
                    "event_type": EventType.PLAN_REVISION_SUGGESTED.value,
                    "limit": 200,
                },
            )
            if resp_suggested.status_code == 200:
                events_sugg = resp_suggested.json()
                if isinstance(events_sugg, list):
                    replan_suggestions_count = _count_replans_for_plan(
                        events_sugg, plan_id
                    )
        except Exception:
            logger.warning(
                "Failed to fetch plan.revision_suggested events for health metrics"
            )

        try:
            resp_confirmed = await http_client.get(
                f"{cfg.memory_service_url}/events",
                params={
                    "event_type": EventType.PLAN_REVISION_CONFIRMED.value,
                    "limit": 200,
                },
            )
            if resp_confirmed.status_code == 200:
                events_conf = resp_confirmed.json()
                if isinstance(events_conf, list):
                    replan_confirmed_count = _count_replans_for_plan(
                        events_conf, plan_id
                    )
        except Exception:
            logger.warning(
                "Failed to fetch plan.revision_confirmed events for health metrics"
            )

        return {
            "plan_id": plan_id,
            "total_prompt_tokens": token_summary["total_prompt_tokens"],
            "total_completion_tokens": token_summary["total_completion_tokens"],
            "total_tokens": token_summary["total_tokens"],
            "estimated_cost_prompt_usd": token_summary["estimated_cost_prompt_usd"],
            "estimated_cost_completion_usd": token_summary[
                "estimated_cost_completion_usd"
            ],
            "estimated_cost_total_usd": token_summary["estimated_cost_total_usd"],
            "pipeline_status": health_summary["pipeline_status"],
            "first_event_at": health_summary["first_event_at"],
            "last_event_at": health_summary["last_event_at"],
            "duration_seconds": health_summary["duration_seconds"],
            "qa_retry_count": health_summary["qa_retry_count"],
            "qa_failed_count": health_summary["qa_failed_count"],
            "security_blocked_count": health_summary["security_blocked_count"],
            "replan_suggestions_count": replan_suggestions_count,
            "replan_confirmed_count": replan_confirmed_count,
            "by_service": token_summary["by_service"],
        }
    except Exception as exc:
        logger.exception("Failed to get plan_metrics for %s", plan_id[:8])
        return JSONResponse(content={"error": str(exc)}, status_code=502)


async def build_plan_detail_json_response(
    runtime: GatewayRuntime, plan_id: str,
) -> JSONResponse:
    http_client = runtime.http_client
    cfg = runtime.cfg
    try:
        metrics_resp = await aggregate_plan_metrics(runtime, plan_id)
        if isinstance(metrics_resp, JSONResponse) and metrics_resp.status_code != 200:
            metrics_data: dict[str, Any] = {}
        else:
            metrics_data = (
                metrics_resp
                if isinstance(metrics_resp, dict)
                else getattr(metrics_resp, "body", None)
            )
            if not isinstance(metrics_data, dict):
                try:
                    metrics_data = (
                        json_lib.loads(metrics_resp.body)
                        if isinstance(metrics_resp, JSONResponse)
                        else {}
                    )
                except Exception:
                    metrics_data = {}

        try:
            tasks_http = await http_client.get(
                f"{cfg.memory_service_url}/tasks/{plan_id}"
            )
            tasks_data = tasks_http.json() if tasks_http.status_code == 200 else []
        except Exception:
            tasks_data = []

        try:
            events_http = await http_client.get(
                f"{cfg.memory_service_url}/events",
                params={"plan_id": plan_id, "limit": 500},
            )
            events_data = events_http.json() if events_http.status_code == 200 else []
        except Exception:
            events_data = []

        detail = _build_plan_detail_json(plan_id, metrics_data, tasks_data, events_data)
        return JSONResponse(content=detail, status_code=200)
    except Exception as exc:
        logger.exception("Failed to build plan_detail for %s", plan_id[:8])
        return JSONResponse(content={"error": str(exc)}, status_code=502)


def _aggregate_token_usage(
    token_events: list[dict[str, Any]],
    prompt_price: float,
    completion_price: float,
) -> dict[str, Any]:
    """
    Aggregate prompt/completion tokens and estimate cost per service and in total.
    """
    by_service: dict[str, dict[str, float]] = {}
    total_prompt = 0
    total_completion = 0

    for ev in token_events:
        payload = ev.get("payload") or {}
        service = str(payload.get("service", "unknown"))
        pt = int(payload.get("prompt_tokens", 0) or 0)
        ct = int(payload.get("completion_tokens", 0) or 0)
        if service not in by_service:
            by_service[service] = {"prompt_tokens": 0.0, "completion_tokens": 0.0}
        by_service[service]["prompt_tokens"] += pt
        by_service[service]["completion_tokens"] += ct
        total_prompt += pt
        total_completion += ct

    prompt_cost = (total_prompt / 1000.0) * prompt_price
    completion_cost = (total_completion / 1000.0) * completion_price
    total_cost = prompt_cost + completion_cost

    by_service_list: list[dict[str, float | str]] = []
    for service, values in sorted(by_service.items()):
        svc_prompt = values["prompt_tokens"]
        svc_completion = values["completion_tokens"]
        svc_prompt_cost = (svc_prompt / 1000.0) * prompt_price
        svc_completion_cost = (svc_completion / 1000.0) * completion_price
        by_service_list.append(
            {
                "service": service,
                "prompt_tokens": int(svc_prompt),
                "completion_tokens": int(svc_completion),
                "total_tokens": int(svc_prompt + svc_completion),
                "estimated_cost_prompt_usd": svc_prompt_cost,
                "estimated_cost_completion_usd": svc_completion_cost,
                "estimated_cost_total_usd": svc_prompt_cost + svc_completion_cost,
            }
        )

    return {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "estimated_cost_prompt_usd": prompt_cost,
        "estimated_cost_completion_usd": completion_cost,
        "estimated_cost_total_usd": total_cost,
        "by_service": by_service_list,
    }


def _compute_pipeline_health(
    health_events: list[dict[str, Any]],
    plan_id: str,
) -> dict[str, Any]:
    """
    Compute basic pipeline health metrics (status, duration, QA/security counters)
    from the list of events for a plan.
    """
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    qa_retry_count = 0
    qa_failed_count = 0
    security_blocked_count = 0

    for ev in health_events:
        ts_str = ev.get("created_at")
        if isinstance(ts_str, str):
            try:
                ts = datetime.fromisoformat(ts_str)
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            except Exception:
                pass

        etype = str(ev.get("event_type", ""))
        payload = ev.get("payload") or {}

        if etype == EventType.TASK_ASSIGNED.value:
            feedback = str(payload.get("qa_feedback", "") or "")
            if feedback.strip():
                qa_retry_count += 1
        elif etype == EventType.QA_FAILED.value:
            qa_failed_count += 1
        elif etype == EventType.SECURITY_BLOCKED.value:
            security_blocked_count += 1

    duration_seconds = 0
    if first_ts and last_ts:
        try:
            duration_seconds = int((last_ts - first_ts).total_seconds())
        except Exception:
            duration_seconds = 0

    pipeline_status = "unknown"
    if any(
        str(ev.get("event_type", "")) == EventType.PIPELINE_CONCLUSION.value
        and bool((ev.get("payload") or {}).get("approved", False))
        for ev in health_events
    ):
        pipeline_status = "approved"
    elif security_blocked_count > 0:
        pipeline_status = "security_blocked"
    elif qa_failed_count > 0:
        pipeline_status = "qa_failed"
    elif health_events:
        pipeline_status = "in_progress"

    return {
        "pipeline_status": pipeline_status,
        "first_event_at": first_ts.isoformat() if first_ts else None,
        "last_event_at": last_ts.isoformat() if last_ts else None,
        "duration_seconds": duration_seconds,
        "qa_retry_count": qa_retry_count,
        "qa_failed_count": qa_failed_count,
        "security_blocked_count": security_blocked_count,
    }


def _count_replans_for_plan(
    events: list[dict[str, Any]],
    plan_id: str,
) -> int:
    """
    Count how many replanning events in the list target the given original plan_id.
    """
    count = 0
    for ev in events:
        payload = ev.get("payload") or {}
        if str(payload.get("original_plan_id", "")) == plan_id:
            count += 1
    return count


def _build_plan_detail_json(
    plan_id: str,
    metrics: dict[str, Any],
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compose a high-level "plan detail" JSON document from raw metrics, tasks and events.

    This is intentionally conservative: it avoids heavy processing and focuses on
    the most useful signals for the frontend (prompt, planner reasoning, tasks,
    QA/Security outcomes, replans and a small event sample).
    """
    original_prompt = ""
    planner_reasoning = ""
    created_at = None

    qa_outcomes: list[dict[str, Any]] = []
    code_history: dict[str, list[dict[str, Any]]] = {}
    security_outcome: dict[str, Any] | None = None
    replans: list[dict[str, Any]] = []

    for ev in events or []:
        etype = str(ev.get("event_type", ""))
        payload = ev.get("payload") or {}
        if not created_at and isinstance(ev.get("created_at"), str):
            created_at = ev["created_at"]

        if etype == "plan.created":
            original_prompt = str(payload.get("original_prompt", "")).strip()
            planner_reasoning = str(payload.get("reasoning", "")).strip()
        elif etype == "code.generated":
            task_id = str(payload.get("task_id", ""))
            file_path = str(payload.get("file_path", "") or "")
            language = str(payload.get("language", "") or "")
            code = str(payload.get("code", "") or "")
            reasoning = str(payload.get("reasoning", "") or "")
            qa_attempt = int(payload.get("qa_attempt", 0) or 0)
            if task_id:
                history_list = code_history.setdefault(task_id, [])
                history_list.append(
                    {
                        "qa_attempt": qa_attempt,
                        "code": code,
                        "reasoning": reasoning,
                        "file_path": file_path,
                        "language": language,
                    }
                )
        elif etype == "qa.failed":
            qa_outcomes.append(
                {
                    "task_id": payload.get("task_id"),
                    "module": payload.get("module", ""),
                    "severity_hint": payload.get("severity_hint", "medium"),
                    "issues": payload.get("issues") or [],
                    "reasoning": payload.get("reasoning", ""),
                    "qa_attempt": payload.get("qa_attempt", 0),
                }
            )
        elif etype == "security.approved" or etype == "security.blocked":
            security_outcome = {
                "approved": bool(payload.get("approved", False)),
                "severity_hint": payload.get("severity_hint", "medium"),
                "violations": payload.get("violations") or [],
                "reasoning": payload.get("reasoning", ""),
                "files_scanned": payload.get("files_scanned", 0),
            }
        elif etype == "plan.revision_suggested" or etype == "plan.revision_confirmed":
            replans.append(
                {
                    "event_type": etype,
                    "severity": payload.get("severity", "medium"),
                    "reason": payload.get("reason", ""),
                    "summary": payload.get("summary", ""),
                    "target_group_ids": payload.get("target_group_ids") or [],
                    "suggestions": payload.get("suggestions") or [],
                    "original_plan_id": payload.get("original_plan_id", ""),
                    "new_plan_id": payload.get("new_plan_id", ""),
                }
            )

    task_summaries: list[dict[str, Any]] = []
    for t in tasks or []:
        tid = str(t.get("task_id", ""))
        history_list = code_history.get(tid) or []
        history_list.sort(key=lambda h: int(h.get("qa_attempt", 0) or 0))
        latest = history_list[-1] if history_list else {}
        task_summaries.append(
            {
                "task_id": t.get("task_id"),
                "file_path": t.get("file_path", ""),
                "language": t.get("language", ""),
                "group_id": t.get("group_id", ""),
                "status": t.get("status", ""),
                "qa_attempt": t.get("qa_attempt", 0),
                "code": latest.get("code", ""),
                "dev_reasoning": latest.get("reasoning", ""),
                "code_history": history_list,
            }
        )

    modules_map: dict[str, dict[str, Any]] = {}
    for t in task_summaries:
        gid = str(t.get("group_id", "") or "root")
        mod = modules_map.setdefault(
            gid,
            {
                "group_id": gid,
                "tasks_count": 0,
                "qa_failed_count": 0,
                "max_severity_hint": "low",
            },
        )
        mod["tasks_count"] += 1

    for qa in qa_outcomes:
        task_id = qa.get("task_id")
        severity = str(qa.get("severity_hint", "medium") or "medium")
        group_id = "root"
        for t in task_summaries:
            if t.get("task_id") == task_id:
                group_id = str(t.get("group_id", "") or "root")
                break
        mod = modules_map.setdefault(
            group_id,
            {
                "group_id": group_id,
                "tasks_count": 0,
                "qa_failed_count": 0,
                "max_severity_hint": "low",
            },
        )
        mod["qa_failed_count"] += 1
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        current = str(mod.get("max_severity_hint", "low") or "low")
        if order.get(severity, 1) > order.get(current, 0):
            mod["max_severity_hint"] = severity

    modules_summary = list(modules_map.values())

    max_events = 80
    events_sample = events[:max_events] if isinstance(events, list) else []

    detail: dict[str, Any] = {
        "plan_id": plan_id,
        "created_at": created_at,
        "status": metrics.get("pipeline_status", "unknown"),
        "original_prompt": original_prompt,
        "planner_reasoning": planner_reasoning,
        "mode": metrics.get("mode", "normal"),
        "metrics": metrics,
        "tasks": task_summaries,
        "modules": modules_summary,
        "qa_outcomes": qa_outcomes,
        "security_outcome": security_outcome or {},
        "replans": {"items": replans},
        "events": events_sample,
    }
    return detail
