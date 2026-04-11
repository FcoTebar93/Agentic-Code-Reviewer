"""
Code generation logic using the LLM adapter.

Each developer agent:
1. Reads the planner's reasoning and explicitly responds to it.
2. Implements the task with production-quality code.
3. Returns both REASONING (referencing the planner) and the CODE.

This creates a visible chain of inter-agent communication in the event feed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from services.dev_service.prompts import (
    CODE_GEN_PROMPT,
    CODE_GEN_PROMPT_NO_PRIOR,
    TOOL_LOOP_SYSTEM,
)
from services.dev_service.security_gate_brief import security_gate_brief
from shared.contracts.events import TaskSpec
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
from shared.prompt_locale import natural_language_rules_for_locale
from shared.tools import ToolRegistry, execute_tool
from shared.tools.models import ToolExecutionResult
from shared.utils import infer_framework_hint

logger = logging.getLogger(__name__)


@dataclass
class CodeResult:
    code: str
    reasoning: str


SERVICE_NAME = "dev_service"

_CODEGEN_REPAIR = (
    "Your answer must include exactly the REASONING: and CODE: sections with executable code "
    "in CODE (non-empty unless the task is explicitly empty). "
    "CODE must be only the target file — one file, no markdown fences, no extra files. "
    "Keep REASONING short (2-4 sentences). Prefer minimal edits; do not rewrite unrelated code."
)

_READ_ONLY_TOOLS = ("read_file", "list_project_files", "search_in_repo")
_CI_TOOLS = ("run_tests", "run_lints")


def _tool_loop_tool_names(include_ci: bool) -> list[str]:
    names = list(_READ_ONLY_TOOLS)
    if include_ci:
        names.extend(_CI_TOOLS)
    return names


def _qa_feedback_block(qa_feedback: str) -> str:
    q = (qa_feedback or "").strip()
    if not q:
        return ""
    return (
        "---\nQA FEEDBACK (previous submission rejected — address everything below):\n"
        f"{q}\n---\n\n"
    )


def _security_brief_block() -> str:
    body = security_gate_brief().strip()
    if not body:
        return ""
    return f"---\n{body}\n---\n\n"


def _build_codegen_user_content(
    task: TaskSpec,
    plan_reasoning: str,
    short_term_memory: str,
    user_locale: str = "en",
    *,
    qa_feedback: str = "",
) -> str:
    framework_hint = infer_framework_hint(task.language, task.file_path)
    stm_block = short_term_memory.strip()
    if framework_hint:
        stm_block = f"FRAMEWORK HINT: {framework_hint}\n\n" + (stm_block or "")
    rules = natural_language_rules_for_locale(user_locale)
    qa_block = _qa_feedback_block(qa_feedback)
    sec_block = _security_brief_block()
    if plan_reasoning.strip():
        return CODE_GEN_PROMPT.format(
            language=task.language,
            plan_reasoning=plan_reasoning,
            description=task.description,
            file_path=task.file_path,
            qa_feedback_block=qa_block,
            security_brief_block=sec_block,
            short_term_memory=stm_block or "None.",
            response_language_rules=rules,
        )
    return CODE_GEN_PROMPT_NO_PRIOR.format(
        language=task.language,
        description=task.description,
        file_path=task.file_path,
        qa_feedback_block=qa_block,
        security_brief_block=sec_block,
        response_language_rules=rules,
    )


def _tool_message_payload(result: ToolExecutionResult) -> str:
    if result.success:
        return json.dumps(result.output, default=str)
    return json.dumps({"success": False, "error": result.error or "unknown"})


def _codegen_parse_ok(result: CodeResult, _raw: str) -> bool:
    return bool((result.code or "").strip())


async def generate_code(
    llm: LLMProvider,
    task: TaskSpec,
    plan_reasoning: str = "",
    short_term_memory: str = "",
    user_locale: str = "en",
    *,
    qa_feedback: str = "",
) -> tuple[CodeResult, int, int]:
    """Use the LLM to generate code for a single task. Returns (result, prompt_tokens, completion_tokens)."""
    prompt = _build_codegen_user_content(
        task,
        plan_reasoning,
        short_term_memory,
        user_locale=user_locale,
        qa_feedback=qa_feedback,
    )

    def _parse(raw: str) -> tuple[CodeResult | None, bool]:
        r = _parse_response(raw)
        return r, _codegen_parse_ok(r, raw)

    result, pt, ct = await generate_text_with_parse_retry(
        llm,
        initial_prompt=prompt,
        repair_instruction=_CODEGEN_REPAIR,
        parse=_parse,
        service_name=SERVICE_NAME,
        max_attempts=2,
    )

    logger.info(
        "Generated %d chars of %s code for %s. Reasoning: %s",
        len(result.code), task.language, task.file_path, result.reasoning[:80],
    )
    return result, pt, ct


async def generate_code_with_tool_loop(
    llm: LLMProvider,
    task: TaskSpec,
    *,
    plan_reasoning: str = "",
    short_term_memory: str = "",
    registry: ToolRegistry,
    max_steps: int = 8,
    include_ci_tools: bool = False,
    plan_id: str | None = None,
    redis_url: str | None = None,
    user_locale: str = "en",
    qa_feedback: str = "",
) -> tuple[CodeResult, int, int]:
    """
    Multi-turn generation: model may call repo tools before emitting REASONING/CODE.

    Requires an OpenAI-compatible provider that supports Chat Completions tools.
    The mock provider simulates one read_file round for local tests.
    """
    tools = tools_openai_from_registry(registry, _tool_loop_tool_names(include_ci_tools))
    if not tools:
        logger.warning("Tool loop: no tools matched registry; using single-shot codegen")
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="fallback_single_shot"
        ).inc()
        return await generate_code(
            llm,
            task,
            plan_reasoning,
            short_term_memory,
            user_locale=user_locale,
            qa_feedback=qa_feedback,
        )

    user_content = _build_codegen_user_content(
        task,
        plan_reasoning,
        short_term_memory,
        user_locale=user_locale,
        qa_feedback=qa_feedback,
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": TOOL_LOOP_SYSTEM.format(
                language=task.language,
                response_language_rules=natural_language_rules_for_locale(user_locale),
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
            return (
                CodeResult(
                    code="",
                    reasoning=(
                        "Dev tool loop detenido: presupuesto de tokens del bucle superado "
                        "(ADMADC_TOOL_LOOP_MAX_TOKENS_PER_LOOP)."
                    ),
                ),
                total_pt,
                total_ct,
            )
        if budget.max_tokens_plan > 0:
            allowed = await plan_tool_loop_try_add_tokens(
                redis_url, plan_id, pt + ct, budget.max_tokens_plan
            )
            if not allowed:
                agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
                agent_tool_loop_outcomes_total.labels(
                    service=SERVICE_NAME, outcome="budget_exceeded"
                ).inc()
                return (
                    CodeResult(
                        code="",
                        reasoning=(
                            "Dev tool loop detenido: presupuesto acumulado de tokens por plan "
                            "superado (ADMADC_PLAN_TOOL_LOOP_MAX_TOKENS)."
                        ),
                    ),
                    total_pt,
                    total_ct,
                )

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
                        args_dict = json.loads(raw_args.strip() or "{}")
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
                    return (
                        CodeResult(
                            code="",
                            reasoning=(
                                "Dev tool loop detenido: límite de llamadas a herramientas "
                                "superado (ADMADC_TOOL_LOOP_MAX_TOOL_CALLS)."
                            ),
                        ),
                        total_pt,
                        total_ct,
                    )
                agent_tool_calls_total.labels(
                    service=SERVICE_NAME,
                    tool_name=name or "unknown",
                    result="success" if exec_result.success else "failure",
                ).inc()
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tc.get("id") or ""),
                        "content": _tool_message_payload(exec_result),
                    }
                )
            continue

        result = _parse_response(resp.content or "")
        if not _codegen_parse_ok(result, resp.content or ""):
            messages.append(
                {
                    "role": "user",
                    "content": (
                        _CODEGEN_REPAIR
                        + " Devuelve de nuevo REASONING: y CODE: completos en un único mensaje "
                        "sin herramientas."
                    ),
                }
            )
            continue
        agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="completed"
        ).inc()
        logger.info(
            "Tool-loop generated %d chars of %s code for %s. Reasoning: %s",
            len(result.code),
            task.language,
            task.file_path,
            result.reasoning[:80],
        )
        return result, total_pt, total_ct

    agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
    agent_tool_loop_outcomes_total.labels(
        service=SERVICE_NAME, outcome="exhausted"
    ).inc()
    result = CodeResult(
        code="",
        reasoning=(
            "Dev tool loop stopped after maximum steps without a final CODE block. "
            "Consider raising DEV_TOOL_LOOP_MAX_STEPS or simplifying the task."
        ),
    )
    return result, total_pt, total_ct


def _parse_response(raw: str) -> CodeResult:
    """Parse REASONING/CODE sections from the LLM response."""
    reasoning = ""
    code = raw.strip()

    if "REASONING:" in raw and "CODE:" in raw:
        parts = raw.split("CODE:", 1)
        reasoning_part = parts[0].replace("REASONING:", "").strip()
        reasoning = reasoning_part
        code = parts[1].strip()
    elif "REASONING:" in raw:
        parts = raw.split("REASONING:", 1)
        reasoning = parts[1].strip() if len(parts) > 1 else ""
        code = ""

    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:])
        if code.endswith("```"):
            code = code[:-3].strip()

    return CodeResult(code=code.strip(), reasoning=reasoning)
