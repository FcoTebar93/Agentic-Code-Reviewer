"""
QA review logic: static pattern analysis + LLM-based code review.

Design: two-pass approach.
Pass 1 (static): immediate rejection for known dangerous patterns.
         This is deterministic, zero-LLM-cost, and catches obvious issues.
Pass 2 (LLM): semantic review to catch logic errors, missing error handling,
         and code quality issues that static analysis cannot detect.
Both passes must succeed for the code to be marked as QA_PASSED.

The LLM is asked to provide a REASONING section explaining the review
decision, which is propagated to the event payload for frontend visibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared.llm_adapter import LLMProvider
from services.qa_service.config import DANGEROUS_PATTERNS

logger = logging.getLogger(__name__)

QA_REVIEW_PROMPT = """You are a strict senior code reviewer performing a quality assurance check.

Analyse the following {language} code intended for file `{file_path}`:

```{language}
{code}
```

The original task description was:
{description}

Your job:
1. Check that the code implements the described task correctly.
2. Identify any logic errors, missing error handling, or undefined variables.
3. Check for security anti-patterns (hardcoded secrets, dangerous functions, SQL injection, etc.).
4. Check code quality (readability, unnecessary complexity).

First provide your reasoning (what you checked and why you made your decision).
Then give your structured verdict.

Format your response EXACTLY as:
REASONING: <your review reasoning in 2-3 sentences>
VERDICT: PASS or FAIL
ISSUES:
- <issue 1 if any>
- <issue 2 if any>
(or "ISSUES: none" if PASS)
"""


@dataclass
class ReviewResult:
    passed: bool
    issues: list[str]
    reasoning: str = ""


async def review_code(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
) -> ReviewResult:
    """
    Run static checks then LLM review.

    Returns ReviewResult(passed=True, ...) on full approval.
    Returns ReviewResult(passed=False, ...) on any failure.
    """
    static_issues = _static_check(code)
    if static_issues:
        reasoning = (
            f"Static analysis detected {len(static_issues)} dangerous pattern(s) "
            "before LLM review. Immediate rejection applied."
        )
        logger.warning("Static check FAILED for %s: %s", file_path, static_issues)
        return ReviewResult(passed=False, issues=static_issues, reasoning=reasoning)

    llm_result = await _llm_review(llm, code, file_path, language, task_description)
    return llm_result


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
) -> ReviewResult:
    prompt = QA_REVIEW_PROMPT.format(
        language=language,
        file_path=file_path,
        code=code,
        description=task_description,
    )
    response = await llm.generate_text(prompt)
    return _parse_review_response(response.content)


def _parse_review_response(content: str) -> ReviewResult:
    """Parse the structured LLM response into a ReviewResult with reasoning."""
    lines = content.strip().splitlines()
    passed = True
    issues: list[str] = []
    reasoning = ""

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("REASONING:"):
            reasoning = stripped[len("REASONING:"):].strip()
        elif upper.startswith("VERDICT:"):
            verdict = upper.replace("VERDICT:", "").strip()
            passed = verdict == "PASS"
        elif stripped.startswith("- ") and not passed:
            issue = stripped.lstrip("- ").strip()
            if issue.lower() not in ("none", ""):
                issues.append(issue)

    if not passed and not issues:
        issues.append("LLM reviewer returned FAIL without specific issues")

    logger.info(
        "LLM review result: %s, issues=%d. Reasoning: %s",
        "PASS" if passed else "FAIL", len(issues), reasoning[:60],
    )
    return ReviewResult(passed=passed, issues=issues, reasoning=reasoning)
