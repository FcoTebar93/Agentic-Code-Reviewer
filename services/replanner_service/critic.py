from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from shared.contracts.events import QAResultPayload, SecurityResultPayload
from shared.llm_adapter import LLMProvider, LLMResponse
from shared.llm_adapter.models import LLMRequest
from shared.llm_adapter.openai_tool_schemas import tools_openai_from_registry
from shared.observability.metrics import (
    agent_tool_calls_total,
    agent_tool_loop_llm_rounds,
    agent_tool_loop_outcomes_total,
    llm_tokens,
)
from shared.tools import ToolRegistry, execute_tool
from shared.tools.models import ToolExecutionResult

logger = logging.getLogger(__name__)

SERVICE_NAME = "replanner_service"

ADMADC_TOOL_LOOP_MARKER = "[ADMADC_TOOL_LOOP]"

_REPLANNER_TOOL_NAMES = ("semantic_outcome_memory", "failure_patterns")


REPLANNER_PROMPT = """You are an autonomous replanning agent in a multi-agent dev pipeline.

Your goal:
{agent_goal}

You are analysing the outcome of a previous plan with id {plan_id}.

You receive:
- The final QA and/or Security result.
- A compact semantic memory window with past decisions and conclusions.
- Aggregated historical failure patterns by module (qa.failed / security.blocked hot spots).

MEMORY CONTEXT:
{memory_context}

CURRENT OUTCOME SUMMARY:
{outcome_summary}
{security_instruction}

Your job:
1. Decide whether the existing plan needs revision.
2. If yes, propose the SMALLEST set of concrete, high-leverage adjustments.
3. Prioritise changes in modules/directories that appear as hot spots in the failure patterns.
4. Prefer adding or hardening tests, safeguards and small refactors in those modules over broad, cross-cutting rewrites.
5. Focus on structural changes to the plan and task graph (what to re-run, what new tasks/tests to add), not line-by-line code fixes.

Respond EXACTLY in this format:
REASON: <1-3 sentences explaining why a revision is or is not needed>
SEVERITY: low|medium|high|critical
REVISION_NEEDED: yes|no
SUGGESTIONS:
- <suggestion 1 (if any)>
- <suggestion 2 (if any)>
"""
SECURITY_BLOCKED_INSTRUCTION = """
IMPORTANT (Security denied): The code was BLOCKED by the security scan. Your SUGGESTIONS must directly address EACH violation and the security reasoning above, so that the next implementation satisfies the security rules and the next run succeeds. Each suggestion should state what to remove, change or add to comply with security.
"""


REPLANNER_TOOL_LOOP_SYSTEM = """You are a replanning critic in a multi-agent dev pipeline.

Use semantic_outcome_memory (with the plan id) and failure_patterns when you need richer memory than the summary below.
Prefer minimal, targeted tool calls.

When finished, respond with NO tool calls, exactly in this format:
REASON: <1-3 sentences>
SEVERITY: low|medium|high|critical
REVISION_NEEDED: yes|no
SUGGESTIONS:
- <suggestion or "none">
"""


@dataclass
class ReplanDecision:
    revision_needed: bool
    severity: str
    reason: str
    suggestions: list[str]


async def analyse_outcome(
    llm: LLMProvider,
    agent_goal: str,
    plan_id: str,
    outcome: QAResultPayload | SecurityResultPayload,
    memory_context: str,
    outcome_type: str = "qa_failed",
) -> tuple[ReplanDecision, int, int]:
    """Returns (decision, prompt_tokens, completion_tokens)."""
    outcome_summary = _summarise_outcome(outcome)
    security_instruction = (
        SECURITY_BLOCKED_INSTRUCTION if outcome_type == "security_blocked" else ""
    )
    prompt = REPLANNER_PROMPT.format(
        agent_goal=agent_goal,
        plan_id=plan_id,
        memory_context=memory_context.strip() or "None.",
        outcome_summary=outcome_summary,
        security_instruction=security_instruction,
    )

    response: LLMResponse = await llm.generate_text(prompt)

    pt = response.prompt_tokens or 0
    ct = response.completion_tokens or 0
    if pt or ct:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)

    decision = _parse_replanner_response(response.content)

    logger.info(
        "Replanner analysed outcome for plan %s: revision_needed=%s, severity=%s, reason=%s",
        plan_id[:8],
        decision.revision_needed,
        decision.severity,
        decision.reason[:120],
    )
    return decision, pt, ct


def _tool_payload(result: ToolExecutionResult) -> str:
    if result.success:
        return json.dumps(result.output, default=str)
    return json.dumps({"success": False, "error": result.error or "unknown"})


