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
from typing import Literal

from shared.llm_adapter import LLMProvider, LLMResponse
from shared.observability.metrics import llm_tokens
from shared.policies import rules_for_language, Rule
from shared.tools import ToolRegistry, execute_tool
from shared.tools.models import ToolExecutionResult
from services.qa_service.config import DANGEROUS_PATTERNS
from services.qa_service.prompts import QA_REVIEW_PROMPT, QA_REVIEW_PROMPT_NO_PRIOR

logger = logging.getLogger(__name__)

ADMADC_TOOL_LOOP_QA = "[ADMADC_TOOL_LOOP_QA]"
_QA_READ_TOOLS = ("read_file", "search_in_repo")
_QA_PARSE_REPAIR = (
    "Incluye obligatoriamente la línea VERDICT: PASS o VERDICT: FAIL y el resto de secciones del formato."
)

@dataclass
class ReviewResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    reasoning: str = ""
    structured_feedback: dict | None = None


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
) -> tuple[ReviewResult, int, int]:
    static_issues = _static_check(code)
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
                            "title": "Patrones estáticos peligrosos detectados antes del QA LLM",
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


async def _llm_review(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
) -> str:
    qa_rules_block = _build_qa_rules_block(language)
    response_language_rules = natural_language_rules_for_locale(user_locale)

    if dev_reasoning.strip():
        prompt = QA_REVIEW_PROMPT.format(
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
) -> tuple[ReviewResult, int, int]:
    prompt = _build_llm_review_prompt(
        code,
        file_path,
        language,
        task_description,
        dev_reasoning,
        short_term_memory,
        static_analysis_report,
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
) -> tuple[ReviewResult, int, int]:
    tools = tools_openai_from_registry(registry, _QA_READ_TOOLS)
    if not tools:
        logger.warning("QA tool loop: sin herramientas en registry; revisión single-shot")
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
        )

    base_prompt = _build_llm_review_prompt(
        code,
        file_path,
        language,
        task_description,
        dev_reasoning,
        short_term_memory,
        static_analysis_report,
    )
    user_content = f"{ADMADC_TOOL_LOOP_QA}\n\n{base_prompt}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": QA_TOOL_LOOP_SYSTEM},
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
                "REASONING: QA tool loop detenido por presupuesto de tokens del bucle.\n"
                "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
                "  DETAILS: Se superó ADMADC_TOOL_LOOP_MAX_TOKENS_PER_LOOP.\n"
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
                    "REASONING: QA tool loop detenido por presupuesto de tokens acumulados del plan.\n"
                    "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
                    "  DETAILS: Se superó ADMADC_PLAN_TOOL_LOOP_MAX_TOKENS.\n"
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
                        "REASONING: QA tool loop detenido por límite de llamadas a herramientas.\n"
                        "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
                        "  DETAILS: Se superó ADMADC_TOOL_LOOP_MAX_TOOL_CALLS.\n"
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
                    "content": _QA_PARSE_REPAIR + " Responde sin herramientas.",
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
    r = _parse_review_response(
        "REASONING: QA tool loop agotó el máximo de pasos sin veredicto final.\n"
        "VERDICT: FAIL\nISSUES:\n- [error|functional] exhausted\n"
        "  DETAILS: Aumenta QA_TOOL_LOOP_MAX_STEPS o reduce el alcance.\n"
    )
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
    reasoning = ""
    in_issues = False
    current_section: Literal["functionality", "style", "security", "other"] = "other"
    structured: dict[str, list[dict]] = {
        "functionality": [],
        "style": [],
        "security": [],
    }

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
    )
