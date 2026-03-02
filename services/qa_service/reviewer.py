"""
QA review logic: static pattern analysis + LLM-based code review.

Each QA agent:
1. Reads the developer's reasoning and explicitly responds to it.
2. Performs static and semantic review of the code.
3. Returns REASONING that references the developer's decisions.

This creates a visible inter-agent dialogue: dev explains choices, QA responds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared.llm_adapter import LLMProvider, LLMResponse
from shared.observability.metrics import llm_tokens
from shared.policies import rules_for_language, Rule
from services.qa_service.config import DANGEROUS_PATTERNS
from services.qa_service.prompts import QA_REVIEW_PROMPT, QA_REVIEW_PROMPT_NO_PRIOR

logger = logging.getLogger(__name__)

@dataclass
class ReviewResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    reasoning: str = ""


SERVICE_NAME = "qa_service"


async def review_code(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
) -> tuple[ReviewResult, int, int]:
    """
    Run static checks then LLM review. Returns (result, prompt_tokens, completion_tokens).
    """
    static_issues = _static_check(code)
    if static_issues:
        reasoning = (
            f"Static analysis detected {len(static_issues)} dangerous pattern(s) "
            "before LLM review. Immediate rejection applied regardless of "
            "developer's stated rationale."
        )
        logger.warning("Static check FAILED for %s: %s", file_path, static_issues)
        return ReviewResult(passed=False, issues=static_issues, reasoning=reasoning), 0, 0

    return await _llm_review(
        llm, code, file_path, language, task_description, dev_reasoning,
        short_term_memory=short_term_memory,
    )


def _static_check(code: str) -> list[str]:
    """Detect known dangerous patterns. O(n*m) but code is small."""
    issues = []
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            issues.append(f"Dangerous pattern detected: `{pattern}`")
    return issues


async def _llm_review(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
) -> tuple[ReviewResult, int, int]:
    qa_rules: list[Rule] = rules_for_language(language, category="qa")
    important_rules = [r for r in qa_rules if r.severity.value in ("blocker", "error")]
    rules_source = important_rules or qa_rules
    rules_lines = [
        f"- [{r.id}] ({r.severity.value}): {r.description}" for r in rules_source
    ]
    qa_rules_block = "\n".join(rules_lines) if rules_lines else "No specific rules."

    if dev_reasoning.strip():
        prompt = QA_REVIEW_PROMPT.format(
            language=language,
            file_path=file_path,
            code=code,
            description=task_description,
            dev_reasoning=dev_reasoning,
            short_term_memory=short_term_memory.strip() or "None.",
            qa_rules_block=qa_rules_block,
        )
    else:
        prompt = QA_REVIEW_PROMPT_NO_PRIOR.format(
            language=language,
            file_path=file_path,
            code=code,
            description=task_description,
            qa_rules_block=qa_rules_block,
        )

    response: LLMResponse = await llm.generate_text(prompt)

    pt = response.prompt_tokens or 0
    ct = response.completion_tokens or 0
    if pt or ct:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)

    result = _parse_review_response(response.content)
    return result, pt, ct


def _parse_review_response(content: str) -> ReviewResult:
    """Parse the structured LLM response into a ReviewResult with reasoning."""
    lines = content.strip().splitlines()
    passed = True
    issues: list[str] = []
    reasoning = ""
    in_issues = False

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("REASONING:"):
            reasoning = stripped[len("REASONING:"):].strip()
            in_issues = False
        elif upper.startswith("VERDICT:"):
            verdict = upper.replace("VERDICT:", "").strip()
            passed = verdict == "PASS"
            in_issues = False
        elif upper.startswith("ISSUES:"):
            in_issues = True
            inline = stripped[len("ISSUES:"):].strip()
            if inline.lower() not in ("none", ""):
                issues.append(inline)
        elif in_issues and stripped.startswith("- "):
            issue = stripped.lstrip("- ").strip()
            if issue.lower() not in ("none", ""):
                issues.append(issue)

    if not passed and not issues:
        issues.append("LLM reviewer returned FAIL without specific issues")

    logger.info(
        "LLM review result: %s, issues=%d. Reasoning: %s",
        "PASS" if passed else "FAIL", len(issues), reasoning[:80],
    )
    return ReviewResult(passed=passed, issues=issues, reasoning=reasoning)