async def analyse_outcome_with_tool_loop(
    llm: LLMProvider,
    registry: ToolRegistry,
    *,
    agent_goal: str,
    plan_id: str,
    outcome: QAResultPayload | SecurityResultPayload,
    memory_context: str,
    outcome_type: str = "qa_failed",
    max_steps: int = 8,
) -> tuple[ReplanDecision, int, int]:
    """Multi-turn replanner with memory tools before structured verdict."""
    tools = tools_openai_from_registry(registry, _REPLANNER_TOOL_NAMES)
    if not tools:
        logger.warning("Replanner tool loop: no tools; single-shot analyse_outcome")
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="fallback_single_shot"
        ).inc()
        return await analyse_outcome(
            llm,
            agent_goal,
            plan_id,
            outcome,
            memory_context,
            outcome_type,
        )

    outcome_summary = _summarise_outcome(outcome)
    security_instruction = (
        SECURITY_BLOCKED_INSTRUCTION if outcome_type == "security_blocked" else ""
    )
    base_user = REPLANNER_PROMPT.format(
        agent_goal=agent_goal,
        plan_id=plan_id,
        memory_context=memory_context.strip() or "None.",
        outcome_summary=outcome_summary,
        security_instruction=security_instruction,
    )
    user_content = f"{ADMADC_TOOL_LOOP_MARKER}\n\n{base_user}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": REPLANNER_TOOL_LOOP_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    total_pt = 0
    total_ct = 0
    llm_rounds = 0

    for _step in range(max(1, max_steps)):
        llm_rounds += 1
        req = LLMRequest(
            prompt="",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        resp = await llm.generate(req)
        pt = resp.prompt_tokens or 0
        ct = resp.completion_tokens or 0
        total_pt += pt
        total_ct += ct
        if pt or ct:
            llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
            llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)

        if resp.tool_calls:
            asst: dict[str, Any] = {
                "role": "assistant",
                "tool_calls": resp.tool_calls,
            }
            asst["content"] = (resp.content or "").strip() or None
            messages.append(asst)
            for tc in resp.tool_calls:
                fn = tc.get("function") or {}
                name = str(fn.get("name") or "")
                raw_args = fn.get("arguments")
                if isinstance(raw_args, str):
                    try:
                        args_dict: Any = json.loads(raw_args.strip() or "{}")
                    except json.JSONDecodeError:
                        args_dict = None
                elif isinstance(raw_args, dict):
                    args_dict = raw_args
                else:
                    args_dict = {}
                if not isinstance(args_dict, dict):
                    exec_result = ToolExecutionResult(
                        success=False,
                        error="Tool arguments must be a JSON object",
                    )
                else:
                    exec_result = await execute_tool(registry, name, args_dict)
                agent_tool_calls_total.labels(
                    service=SERVICE_NAME,
                    tool_name=name or "unknown",
                    result="success" if exec_result.success else "failure",
                ).inc()
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tc.get("id") or ""),
                        "content": _tool_payload(exec_result),
                    }
                )
            continue

        decision = _parse_replanner_response(resp.content or "")
        agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="completed"
        ).inc()
        logger.info(
            "Replanner tool-loop plan %s: revision_needed=%s, severity=%s",
            plan_id[:8],
            decision.revision_needed,
            decision.severity,
        )
        return decision, total_pt, total_ct

    agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
    agent_tool_loop_outcomes_total.labels(
        service=SERVICE_NAME, outcome="exhausted"
    ).inc()
    decision = _parse_replanner_response("")
    logger.warning("Replanner tool loop exhausted max_steps=%s plan=%s", max_steps, plan_id[:8])
    return decision, total_pt, total_ct


def _summarise_outcome(outcome: QAResultPayload | SecurityResultPayload) -> str:
    if isinstance(outcome, QAResultPayload):
        status = "PASSED" if outcome.passed else "FAILED"
        issues = ", ".join(outcome.issues) if outcome.issues else "none"
        module = getattr(outcome, "module", "") or "unknown_module"
        severity = getattr(outcome, "severity_hint", "") or "medium"
        return (
            f"QA RESULT ({status}) for task {outcome.task_id} in plan {outcome.plan_id}. "
            f"Module: {module}. Severity hint: {severity}. "
            f"Issues: {issues}. Reasoning: {outcome.reasoning}"
        )

    status = "APPROVED" if outcome.approved else "BLOCKED"
    severity = getattr(outcome, "severity_hint", "") or "medium"
    lines = [
        f"SECURITY RESULT: {status} for plan {outcome.plan_id}, branch {outcome.branch_name}.",
        f"Severity hint: {severity}.",
        f"Files scanned: {outcome.files_scanned}.",
    ]
    if outcome.violations:
        lines.append("Violations (code MUST be changed to fix these):")
        for i, v in enumerate(outcome.violations, 1):
            lines.append(f"  {i}. {v}")
    else:
        lines.append("Violations: none listed.")
    if (outcome.reasoning or "").strip():
        lines.append(f"Security reasoning: {outcome.reasoning}")
    return "\n".join(lines)


def _parse_replanner_response(raw: str) -> ReplanDecision:
    revision_needed = False
    severity = "medium"
    reason = ""
    suggestions: list[str] = []

    lines = raw.strip().splitlines()
    in_suggestions = False

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("REASON:"):
            reason = stripped[len("REASON:") :].strip()
            in_suggestions = False
        elif upper.startswith("SEVERITY:"):
            severity = stripped[len("SEVERITY:") :].strip().lower() or "medium"
            in_suggestions = False
        elif upper.startswith("REVISION_NEEDED:"):
            flag = stripped[len("REVISION_NEEDED:") :].strip().lower()
            revision_needed = flag == "yes"
            in_suggestions = False
        elif upper.startswith("SUGGESTIONS:"):
            in_suggestions = True
        elif in_suggestions and stripped.startswith("- "):
            suggestion = stripped.lstrip("- ").strip()
            if suggestion and suggestion.lower() not in ("none", "n/a"):
                suggestions.append(suggestion)

    return ReplanDecision(
        revision_needed=revision_needed,
        severity=severity,
        reason=reason,
        suggestions=suggestions,
    )

