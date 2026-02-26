from __future__ import annotations

import logging
from dataclasses import dataclass

from shared.contracts.events import QAResultPayload, SecurityResultPayload
from shared.llm_adapter import LLMProvider, LLMResponse
from shared.observability.metrics import llm_tokens

logger = logging.getLogger(__name__)

SERVICE_NAME = "replanner_service"


REPLANNER_PROMPT = """You are an autonomous replanning agent in a multi-agent dev pipeline.

Your goal:
{agent_goal}

You are analysing the outcome of a previous plan with id {plan_id}.

You receive:
- The final QA and/or Security result.
- A compact semantic memory window with past decisions and conclusions.

MEMORY CONTEXT:
{memory_context}

CURRENT OUTCOME SUMMARY:
{outcome_summary}
{security_instruction}

Your job:
1. Decide whether the existing plan needs revision.
2. If yes, propose the smallest set of concrete, high-leverage adjustments.
3. Focus on structural changes to the plan, not line-by-line code fixes.

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


def _summarise_outcome(outcome: QAResultPayload | SecurityResultPayload) -> str:
    if isinstance(outcome, QAResultPayload):
        status = "PASSED" if outcome.passed else "FAILED"
        issues = ", ".join(outcome.issues) if outcome.issues else "none"
        return (
            f"QA RESULT ({status}) for task {outcome.task_id} in plan {outcome.plan_id}. "
            f"Issues: {issues}. Reasoning: {outcome.reasoning}"
        )

    status = "APPROVED" if outcome.approved else "BLOCKED"
    lines = [
        f"SECURITY RESULT: {status} for plan {outcome.plan_id}, branch {outcome.branch_name}.",
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

