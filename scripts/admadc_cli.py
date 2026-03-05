"""
ADMADC CLI — lightweight client for the gateway API.

Usage:
  python scripts/admadc_cli.py status
  python scripts/admadc_cli.py plan --prompt "Add a health endpoint" [--mode ahorro]
  python scripts/admadc_cli.py events [--limit 20]
  python scripts/admadc_cli.py tasks <plan_id>
  python scripts/admadc_cli.py metrics <plan_id>
  python scripts/admadc_cli.py approvals
  python scripts/admadc_cli.py approve <approval_id>
  python scripts/admadc_cli.py reject <approval_id>
  python scripts/admadc_cli.py replan --payload '{"original_plan_id":"...", ...}'

Environment:
  ADMADC_GATEWAY_URL  Base URL for the gateway (default: http://localhost:8080)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any
from urllib.parse import urlparse, urlunparse

try:
    import httpx
except ImportError:
    print("error: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

DEFAULT_BASE = os.environ.get("ADMADC_GATEWAY_URL", "http://localhost:8080")


def _get_client(base: str, timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(base_url=base.rstrip("/"), timeout=timeout)


def _build_ws_url(base: str) -> str:
    """
    Convert the HTTP base URL into a WebSocket URL for /ws.

    Examples:
      http://localhost:8080 -> ws://localhost:8080/ws
      https://example.com   -> wss://example.com/ws
    """
    parsed = urlparse(base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = "/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def cmd_status(base: str) -> None:
    with _get_client(base) as client:
        r = client.get("/api/status")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def cmd_plan(
    base: str,
    prompt: str,
    project: str = "default",
    repo_url: str = "",
    mode: str = "normal",
) -> str | None:
    with _get_client(base) as client:
        body = {
            "prompt": prompt,
            "project_name": project,
            "repo_url": repo_url or "",
            "mode": "ahorro" if mode.lower() == "ahorro" else "normal",
        }
        r = client.post("/api/plan", json=body)
        r.raise_for_status()
        data = r.json()
        print(json.dumps(data, indent=2))
        plan_id = data.get("plan_id")
        if plan_id:
            print(f"\n# Plan ID: {plan_id}", file=sys.stderr)
        return plan_id


def cmd_events(base: str, limit: int = 50) -> None:
    with _get_client(base) as client:
        r = client.get("/api/events", params={"limit": limit})
        r.raise_for_status()
        events = r.json()
        if isinstance(events, list):
            print(json.dumps(events[:limit], indent=2))
        else:
            print(json.dumps(events, indent=2))


def cmd_tasks(base: str, plan_id: str) -> None:
    with _get_client(base) as client:
        r = client.get(f"/api/tasks/{plan_id}")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def cmd_metrics(base: str, plan_id: str) -> None:
    with _get_client(base) as client:
        r = client.get(f"/api/plan_metrics/{plan_id}")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def cmd_approvals(base: str) -> None:
    with _get_client(base) as client:
        r = client.get("/api/approvals")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def cmd_approve(base: str, approval_id: str) -> None:
    with _get_client(base) as client:
        r = client.post(f"/api/approvals/{approval_id}/approve")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def cmd_reject(base: str, approval_id: str) -> None:
    with _get_client(base) as client:
        r = client.post(f"/api/approvals/{approval_id}/reject")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def cmd_replan(base: str, payload: dict) -> None:
    with _get_client(base) as client:
        r = client.post("/api/replan", json=payload)
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def _event_matches_plan(ev: dict[str, Any], plan_id: str) -> bool:
    """Best-effort match of an event JSON to a given plan_id."""
    if not plan_id:
        return True
    payload = ev.get("payload") or {}
    if str(payload.get("plan_id", "")) == plan_id:
        return True
    if str(ev.get("plan_id", "")) == plan_id:
        return True
    return False


async def _watch_plan_async(
    base: str,
    plan_id: str,
    include_history: bool = True,
    raw: bool = False,
    event_types: list[str] | None = None,
) -> None:
    try:
        import websockets  # type: ignore[import]
    except ImportError:
        print(
            "error: websockets is required for watch-plan. "
            "Install with: pip install websockets",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ws_url = _build_ws_url(base)
    filt_types = [t.strip() for t in (event_types or []) if t.strip()]

    print(f"# Conectando a WebSocket {ws_url} para plan {plan_id}...", file=sys.stderr)

    async with websockets.connect(ws_url) as ws:  # type: ignore[attr-defined]
        print("# Conectado. Ctrl+C para salir.\n", file=sys.stderr)
        while True:
            msg = await ws.recv()
            try:
                data = json.loads(msg)
            except Exception:
                print(f"[raw] {msg}")
                continue

            msg_type = data.get("type")
            if msg_type == "history" and not include_history:
                continue

            if msg_type in {"history", "event"}:
                ev = data.get("event") or {}
                if not isinstance(ev, dict):
                    continue
                if not _event_matches_plan(ev, plan_id):
                    continue
                ev_type = str(ev.get("event_type", ""))
                if filt_types and ev_type not in filt_types:
                    continue

                if raw:
                    print(json.dumps(ev, indent=2))
                else:
                    created_at = ev.get("created_at", "?")
                    service = (ev.get("payload") or {}).get("service", ev.get("service", "?"))
                    print(f"[{created_at}] {ev_type} ({service})")

            elif msg_type in {"approval", "approval_decided"}:
                # Mensajes de aprobaciones HITL, los mostramos siempre
                if raw:
                    print(json.dumps(data, indent=2))
                else:
                    approval = data.get("approval") or {}
                    a_id = approval.get("approval_id", "") or approval.get("id", "")
                    status = approval.get("decision") or msg_type
                    print(f"[HITL] approval {a_id} -> {status}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ADMADC CLI — gateway API client",
        epilog="Set ADMADC_GATEWAY_URL for a custom gateway base URL.",
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help="Gateway base URL (default: env ADMADC_GATEWAY_URL or http://localhost:8080)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show gateway status (connections, pending approvals)")

    p_plan = sub.add_parser("plan", help="Create a new plan (POST /api/plan)")
    p_plan.add_argument("--prompt", required=True, help="User prompt for the plan")
    p_plan.add_argument("--project", default="default", help="Project name")
    p_plan.add_argument("--repo-url", default="", help="GitHub repo URL (optional)")
    p_plan.add_argument(
        "--mode",
        choices=["normal", "ahorro"],
        default="normal",
        help="normal = full context; ahorro = reduced tokens",
    )
    p_plan.add_argument(
        "--watch",
        action="store_true",
        help="Tras crear el plan, seguir sus eventos en tiempo real (WebSocket)",
    )

    p_events = sub.add_parser("events", help="List recent events (GET /api/events)")
    p_events.add_argument("--limit", type=int, default=50, help="Max events to return")

    p_tasks = sub.add_parser("tasks", help="Get tasks for a plan (GET /api/tasks/{plan_id})")
    p_tasks.add_argument("plan_id", help="Plan ID")

    p_metrics = sub.add_parser(
        "metrics",
        help="Get plan metrics: tokens, pipeline status, duration (GET /api/plan_metrics/{plan_id})",
    )
    p_metrics.add_argument("plan_id", help="Plan ID")

    sub.add_parser("approvals", help="List pending human approvals")
    p_approve = sub.add_parser("approve", help="Approve a PR (human-in-the-loop)")
    p_approve.add_argument("approval_id", help="Approval ID from /api/approvals")
    p_reject = sub.add_parser("reject", help="Reject a PR (human-in-the-loop)")
    p_reject.add_argument("approval_id", help="Approval ID from /api/approvals")

    p_replan = sub.add_parser(
        "replan",
        help="Confirm a plan revision (POST /api/replan). Payload via --payload or stdin.",
    )
    p_replan.add_argument(
        "--payload",
        type=str,
        default="",
        help="JSON PlanRevisionPayload (or read from stdin if omitted)",
    )

    p_watch = sub.add_parser(
        "watch-plan",
        help="Stream real-time events for a plan over WebSocket",
    )
    p_watch.add_argument("plan_id", help="Plan ID to filter events")
    p_watch.add_argument(
        "--raw",
        action="store_true",
        help="Print full raw event JSON instead of a compact line",
    )
    p_watch.add_argument(
        "--no-history",
        action="store_true",
        help="Do not show the initial history of recent events on connect",
    )
    p_watch.add_argument(
        "--event-type",
        action="append",
        default=[],
        help="Filter by event_type (can be used multiple times)",
    )

    args = parser.parse_args()
    base = args.base

    if args.command == "status":
        cmd_status(base)
    elif args.command == "plan":
        plan_id = cmd_plan(
            base,
            prompt=args.prompt,
            project=args.project,
            repo_url=args.repo_url or "",
            mode=args.mode,
        )
        if args.watch and plan_id:
            try:
                asyncio.run(
                    _watch_plan_async(
                        base,
                        plan_id=plan_id,
                        include_history=True,
                        raw=False,
                        event_types=None,
                    )
                )
            except KeyboardInterrupt:
                print("\n# watch-plan terminado por el usuario", file=sys.stderr)
    elif args.command == "events":
        cmd_events(base, limit=args.limit)
    elif args.command == "tasks":
        cmd_tasks(base, args.plan_id)
    elif args.command == "metrics":
        cmd_metrics(base, args.plan_id)
    elif args.command == "approvals":
        cmd_approvals(base)
    elif args.command == "approve":
        cmd_approve(base, args.approval_id)
    elif args.command == "reject":
        cmd_reject(base, args.approval_id)
    elif args.command == "replan":
        if args.payload:
            payload = json.loads(args.payload)
        else:
            payload = json.load(sys.stdin)
        cmd_replan(base, payload)
    elif args.command == "watch-plan":
        include_history = not getattr(args, "no_history", False)
        try:
            asyncio.run(
                _watch_plan_async(
                    base,
                    plan_id=args.plan_id,
                    include_history=include_history,
                    raw=args.raw,
                    event_types=args.event_type,
                )
            )
        except KeyboardInterrupt:
            print("\n# watch-plan terminado por el usuario", file=sys.stderr)


if __name__ == "__main__":
    main()
