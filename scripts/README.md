# ADMADC CLI

Lightweight command-line client to operate the platform via the Gateway API.

## Requirements

- Python 3.10+
- `httpx`: `pip install httpx` (or use the project environment where it is already installed)
- (Optional, for real-time streaming) `websockets`: `pip install websockets`

## Usage

Optional environment variable:

- `ADMADC_GATEWAY_URL`: gateway base URL (default: `http://localhost:8080`)

Optional config file for profiles:

- Path: `~/.admadc/config.json`
- Example:

```json
{
  "default_profile": "local",
  "profiles": {
    "local":  { "base": "http://localhost:8080" },
    "staging": { "base": "https://staging-gateway.example.com" }
  }
}
```

### Commands

| Command | Description |
|--------|-------------|
| `python scripts/admadc_cli.py status` | Gateway status (WS connections, pending approvals) |
| `python scripts/admadc_cli.py shell` | Start an interactive ADMADC shell (REPL-style CLI) |
| `python scripts/admadc_cli.py health` | Basic health for core services (`/health` on gateway, meta_planner, dev, qa, etc.) |
| `python scripts/admadc_cli.py doctor` | Quick diagnostic (shows gateway `/api/status` and runs `health` for services) |
| `python scripts/admadc_cli.py plan --prompt "..."` | Create a plan (options: `--project`, `--repo-url`, `--mode normal\|ahorro`, `--watch`) |
| `python scripts/admadc_cli.py events [--limit 20] [--plan-id ...] [--event-type ...]` | List recent events, with optional filters |
| `python scripts/admadc_cli.py tasks <plan_id>` | Tasks for a plan |
| `python scripts/admadc_cli.py metrics <plan_id> [--watch] [--interval 5]` | Plan metrics (tokens, pipeline status, duration), optional watch mode |
| `python scripts/admadc_cli.py approvals [--plan-id ...] [--auto-approve]` | List pending PR approvals (HITL) and optionally approve in batch |
| `python scripts/admadc_cli.py approve <approval_id>` | Approve a PR |
| `python scripts/admadc_cli.py reject <approval_id>` | Reject a PR |
| `python scripts/admadc_cli.py replan --payload '{"original_plan_id":"..."}'` | Confirm a replan (full `plan.revision_suggested` payload) |
| `python scripts/admadc_cli.py watch-plan <plan_id>` | Follow a plan’s events in real time (via WebSocket, requires `websockets`) |

### Examples

```bash
# Create a plan in "ahorro" (token-saving) mode
python scripts/admadc_cli.py plan --prompt "Add a /health endpoint" --mode ahorro

# Create a plan and follow it in real time with a single command
python scripts/admadc_cli.py plan --prompt "Add a /health endpoint" --watch

# Show metrics for a plan (use the plan_id returned by the plan command)
python scripts/admadc_cli.py metrics abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Confirm a replan (payload usually comes from a `plan.revision_suggested` event in the UI)
echo '{"original_plan_id":"...", "new_plan_id":"...", "reason":"...", "severity":"high", "suggestions":[]}' | python scripts/admadc_cli.py replan

# Follow a specific plan in real time
python scripts/admadc_cli.py watch-plan abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Show only events for a specific plan
python scripts/admadc_cli.py events --plan-id abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Show only `qa.failed` events for a plan
python scripts/admadc_cli.py events --plan-id abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx --event-type qa.failed

# Watch a plan's metrics until it finishes
python scripts/admadc_cli.py metrics abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx --watch --interval 3

# Check basic platform health
python scripts/admadc_cli.py health

# Run a quick diagnostic (status + health)
python scripts/admadc_cli.py doctor
```
