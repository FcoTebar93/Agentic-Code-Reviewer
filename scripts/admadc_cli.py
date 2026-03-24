"""
ADMADC CLI — lightweight client for the gateway API.

Usage:
  python scripts/admadc_cli.py status
  python scripts/admadc_cli.py plan --prompt "Add a health endpoint" [--mode save]
  python scripts/admadc_cli.py events [--limit 20]
  python scripts/admadc_cli.py tasks <plan_id>
  python scripts/admadc_cli.py metrics <plan_id>
  python scripts/admadc_cli.py approvals
  python scripts/admadc_cli.py approve <approval_id>
  python scripts/admadc_cli.py reject <approval_id>
  python scripts/admadc_cli.py replan --payload '{"original_plan_id":"...", ...}'

Environment:
  ADMADC_GATEWAY_URL  Base URL for the gateway (default: http://localhost:8080)

Config file (optional, for profiles):
  ~/.admadc/config.json
    {
      "default_profile": "local",
      "profiles": {
        "local":  { "base": "http://localhost:8080" },
        "staging": { "base": "https://staging-gateway.example.com" }
      }
    }
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

try:
    import httpx
except ImportError:
    print("error: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

DEFAULT_BASE = os.environ.get("ADMADC_GATEWAY_URL", "http://localhost:8080")
CONFIG_PATH = os.path.expanduser("~/.admadc/config.json")


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


def _load_base_from_profile(profile: str | None, base_arg: str | None) -> str:
    """
    Resolve the final base URL combining configuration and flags.

    Priority order:
    1) If --profile is provided, use profiles[profile].base from ~/.admadc/config.json.
    2) Else, if ~/.admadc/config.json has "default_profile", use that profile's base.
    3) Else, fall back to --base (if provided).
    4) Else, fall back to DEFAULT_BASE / ADMADC_GATEWAY_URL.
    """
    cfg: dict[str, Any] | None = None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = None
    except Exception as exc:
        print(
            f"[profiles] Could not read {CONFIG_PATH}: {exc}. "
            "Using --base or ADMADC_GATEWAY_URL instead.",
            file=sys.stderr,
        )
        cfg = None

    selected_profile = profile
    if cfg is not None and not selected_profile:
        default_profile = cfg.get("default_profile")
        if isinstance(default_profile, str) and default_profile:
            selected_profile = default_profile

    if not cfg or not selected_profile:
        return (base_arg or DEFAULT_BASE).rstrip("/")

    profiles = cfg.get("profiles") or {}
    profile_cfg = profiles.get(selected_profile)
    if not isinstance(profile_cfg, dict) or "base" not in profile_cfg:
        print(
            f"[profiles] Profile '{selected_profile}' not found or missing 'base' in {CONFIG_PATH}. "
            "Using --base or ADMADC_GATEWAY_URL instead.",
            file=sys.stderr,
        )
        return (base_arg or DEFAULT_BASE).rstrip("/")

    base = str(profile_cfg.get("base") or "").strip()
    if not base:
        print(
            f"[profiles] Profile '{selected_profile}' has empty 'base' in {CONFIG_PATH}. "
            "Using --base or ADMADC_GATEWAY_URL instead.",
            file=sys.stderr,
        )
        return (base_arg or DEFAULT_BASE).rstrip("/")

    print(f"[profiles] Using profile '{selected_profile}' with base={base}", file=sys.stderr)
    return base.rstrip("/")


def _build_service_url(base: str, port: int) -> str:
    """
    Build a service URL (http://host:port) reusing the host/scheme from the gateway base URL.

    This assumes the default docker-compose deployment (ports 8001..8007, 8003, 8004, 8005, 8006).
    """
    parsed = urlparse(base)
    host = parsed.hostname or "localhost"
    scheme = parsed.scheme or "http"
    return f"{scheme}://{host}:{port}"


def cmd_status(base: str) -> None:
    with _get_client(base) as client:
        r = client.get("/api/status")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def _normalize_cli_user_locale(raw: str) -> str:
    """Match shared.prompt_locale.normalize_user_locale (primary BCP-47 tag)."""
    if not raw or not str(raw).strip():
        return "en"
    loc = str(raw).strip().lower().replace("_", "-")
    primary = loc.split("-", 1)[0]
    if primary in {"en", "es", "fr", "de", "pt", "it", "ja", "zh", "ko"}:
        return primary
    return "en"


def cmd_plan(
    base: str,
    prompt: str,
    project: str = "default",
    repo_url: str = "",
    mode: str = "normal",
    user_locale: str = "en",
) -> str | None:
    with _get_client(base) as client:
        body = {
            "prompt": prompt,
            "project_name": project,
            "repo_url": repo_url or "",
            "user_locale": _normalize_cli_user_locale(user_locale),
        }
        mode_norm = (mode or "normal").strip().lower()
        if mode_norm not in {"normal", "save"}:
            # Backwards-compatible alias for older scripts that used "ahorro"
            if mode_norm == "ahorro":
                mode_norm = "save"
            else:
                mode_norm = "normal"
        body["mode"] = mode_norm
        r = client.post("/api/plan", json=body)
        r.raise_for_status()
        data = r.json()
        print(json.dumps(data, indent=2))
        plan_id = data.get("plan_id")
        if plan_id:
            print(f"\n# Plan ID: {plan_id}", file=sys.stderr)
        return plan_id


def cmd_events(
    base: str,
    limit: int = 50,
    plan_id: str | None = None,
    event_type: str | None = None,
) -> None:
    with _get_client(base) as client:
        params: dict[str, Any] = {"limit": limit}
        if plan_id:
            params["plan_id"] = plan_id
        if event_type:
            params["event_type"] = event_type
        r = client.get("/api/events", params=params)
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


def cmd_metrics(base: str, plan_id: str, watch: bool = False, interval: float = 5.0) -> None:
    if not watch:
        with _get_client(base) as client:
            r = client.get(f"/api/plan_metrics/{plan_id}")
            r.raise_for_status()
            print(json.dumps(r.json(), indent=2))
        return

    with _get_client(base) as client:
        print(
            f"# Watching metrics for plan {plan_id} (every {interval:.1f}s). Ctrl+C to stop.",
            file=sys.stderr,
        )
        while True:
            try:
                r = client.get(f"/api/plan_metrics/{plan_id}")
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                print(f"[metrics] error: {exc}", file=sys.stderr)
                time.sleep(interval)
                continue

            status = data.get("pipeline_status", "unknown")
            total_tokens = data.get("total_tokens", 0)
            cost = data.get("estimated_cost_total_usd", 0.0)
            qa_failed = data.get("qa_failed_count", 0)
            security_blocked = data.get("security_blocked_count", 0)
            ts = time.strftime("%H:%M:%S")
            print(
                f"[{ts}] status={status} tokens={total_tokens} "
                f"cost=${cost:.4f} qa_failed={qa_failed} security_blocked={security_blocked}"
            )

            if status in {"approved", "security_blocked", "qa_failed"}:
                print("# Pipeline finished, stopping metrics watch.", file=sys.stderr)
                break

            time.sleep(interval)


def cmd_approvals(
    base: str,
    plan_id: str | None = None,
    auto_approve: bool = False,
) -> None:
    with _get_client(base) as client:
        r = client.get("/api/approvals")
        r.raise_for_status()
        data = r.json()

        pending = data.get("pending", [])
        if not isinstance(pending, list):
            pending = []

        if plan_id:
            pending = [
                a for a in pending if str(a.get("plan_id", "")) == plan_id
            ]

        if not auto_approve:
            out = {
                "pending": pending,
                "count": len(pending),
            }
            print(json.dumps(out, indent=2))
            return

        if not pending:
            print("# No pending approvals match the current filter.", file=sys.stderr)
            return

        print(
            f"# Auto-approving {len(pending)} pending approval(s)"
            + (f" for plan_id={plan_id}" if plan_id else "")
            + "...",
            file=sys.stderr,
        )

        for a in pending:
            approval_id = a.get("approval_id") or a.get("id")
            if not approval_id:
                continue
            try:
                ar = client.post(f"/api/approvals/{approval_id}/approve")
                ar.raise_for_status()
                print(
                    f"approved {approval_id}: "
                    f"{json.dumps(ar.json(), ensure_ascii=False)}"
                )
            except Exception as exc:
                print(
                    f"[auto-approve] error approving {approval_id}: {exc}",
                    file=sys.stderr,
                )


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


def cmd_health(base: str) -> None:
    """
    Query /health for the gateway and core services (default ports).
    """
    services = {
        "gateway": base.rstrip("/"),
        "meta_planner": _build_service_url(base, 8001),
        "dev_service": _build_service_url(base, 8002),
        "github_service": _build_service_url(base, 8003),
        "memory_service": _build_service_url(base, 8004),
        "qa_service": _build_service_url(base, 8005),
        "security_service": _build_service_url(base, 8006),
        "replanner_service": _build_service_url(base, 8007),
    }

    print("# Health check for services (reusing scheme/host from ADMADC_GATEWAY_URL)\n")

    for name, url in services.items():
        health_url = f"{url}/health"
        try:
            r = httpx.get(health_url, timeout=5.0)
            status = r.status_code
            ok = status == 200
            body = r.json() if ok else {}
            service_name = body.get("service") or name
            print(f"{service_name:18s} [{status}] {'OK' if ok else 'FAIL'}  -> {health_url}")
        except Exception as exc:
            print(f"{name:18s} [ERR] FAIL  -> {health_url}  ({exc})")


def cmd_doctor(base: str) -> None:
    """
    Quick health diagnostic for the platform.

    - Prints the effective gateway base URL.
    - Shows gateway status (/api/status).
    - Runs cmd_health for /health on the core services.
    """
    print(f"# ADMADC doctor\n# Gateway base: {base}\n")

    print("## Gateway /api/status\n")
    try:
        with _get_client(base, timeout=5.0) as client:
            r = client.get("/api/status")
            r.raise_for_status()
            print(json.dumps(r.json(), indent=2))
    except Exception as exc:
        print(f"[doctor] Could not query /api/status on {base}: {exc}\n", file=sys.stderr)

    print("\n## Services /health\n")
    cmd_health(base)


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
        import websockets
    except ImportError:
        print(
            "error: websockets is required for watch-plan. "
            "Install with: pip install websockets",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ws_url = _build_ws_url(base)
    filt_types = [t.strip() for t in (event_types or []) if t.strip()]

    print(f"# Connecting to WebSocket {ws_url} for plan {plan_id}...", file=sys.stderr)

    async with websockets.connect(ws_url) as ws:
        print("# Connected. Press Ctrl+C to exit.\n", file=sys.stderr)
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
                if raw:
                    print(json.dumps(data, indent=2))
                else:
                    approval = data.get("approval") or {}
                    a_id = approval.get("approval_id", "") or approval.get("id", "")
                    status = approval.get("decision") or msg_type
                    print(f"[HITL] approval {a_id} -> {status}")


def cmd_shell(base: str) -> None:
    """
    Minimal interactive shell so you don't have to repeat flags.

    Commands (type 'help' inside the shell for a summary):
      status
      plan <prompt...>
      events [plan_id]
      tasks <plan_id>
      metrics [plan_id]
      approvals
      approve <approval_id>
      reject <approval_id>
      watch-plan [plan_id]
      quit / exit
    """
    last_plan_id: str | None = None
    print(f"# ADMADC shell (base={base})")
    print("# Type 'help' for commands, 'quit' or 'exit' to leave.\n")

    while True:
        try:
            line = input("admadc> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n# Leaving shell.", file=sys.stderr)
            break

        if not line:
            continue
        if line in {"quit", "exit"}:
            print("# Bye.")
            break
        if line == "help":
            print(
                "Commands:\n"
                "  status                       - show gateway status\n"
                "  plan <prompt...>             - create a plan (remembers plan_id)\n"
                "  events [plan_id]             - list recent events (optionally for a plan)\n"
                "  tasks <plan_id>              - list tasks for a plan\n"
                "  metrics [plan_id]            - show metrics for a plan (defaults to last plan)\n"
                "  approvals                    - list pending approvals\n"
                "  approve <approval_id>        - approve a PR\n"
                "  reject <approval_id>         - reject a PR\n"
                "  watch-plan [plan_id]         - stream events for a plan (defaults to last plan)\n"
                "  help                         - show this help\n"
                "  quit / exit                  - leave the shell\n"
            )
            continue

        parts = line.split()
        cmd = parts[0]
        args = parts[1:]

        try:
            if cmd == "status":
                cmd_status(base)
            elif cmd == "plan":
                if not args:
                    print("usage: plan <prompt...>", file=sys.stderr)
                    continue
                prompt = " ".join(args)
                plan_id = cmd_plan(base, prompt=prompt)
                if plan_id:
                    last_plan_id = plan_id
            elif cmd == "events":
                plan_id = args[0] if args else None
                cmd_events(base, plan_id=plan_id)
            elif cmd == "tasks":
                if not args:
                    print("usage: tasks <plan_id>", file=sys.stderr)
                    continue
                cmd_tasks(base, args[0])
            elif cmd == "metrics":
                plan_id = args[0] if args else last_plan_id
                if not plan_id:
                    print(
                        "metrics: no plan_id provided and no last plan_id known.",
                        file=sys.stderr,
                    )
                    continue
                cmd_metrics(base, plan_id)
            elif cmd == "approvals":
                cmd_approvals(base)
            elif cmd == "approve":
                if not args:
                    print("usage: approve <approval_id>", file=sys.stderr)
                    continue
                cmd_approve(base, args[0])
            elif cmd == "reject":
                if not args:
                    print("usage: reject <approval_id>", file=sys.stderr)
                    continue
                cmd_reject(base, args[0])
            elif cmd == "watch-plan":
                plan_id = args[0] if args else last_plan_id
                if not plan_id:
                    print(
                        "watch-plan: no plan_id provided and no last plan_id known.",
                        file=sys.stderr,
                    )
                    continue
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
                    print("\n# watch-plan stopped by user", file=sys.stderr)
            else:
                print(f"unknown command: {cmd!r}. Type 'help' for a list of commands.")
        except Exception as exc:
            print(f"[shell] error running '{cmd}': {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ADMADC CLI — gateway API client",
        epilog="Set ADMADC_GATEWAY_URL for a custom gateway base URL.",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Gateway base URL (default: profile base, then env ADMADC_GATEWAY_URL or http://localhost:8080)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=f"Named profile from {CONFIG_PATH} (e.g. local, staging, prod)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show gateway status (connections, pending approvals)")
    sub.add_parser("health", help="Check /health for core services (gateway, meta_planner, dev, qa, etc.)")
    sub.add_parser("doctor", help="Run a quick diagnostic over gateway and core services")
    sub.add_parser("shell", help="Start an interactive ADMADC shell (REPL-style CLI)")

    p_plan = sub.add_parser("plan", help="Create a new plan (POST /api/plan)")
    p_plan.add_argument("--prompt", required=True, help="User prompt for the plan")
    p_plan.add_argument("--project", default="default", help="Project name")
    p_plan.add_argument("--repo-url", default="", help="GitHub repo URL (optional)")
    p_plan.add_argument(
        "--mode",
        choices=["normal", "save", "ahorro"],
        default="normal",
        help="normal = full context; save = reduced-token mode (alias: 'ahorro')",
    )
    p_plan.add_argument(
        "--locale",
        default="en",
        metavar="TAG",
        help="Agent response language (primary BCP-47 tag, e.g. es, en, fr). Default: en.",
    )
    p_plan.add_argument(
        "--watch",
        action="store_true",
        help="After creating the plan, stream its events in real time (WebSocket)",
    )

    p_events = sub.add_parser("events", help="List recent events (GET /api/events)")
    p_events.add_argument("--limit", type=int, default=50, help="Max events to return")
    p_events.add_argument(
        "--plan-id",
        default=None,
        help="Filter events by plan_id",
    )
    p_events.add_argument(
        "--event-type",
        default=None,
        help="Filter events by event_type (e.g. code.generated, qa.failed)",
    )

    p_tasks = sub.add_parser("tasks", help="Get tasks for a plan (GET /api/tasks/{plan_id})")
    p_tasks.add_argument("plan_id", help="Plan ID")

    p_metrics = sub.add_parser(
        "metrics",
        help="Get plan metrics: tokens, pipeline status, duration (GET /api/plan_metrics/{plan_id})",
    )
    p_metrics.add_argument("plan_id", help="Plan ID")
    p_metrics.add_argument(
        "--watch",
        action="store_true",
        help="Watch metrics in a loop until the pipeline finishes",
    )
    p_metrics.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between metrics refreshes when using --watch (default: 5.0)",
    )

    p_approvals = sub.add_parser("approvals", help="List (and optionally auto-approve) pending human approvals")
    p_approvals.add_argument(
        "--plan-id",
        default=None,
        help="Filter pending approvals by plan_id",
    )
    p_approvals.add_argument(
        "--auto-approve",
        action="store_true",
        help="Approve all pending approvals matching the optional filters",
    )

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
    base = _load_base_from_profile(getattr(args, "profile", None), args.base)

    if args.command == "status":
        cmd_status(base)
    elif args.command == "health":
        cmd_health(base)
    elif args.command == "doctor":
        cmd_doctor(base)
    elif args.command == "shell":
        cmd_shell(base)
    elif args.command == "plan":
        plan_id = cmd_plan(
            base,
            prompt=args.prompt,
            project=args.project,
            repo_url=args.repo_url or "",
            mode=args.mode,
            user_locale=args.locale,
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
                print("\n# watch-plan stopped by user", file=sys.stderr)
    elif args.command == "events":
        cmd_events(base, limit=args.limit, plan_id=args.plan_id, event_type=args.event_type)
    elif args.command == "tasks":
        cmd_tasks(base, args.plan_id)
    elif args.command == "metrics":
        cmd_metrics(base, args.plan_id, watch=args.watch, interval=args.interval)
    elif args.command == "approvals":
        cmd_approvals(
            base,
            plan_id=getattr(args, "plan_id", None),
            auto_approve=getattr(args, "auto_approve", False),
        )
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
            print("\n# watch-plan stopped by user", file=sys.stderr)


if __name__ == "__main__":
    main()
