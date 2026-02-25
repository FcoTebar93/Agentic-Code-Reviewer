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
from services.qa_service.config import DANGEROUS_PATTERNS

logger = logging.getLogger(__name__)

QA_REVIEW_PROMPT = """You are a strict senior code reviewer performing a quality assurance check.

The developer agent that wrote this code provided the following reasoning:
---
DEVELOPER'S REASONING:
{dev_reasoning}
---

You also have access to a short memory window of recent events and decisions
for this plan (previous QA results, security decisions, pipeline conclusions, etc.).
Use this context only if it is relevant to your review; otherwise you may ignore it.

SHORT-TERM MEMORY:
{short_term_memory}

Now review the following {language} code intended for file `{file_path}`:

```{language}
{code}
```

The original task description was:
{description}

Your job:
1. Explicitly respond to the developer's reasoning above — do you agree with their approach? Are there concerns?
2. Check that the code correctly implements the described task.
3. Identify any logic errors, missing error handling, or undefined variables.
4. Check for security anti-patterns (hardcoded secrets, dangerous functions, SQL injection, etc.).
5. Check code quality (readability, unnecessary complexity).

Format your response EXACTLY as:
REASONING: <2-4 sentences that (a) respond to the developer's reasoning, (b) explain your review decision>
VERDICT: PASS or FAIL
ISSUES:
- <issue 1 if any>
- <issue 2 if any>
(or "ISSUES: none" if PASS)
"""

QA_REVIEW_PROMPT_NO_PRIOR = """You are a strict senior code reviewer performing a quality assurance check.

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

Format your response EXACTLY as:
REASONING: <your review reasoning in 2-3 sentences>
VERDICT: PASS or FAIL
ISSUES:
- <issue 1 if any>
(or "ISSUES: none" if PASS)
"""


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
    if dev_reasoning.strip():
        prompt = QA_REVIEW_PROMPT.format(
            language=language,
            file_path=file_path,
            code=code,
            description=task_description,
            dev_reasoning=dev_reasoning,
            short_term_memory=short_term_memory.strip() or "None.",
        )
    else:
        prompt = QA_REVIEW_PROMPT_NO_PRIOR.format(
            language=language,
            file_path=file_path,
            code=code,
            description=task_description,
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
