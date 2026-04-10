"""
QA review logic: static pattern analysis + LLM-based code review.

Each QA agent:
1. Reads the developer's reasoning and explicitly responds to it.
2. Performs static and semantic review of the code.
3. Returns REASONING that references the developer's decisions.

This creates a visible inter-agent dialogue: dev explains choices, QA responds.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from services.qa_service.config import DANGEROUS_PATTERNS
from services.qa_service.prompts import (
    QA_REVIEW_PROMPT,
    QA_REVIEW_PROMPT_NO_PRIOR,
    QA_TOOL_LOOP_SYSTEM,
)
from shared.llm_adapter import LLMProvider
from shared.llm_adapter.models import LLMRequest
from shared.llm_adapter.openai_tool_schemas import tools_openai_from_registry
from shared.llm_adapter.parse_retry import generate_text_with_parse_retry
from shared.llm_adapter.tool_loop_budget import (
    loop_tokens_exceeds_budget,
    plan_tool_loop_try_add_tokens,
    tool_calls_exceeds_budget,
    tool_loop_budget_from_env,
)
from shared.observability.metrics import (
    agent_tool_calls_total,
    agent_tool_loop_llm_rounds,
    agent_tool_loop_outcomes_total,
    llm_tokens,
)
from shared.policies import Rule, rules_for_language
from shared.prompt_locale import (
    natural_language_rules_for_locale,
    qa_heuristic_fs_warning,
    qa_heuristic_network_warning,
    qa_heuristic_secrets_warning,
    qa_parse_repair_no_tools_suffix,
    qa_static_pattern_security_title,
    qa_synthetic_budget_fail,
)
from shared.tools import ToolRegistry, execute_tool
from shared.tools.models import ToolExecutionResult

logger = logging.getLogger(__name__)

ADMADC_TOOL_LOOP_QA = "[ADMADC_TOOL_LOOP_QA]"
_QA_READ_TOOLS = ("read_file", "search_in_repo")
_QA_PARSE_REPAIR = (
    "You must include the line VERDICT: PASS or VERDICT: FAIL and all other sections in the required format."
)

@dataclass
class ReviewResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    reasoning: str = ""
    structured_feedback: dict | None = None
    required_changes: list[str] = field(default_factory=list)
    optional_improvements: list[str] = field(default_factory=list)


SERVICE_NAME = "qa_service"


async def review_code(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
    user_locale: str = "en",
) -> tuple[ReviewResult, int, int]:
    """
    Run static checks then LLM review. Returns (result, prompt_tokens, completion_tokens).
    """
    static_issues = _static_check(code, user_locale=user_locale)
    if static_issues:
        reasoning = (
            f"Static analysis detected {len(static_issues)} dangerous pattern(s) "
            "before LLM review. Immediate rejection applied regardless of "
            "developer's stated rationale."
        )
        logger.warning("Static check FAILED for %s: %s", file_path, static_issues)
        return (
            ReviewResult(
                passed=False,
                issues=static_issues,
                reasoning=reasoning,
                structured_feedback={
                    "functionality": [],
                    "style": [],
                    "security": [
                        {
                            "severity": "critical",
                            "title": qa_static_pattern_security_title(user_locale),
                            "details": "; ".join(static_issues),
                        }
                    ],
                },
            ),
            0,
            0,
        )

    return await _llm_review(
        llm,
        code,
        file_path,
        language,
        task_description,
        dev_reasoning,
        short_term_memory=short_term_memory,
        static_analysis_report=static_analysis_report,
        user_locale=user_locale,
    )


async def review_code_with_tool_loop(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
    *,
    registry: ToolRegistry,
    max_steps: int = 8,
    plan_id: str | None = None,
    redis_url: str | None = None,
    user_locale: str = "en",
) -> tuple[ReviewResult, int, int]:
    static_issues = _static_check(code, user_locale=user_locale)
    if static_issues:
        reasoning = (
            f"Static analysis detected {len(static_issues)} dangerous pattern(s) "
            "before LLM review. Immediate rejection applied regardless of "
            "developer's stated rationale."
        )
        logger.warning("Static check FAILED for %s: %s", file_path, static_issues)
        return (
            ReviewResult(
                passed=False,
                issues=static_issues,
                reasoning=reasoning,
                structured_feedback={
                    "functionality": [],
                    "style": [],
                    "security": [
                        {
                            "severity": "critical",
                            "title": qa_static_pattern_security_title(user_locale),
                            "details": "; ".join(static_issues),
                        }
                    ],
                },
            ),
            0,
            0,
        )
    return await _llm_review_with_tool_loop(
        llm,
        code,
        file_path,
        language,
        task_description,
        dev_reasoning,
        short_term_memory=short_term_memory,
        static_analysis_report=static_analysis_report,
        registry=registry,
        max_steps=max_steps,
        plan_id=plan_id,
        redis_url=redis_url,
        user_locale=user_locale,
    )


def _static_check(code: str, *, user_locale: str = "en") -> list[str]:
    """Detect known dangerous patterns. O(n*m) but code is small."""
    issues: list[str] = []
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            issues.append(f"Dangerous pattern detected: `{pattern}`")

    suspicious_snippets = _heuristic_suspicious_snippets(code, user_locale=user_locale)
    issues.extend(suspicious_snippets)
    return issues


def _heuristic_suspicious_snippets(code: str, *, user_locale: str = "en") -> list[str]:
    """
    Lightweight heuristics for suspicious code (network, filesystem, secrets).
    Does not fail the review alone; attached as high-priority security context.
    """
    lowered = code.lower()
    findings: list[str] = []

    network_markers = ("requests.", "httpx.", "fetch(", "axios.", "urlopen(")
    if any(m in lowered for m in network_markers):
        findings.append(qa_heuristic_network_warning(user_locale))

    fs_markers = ("open(", "os.remove(", "os.unlink(", "shutil.", "fs.", "pathlib.")
    if any(m in lowered for m in fs_markers):
        findings.append(qa_heuristic_fs_warning(user_locale))

    secrets_markers = ("os.environ", "process.env", "secret", "api_key", "password")
    if any(m in lowered for m in secrets_markers):
        findings.append(qa_heuristic_secrets_warning(user_locale))

    return findings


def _build_llm_review_prompt(
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
    user_locale: str = "en",
) -> str:
    qa_rules_block = _build_qa_rules_block(language)
    response_language_rules = natural_language_rules_for_locale(user_locale)

    if dev_reasoning.strip():
        return QA_REVIEW_PROMPT.format(
            language=language,
            file_path=file_path,
            code=code,
            description=task_description,
            dev_reasoning=dev_reasoning,
            short_term_memory=short_term_memory.strip() or "None.",
            static_analysis_report=static_analysis_report.strip()
            or "No static analysis issues or warnings were reported by tools.",
            qa_rules_block=qa_rules_block,
            response_language_rules=response_language_rules,
        )
    return QA_REVIEW_PROMPT_NO_PRIOR.format(
        language=language,
        file_path=file_path,
        code=code,
        description=task_description,
        static_analysis_report=static_analysis_report.strip()
        or "No static analysis issues or warnings were reported by tools.",
        qa_rules_block=qa_rules_block,
        response_language_rules=response_language_rules,
    )


async def _llm_review(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
    user_locale: str = "en",
) -> tuple[ReviewResult, int, int]:
    prompt = _build_llm_review_prompt(
        code,
        file_path,
        language,
        task_description,
        dev_reasoning,
        short_term_memory,
        static_analysis_report,
        user_locale=user_locale,
    )

    def _parse(raw: str) -> tuple[ReviewResult | None, bool]:
        r = _parse_review_response(raw or "")
        ok = "VERDICT:" in (raw or "").upper()
        return r, ok

    result, pt, ct = await generate_text_with_parse_retry(
        llm,
        initial_prompt=prompt,
        repair_instruction=_QA_PARSE_REPAIR,
        parse=_parse,
        service_name=SERVICE_NAME,
        max_attempts=2,
    )
    return result, pt, ct


def _qa_tool_payload(result: ToolExecutionResult) -> str:
    if result.success:
        return json.dumps(result.output, default=str)
    return json.dumps({"success": False, "error": result.error or "unknown"})


async def _llm_review_with_tool_loop(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
    *,
    registry: ToolRegistry,
    max_steps: int = 8,
    plan_id: str | None = None,
    redis_url: str | None = None,
    user_locale: str = "en",
) -> tuple[ReviewResult, int, int]:
    tools = tools_openai_from_registry(registry, _QA_READ_TOOLS)
    if not tools:
        logger.warning("QA tool loop: no tools in registry; single-shot review")
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="fallback_single_shot"
        ).inc()
        return await _llm_review(
            llm,
            code,
            file_path,
            language,
            task_description,
            dev_reasoning,
            short_term_memory,
            static_analysis_report,
            user_locale=user_locale,
        )

    base_prompt = _build_llm_review_prompt(
        code,
        file_path,
        language,
        task_description,
        dev_reasoning,
        short_term_memory,
        static_analysis_report,
        user_locale=user_locale,
    )
    user_content = f"{ADMADC_TOOL_LOOP_QA}\n\n{base_prompt}"
    system_rules = natural_language_rules_for_locale(user_locale)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": QA_TOOL_LOOP_SYSTEM.format(
                response_language_rules=system_rules,
            ),
        },
        {"role": "user", "content": user_content},
    ]

    total_pt = 0
    total_ct = 0
    llm_rounds = 0
    tools_executed = 0
    budget = tool_loop_budget_from_env(max_steps)

    for _step in range(max(1, budget.max_steps)):
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
        if loop_tokens_exceeds_budget(total_pt, total_ct, budget.max_tokens_loop):
            agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
            agent_tool_loop_outcomes_total.labels(
                service=SERVICE_NAME, outcome="budget_exceeded"
            ).inc()
            r = _parse_review_response(
                qa_synthetic_budget_fail(user_locale, "loop_tokens")
            )
            return r, total_pt, total_ct
        if budget.max_tokens_plan > 0:
            allowed = await plan_tool_loop_try_add_tokens(
                redis_url, plan_id, pt + ct, budget.max_tokens_plan
            )
            if not allowed:
                agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
                agent_tool_loop_outcomes_total.labels(
                    service=SERVICE_NAME, outcome="budget_exceeded"
                ).inc()
                r = _parse_review_response(
                    qa_synthetic_budget_fail(user_locale, "plan_tokens")
                )
                return r, total_pt, total_ct

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
                tools_executed += 1
                if tool_calls_exceeds_budget(tools_executed, budget.max_tool_calls):
                    agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
                    agent_tool_loop_outcomes_total.labels(
                        service=SERVICE_NAME, outcome="budget_exceeded"
                    ).inc()
                    r = _parse_review_response(
                        qa_synthetic_budget_fail(user_locale, "tool_calls")
                    )
                    return r, total_pt, total_ct
                agent_tool_calls_total.labels(
                    service=SERVICE_NAME,
                    tool_name=name or "unknown",
                    result="success" if exec_result.success else "failure",
                ).inc()
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tc.get("id") or ""),
                        "content": _qa_tool_payload(exec_result),
                    }
                )
            continue

        raw = resp.content or ""
        result = _parse_review_response(raw)
        if "VERDICT:" not in raw.upper():
            messages.append(
                {
                    "role": "user",
                    "content": _QA_PARSE_REPAIR + qa_parse_repair_no_tools_suffix(user_locale),
                }
            )
            continue
        agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="completed"
        ).inc()
        return result, total_pt, total_ct

    agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
    agent_tool_loop_outcomes_total.labels(
        service=SERVICE_NAME, outcome="exhausted"
    ).inc()
    r = _parse_review_response(qa_synthetic_budget_fail(user_locale, "exhausted"))
    return r, total_pt, total_ct


def _build_qa_rules_block(language: str) -> str:
    """
    Build the textual QA rules block for the given language, prioritising
    high-severity rules (blocker/error) to keep the prompt focused.
    """
    qa_rules: list[Rule] = rules_for_language(language, category="qa")
    if not qa_rules:
        return "No specific rules."

    important = [r for r in qa_rules if r.severity.value in ("blocker", "error")]
    source = important or qa_rules
    lines = [f"- [{r.id}] ({r.severity.value}): {r.description}" for r in source]
    return "\n".join(lines)


def _parse_review_response(content: str) -> ReviewResult:
    """Parse the structured LLM response into a ReviewResult with reasoning and sections."""
    lines = content.strip().splitlines()
    passed = True
    issues: list[str] = []
    required_changes: list[str] = []
    optional_improvements: list[str] = []
    reasoning = ""
    in_issues = False
    in_required = False
    in_optional = False
    current_section: Literal["functionality", "style", "security", "other"] = "other"
    structured: dict[str, list[dict]] = {
        "functionality": [],
        "style": [],
        "security": [],
    }

    def _reset_sections() -> None:
        nonlocal in_issues, in_required, in_optional
        in_issues = in_required = in_optional = False

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("REASONING:"):
            reasoning = stripped[len("REASONING:"):].strip()
            _reset_sections()
        elif upper.startswith("VERDICT:"):
            verdict = upper.replace("VERDICT:", "").strip()
            passed = verdict == "PASS"
            _reset_sections()
        elif upper.startswith("ISSUES:"):
            in_issues = True
            in_required = in_optional = False
            inline = stripped[len("ISSUES:"):].strip()
            if inline.lower() not in ("none", ""):
                issues.append(inline)
        elif upper.startswith("REQUIRED_CHANGES:"):
            _reset_sections()
            in_required = True
            inline = stripped[len("REQUIRED_CHANGES:"):].strip()
            if inline.lower() not in ("none", ""):
                required_changes.append(inline)
        elif upper.startswith("OPTIONAL_IMPROVEMENTS:"):
            in_issues = in_required = False
            in_optional = True
            inline = stripped[len("OPTIONAL_IMPROVEMENTS:"):].strip()
            if inline.lower() not in ("none", ""):
                optional_improvements.append(inline)
        elif in_required and stripped:
            num = re.match(r"^(\d+)[.)]\s*(.+)$", stripped)
            if num:
                required_changes.append(num.group(2).strip())
            elif stripped.startswith("- "):
                required_changes.append(stripped[2:].strip())
        elif in_optional and stripped.startswith("- "):
            opt = stripped[2:].strip()
            if opt.lower() not in ("none", ""):
                optional_improvements.append(opt)
        elif in_issues and stripped.startswith("- "):
            issue = stripped.lstrip("- ").strip()
            if issue.lower() not in ("none", ""):
                issues.append(issue)
                sev = "info"
                category = "other"
                if issue.startswith("[") and "]" in issue:
                    header, _, rest = issue[1:].partition("]")
                    parts = header.split("|", 1)
                    if parts:
                        sev = parts[0].strip().lower() or "info"
                    if len(parts) > 1:
                        category = parts[1].strip().lower() or "other"
                    title = rest.strip() or issue
                else:
                    title = issue

                if "seguridad" in category or "security" in category:
                    current_section = "security"
                elif "funcional" in category or "functional" in category:
                    current_section = "functionality"
                elif "estilo" in category or "style" in category:
                    current_section = "style"
                else:
                    current_section = "other"

                target_key = (
                    current_section
                    if current_section in {"functionality", "style", "security"}
                    else "security" if "sec" in category else "functionality"
                )
                structured.setdefault(target_key, []).append(
                    {
                        "severity": sev,
                        "category": category,
                        "title": title,
                    }
                )

    if not passed and not issues:
        issues.append("LLM reviewer returned FAIL without specific issues")

    logger.info(
        "LLM review result: %s, issues=%d. Reasoning: %s",
        "PASS" if passed else "FAIL",
        len(issues),
        reasoning[:80],
    )
    return ReviewResult(
        passed=passed,
        issues=issues,
        reasoning=reasoning,
        structured_feedback=structured,
        required_changes=required_changes,
        optional_improvements=optional_improvements,
    )
