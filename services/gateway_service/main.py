"""
Gateway Service -- single entry point for the React frontend.

Responsibilities:
1. WebSocket /ws  -- subscribe to ALL RabbitMQ events and broadcast to clients
2. POST /api/plan -- proxy to meta_planner
3. GET  /api/events -- proxy to memory_service
4. GET  /api/tasks/{plan_id} -- proxy to memory_service
5. GET  /api/status -- current pipeline state (connections + recent events)
6. HITL approval endpoints:
   GET  /api/approvals          -- list pending human approvals
   POST /api/approvals/{id}/approve -- approve a PR (publishes pr.human_approved)
   POST /api/approvals/{id}/reject  -- reject a PR (publishes pr.human_rejected)

Design: the gateway intercepts security.approved events and holds them for
human review before forwarding to github_service via pr.human_approved.
All other events are forwarded transparently.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.logging.logger import setup_logging
from shared.observability.metrics import metrics_response
from shared.contracts.events import (
    BaseEvent,
    EventType,
    SecurityResultPayload,
    PrApprovalPayload,
    PipelineConclusionPayload,
    PlanRevisionPayload,
    plan_revision_confirmed,
    pr_pending_approval,
    pr_human_approved,
    pr_human_rejected,
    pipeline_conclusion,
)
from shared.utils.rabbitmq import EventBus
from services.gateway_service.config import GatewayConfig
from services.gateway_service.ws_manager import ConnectionManager

SERVICE_NAME = "gateway_service"
event_bus: EventBus | None = None
http_client: httpx.AsyncClient | None = None
cfg: GatewayConfig | None = None
manager = ConnectionManager()

_pending_approvals: dict[str, PrApprovalPayload] = {}

_PLAN_IDEM_TTL_SECONDS = int(os.environ.get("GATEWAY_PLAN_IDEM_TTL_SECONDS", "45"))
_plan_idem_cache: dict[str, tuple[dict, float]] = {}


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = GatewayConfig.from_env()
    timeout = float(os.environ.get("GATEWAY_HTTP_TIMEOUT", "120.0"))
    http_client = httpx.AsyncClient(timeout=timeout)

    event_bus = EventBus(cfg.rabbitmq_url)

    async def _connect_and_consume():
        await event_bus.connect()
        asyncio.create_task(_consume_all_events())
        asyncio.create_task(_consume_security_approved())
        logger.info("Gateway RabbitMQ consumers active")

    asyncio.create_task(_connect_and_consume())
    logger.info("Gateway Service ready — WebSocket broadcast + HITL approval active")
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - Gateway Service",
    version="0.2.0",
    description="WebSocket gateway, HTTP proxy, and Human-in-the-Loop approval system",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(SERVICE_NAME)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "ws_connections": manager.connection_count,
        "pending_approvals": len(_pending_approvals),
    }


@app.get("/metrics")
async def metrics():
    return metrics_response()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        if http_client and cfg:
            try:
                resp = await http_client.get(
                    f"{cfg.memory_service_url}/events",
                    params={"limit": 20},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("value", data) if isinstance(data, dict) else data
                    for evt in reversed(events[:20]):
                        await websocket.send_text(
                            json.dumps({"type": "history", "event": evt})
                        )
            except Exception:
                logger.warning("Could not fetch history for new WebSocket client")

        for approval in _pending_approvals.values():
            await websocket.send_text(
                json.dumps({"type": "approval", "approval": approval.model_dump()})
            )

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket error")
        manager.disconnect(websocket)

def _proxy_json(resp: Any) -> dict[str, Any]:
    """Parse JSON response; avoid 'Expecting value' when upstream returns empty/non-JSON."""
    text = (resp.text or "").strip()
    if not text:
        return {"error": "Upstream returned empty response", "status": resp.status_code}
    try:
        return resp.json()
    except Exception as e:
        return {"error": f"Invalid upstream response: {e}", "body_preview": text[:200]}


@app.post("/api/plan")
async def create_plan(request_body: dict[str, Any]):
    """
    Proxy POST /plan to meta_planner.
    Idempotencia: misma petición (prompt|project_name|repo_url) en 45s devuelve
    la respuesta cacheada sin llamar de nuevo al meta_planner (evita 4x tokens por doble envío).
    """
    try:
        prompt = (request_body.get("prompt") or "").strip()
        project_name = (request_body.get("project_name") or "default").strip()
        repo_url = (request_body.get("repo_url") or "").strip()
        key = hashlib.sha256(
            f"{prompt}|{project_name}|{repo_url}".encode()
        ).hexdigest()
        now = time.monotonic()
        if key in _plan_idem_cache:
            cached_content, cached_at = _plan_idem_cache[key]
            if now - cached_at < _PLAN_IDEM_TTL_SECONDS:
                logger.info(
                    "Plan idempotent (same request within %ds), returning cached response",
                    _PLAN_IDEM_TTL_SECONDS,
                )
                return JSONResponse(content=cached_content, status_code=200)
            del _plan_idem_cache[key]

        resp = await http_client.post(
            f"{cfg.meta_planner_url}/plan",
            json=request_body,
        )
        content = _proxy_json(resp)
        if resp.status_code == 200 and isinstance(content, dict) and "plan_id" in content:
            _plan_idem_cache[key] = (content, now)
        return JSONResponse(content=content, status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/plan")
        return JSONResponse(
            content={"error": str(exc)}, status_code=502
        )


@app.post("/api/replan")
async def confirm_replan(request_body: dict[str, Any]):
  """
  Human-confirmed replan endpoint.

  The frontend sends the payload of a plan.revision_suggested event, which
  must match PlanRevisionPayload. The gateway republishes it as
  plan.revision_confirmed so meta_planner can trigger a new plan.
  """
  try:
      payload = PlanRevisionPayload.model_validate(request_body)
  except Exception as exc:
      return JSONResponse(
          content={"error": f"Invalid PlanRevisionPayload: {exc}"},
          status_code=400,
      )

  event = plan_revision_confirmed(SERVICE_NAME, payload)
  await event_bus.publish(event)
  await manager.broadcast(
      json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
  )

  return {"status": "ok", "original_plan_id": payload.original_plan_id, "new_plan_id": payload.new_plan_id}


@app.get("/api/events")
async def get_events():
    """Proxy GET /events to memory_service."""
    try:
        resp = await http_client.get(f"{cfg.memory_service_url}/events")
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/events")
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@app.get("/api/tasks/{plan_id}")
async def get_tasks(plan_id: str):
    """Proxy GET /tasks/{plan_id} to memory_service."""
    try:
        resp = await http_client.get(
            f"{cfg.memory_service_url}/tasks/{plan_id}"
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as exc:
        logger.exception("Failed to proxy /api/tasks/%s", plan_id)
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@app.get("/api/plan_metrics/{plan_id}")
async def get_plan_metrics(plan_id: str):
    """
    Aggregate LLM token usage for a plan from metrics.tokens_used events.

    Returns total and per-service prompt/completion token counts.
    """
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

        by_service: dict[str, dict[str, float]] = {}
        total_prompt = 0
        total_completion = 0
        for ev in token_events:
            p = ev.get("payload") or {}
            svc = str(p.get("service", "unknown"))
            pt = int(p.get("prompt_tokens", 0) or 0)
            ct = int(p.get("completion_tokens", 0) or 0)
            if svc not in by_service:
                by_service[svc] = {"prompt_tokens": 0.0, "completion_tokens": 0.0}
            by_service[svc]["prompt_tokens"] += pt
            by_service[svc]["completion_tokens"] += ct
            total_prompt += pt
            total_completion += ct

        prompt_price = cfg.llm_prompt_price_per_1k if cfg else 0.0
        completion_price = cfg.llm_completion_price_per_1k if cfg else 0.0

        prompt_cost = (total_prompt / 1000.0) * prompt_price
        completion_cost = (total_completion / 1000.0) * completion_price
        total_cost = prompt_cost + completion_cost

        by_service_list: list[dict[str, float | str]] = []
        for s, v in sorted(by_service.items()):
            svc_prompt = v["prompt_tokens"]
            svc_completion = v["completion_tokens"]
            svc_prompt_cost = (svc_prompt / 1000.0) * prompt_price
            svc_completion_cost = (svc_completion / 1000.0) * completion_price
            by_service_list.append(
                {
                    "service": s,
                    "prompt_tokens": int(svc_prompt),
                    "completion_tokens": int(svc_completion),
                    "total_tokens": int(svc_prompt + svc_completion),
                    "estimated_cost_prompt_usd": svc_prompt_cost,
                    "estimated_cost_completion_usd": svc_completion_cost,
                    "estimated_cost_total_usd": svc_prompt_cost + svc_completion_cost,
                }
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
                    for ev in events_sugg:
                        payload = ev.get("payload") or {}
                        if str(payload.get("original_plan_id", "")) == plan_id:
                            replan_suggestions_count += 1
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
                    for ev in events_conf:
                        payload = ev.get("payload") or {}
                        if str(payload.get("original_plan_id", "")) == plan_id:
                            replan_confirmed_count += 1
        except Exception:
            logger.warning(
                "Failed to fetch plan.revision_confirmed events for health metrics"
            )

        return {
            "plan_id": plan_id,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "estimated_cost_prompt_usd": prompt_cost,
            "estimated_cost_completion_usd": completion_cost,
            "estimated_cost_total_usd": total_cost,
            "pipeline_status": pipeline_status,
            "first_event_at": first_ts.isoformat() if first_ts else None,
            "last_event_at": last_ts.isoformat() if last_ts else None,
            "duration_seconds": duration_seconds,
            "qa_retry_count": qa_retry_count,
            "qa_failed_count": qa_failed_count,
            "security_blocked_count": security_blocked_count,
            "replan_suggestions_count": replan_suggestions_count,
            "replan_confirmed_count": replan_confirmed_count,
            "by_service": by_service_list,
        }
    except Exception as exc:
        logger.exception("Failed to get plan_metrics for %s", plan_id[:8])
        return JSONResponse(content={"error": str(exc)}, status_code=502)


@app.get("/api/status")
async def get_status():
    return {
        "ws_connections": manager.connection_count,
        "pending_approvals": len(_pending_approvals),
        "service": SERVICE_NAME,
    }

@app.get("/api/approvals")
async def list_approvals():
    """Return all pending human approvals."""
    return {
        "pending": [a.model_dump() for a in _pending_approvals.values()],
        "count": len(_pending_approvals),
    }


@app.post("/api/approvals/{approval_id}/approve")
async def approve_pr(approval_id: str):
    """
    Human approves a PR.
    Publishes pr.human_approved and forwards to github_service via RabbitMQ.
    """
    approval = _pending_approvals.get(approval_id)
    if not approval:
        return JSONResponse(
            content={"error": f"Approval {approval_id} not found or already decided"},
            status_code=404,
        )

    approval.decision = "approved"
    _pending_approvals.pop(approval_id, None)

    event = pr_human_approved(SERVICE_NAME, approval)
    await event_bus.publish(event)

    await manager.broadcast(
        json.dumps({"type": "approval_decided", "approval": approval.model_dump()})
    )
    await manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )

    logger.info(
        "Human APPROVED PR for plan %s (approval %s)",
        approval.plan_id[:8],
        approval_id[:8],
    )
    return {"status": "approved", "plan_id": approval.plan_id}


@app.post("/api/approvals/{approval_id}/reject")
async def reject_pr(approval_id: str):
    """
    Human rejects a PR.
    Publishes pr.human_rejected and removes the pending approval.
    """
    approval = _pending_approvals.get(approval_id)
    if not approval:
        return JSONResponse(
            content={"error": f"Approval {approval_id} not found or already decided"},
            status_code=404,
        )

    approval.decision = "rejected"
    _pending_approvals.pop(approval_id, None)

    event = pr_human_rejected(SERVICE_NAME, approval)
    await event_bus.publish(event)

    await manager.broadcast(
        json.dumps({"type": "approval_decided", "approval": approval.model_dump()})
    )
    await manager.broadcast(
        json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
    )

    logger.info(
        "Human REJECTED PR for plan %s (approval %s)",
        approval.plan_id[:8],
        approval_id[:8],
    )
    return {"status": "rejected", "plan_id": approval.plan_id}

async def _consume_all_events() -> None:
    """Broadcast every event on the bus to connected WebSocket clients."""

    async def handler(event: BaseEvent) -> None:
        payload = json.dumps({"type": "event", "event": json.loads(event.model_dump_json())})
        await manager.broadcast(payload)
        logger.debug(
            "Broadcast %s to %d clients",
            event.event_type.value,
            manager.connection_count,
        )

    await event_bus.subscribe(
        queue_name="gateway_service.broadcast",
        routing_keys=["#"],
        handler=handler,
        max_retries=1,
    )


async def _consume_security_approved() -> None:
    """
    Intercept security.approved events to create pending human approvals.

    Instead of letting github_service react directly to security.approved,
    the gateway holds the approval request until a human reviews it
    via the frontend and clicks Approve or Reject.
    """

    async def handler(event: BaseEvent) -> None:
        sec = SecurityResultPayload.model_validate(event.payload)
        if not sec.approved or not sec.pr_context:
            return

        files_changed: list[str] = []
        pr_files = sec.pr_context.get("files")
        if isinstance(pr_files, list):
            for f in pr_files:
                if isinstance(f, dict) and "file_path" in f:
                    files_changed.append(str(f["file_path"]))

        conclusion_payload = PipelineConclusionPayload(
            plan_id=sec.plan_id,
            branch_name=sec.branch_name,
            conclusion_text=sec.reasoning,
            files_changed=files_changed,
            approved=sec.approved,
        )
        conclusion_event = pipeline_conclusion(SERVICE_NAME, conclusion_payload)
        await event_bus.publish(conclusion_event)
        try:
            await http_client.post(
                f"{cfg.memory_service_url}/events",
                json=json.loads(conclusion_event.model_dump_json()),
            )
        except Exception:
            logger.warning("Could not store pipeline.conclusion in memory_service")

        approval = PrApprovalPayload(
            plan_id=sec.plan_id,
            branch_name=sec.branch_name,
            files_count=sec.files_scanned,
            security_reasoning=sec.reasoning,
            pr_context=sec.pr_context,
        )
        _pending_approvals[approval.approval_id] = approval

        pending_event = pr_pending_approval(SERVICE_NAME, approval)
        await event_bus.publish(pending_event)

        await manager.broadcast(
            json.dumps({"type": "approval", "approval": approval.model_dump()})
        )

        logger.info(
            "PR approval pending for plan %s (approval_id %s). "
            "Waiting for human decision.",
            sec.plan_id[:8],
            approval.approval_id[:8],
        )

    await event_bus.subscribe(
        queue_name="gateway_service.hitl_approvals",
        routing_keys=[EventType.SECURITY_APPROVED.value],
        handler=handler,
        max_retries=1,
    )
