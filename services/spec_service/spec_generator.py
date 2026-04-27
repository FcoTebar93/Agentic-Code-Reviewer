"""LLM spec generation: single-shot or multi-turn with repository tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from services.spec_service.prompts import SPEC_PROMPT, SPEC_TOOL_LOOP_SYSTEM
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

SERVICE_NAME = "spec_service"

_SPEC_TOOLS = ("read_file", "list_project_files", "search_in_repo")

_SPEC_REPAIR = (
    "The final answer must contain SPEC: (including ACCEPTANCE CRITERIA: as a numbered list) "
    "and TESTS: sections with non-empty content unless the task is trivial."
)


def build_spec_user_prompt(
    *,
    description: str,
    file_path: str,
    language: str,
    plan_context: str,
    test_layout: str,
    mode: str,
    user_locale: str = "en",
) -> str:
    fw_hint = infer_framework_hint(language, file_path)
    ctx_block = plan_context.strip()
    if fw_hint:
        ctx_block = f"FRAMEWORK HINT: {fw_hint}\n\n" + (ctx_block or "")
    return SPEC_PROMPT.format(
        language=language or "python",
        description=description,
        file_path=file_path,
        plan_context=ctx_block or "None.",
        test_layout=test_layout.strip() or "None.",
        mode=(mode or "normal").strip().lower(),
        response_language_rules=natural_language_rules_for_locale(user_locale),
    )


def parse_spec_response(raw: str) -> tuple[str, str]:
    spec_block = ""
    tests_block = ""
    current = None
    lines = raw.strip().splitlines()
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("SPEC:"):
            current = "spec"
            content = stripped[len("SPEC:") :].strip()
            if content:
                spec_block += content + "\n"
        elif upper.startswith("TESTS:"):
            current = "tests"
            content = stripped[len("TESTS:") :].strip()
            if content:
                tests_block += content + "\n"
        else:
            if current == "spec":
                spec_block += stripped + "\n"
            elif current == "tests":
                tests_block += stripped + "\n"
    return spec_block.strip(), tests_block.strip()


def _spec_parse_ok(spec_text: str, tests_text: str, _raw: str) -> bool:
    return bool(spec_text.strip() or tests_text.strip())


def _tool_payload(result: ToolExecutionResult) -> str:
    if result.success:
        return json.dumps(result.output, default=str)
    return json.dumps({"success": False, "error": result.error or "unknown"})


async def generate_spec(
    llm: LLMProvider,
    *,
    description: str,
    file_path: str,
    language: str,
    plan_context: str,
    test_layout: str,
    mode: str,
    user_locale: str = "en",
) -> tuple[dict[str, str], int, int]:
    prompt = build_spec_user_prompt(
        description=description,
        file_path=file_path,
        language=language,
        plan_context=plan_context,
        test_layout=test_layout,
        mode=mode,
        user_locale=user_locale,
    )
    def _parse(raw: str) -> tuple[dict[str, str] | None, bool]:
        spec_text, tests_text = parse_spec_response(raw or "")
        d = {"spec": spec_text, "tests": tests_text}
        return d, _spec_parse_ok(spec_text, tests_text, raw or "")

    out, pt, ct = await generate_text_with_parse_retry(
        llm,
        initial_prompt=prompt,
        repair_instruction=_SPEC_REPAIR,
        parse=_parse,
        service_name=SERVICE_NAME,
        max_attempts=2,
    )
    return out, pt, ct


async def generate_spec_with_tool_loop(
    llm: LLMProvider,
    registry: ToolRegistry,
    *,
    description: str,
    file_path: str,
    language: str,
    plan_context: str,
    test_layout: str,
    mode: str,
    max_steps: int = 8,
    plan_id: str | None = None,
    redis_url: str | None = None,
    user_locale: str = "en",
) -> tuple[dict[str, str], int, int]:
    tools = tools_openai_from_registry(registry, _SPEC_TOOLS)
    if not tools:
        logger.warning("Spec tool loop: no tools in registry; using single-shot")
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="fallback_single_shot"
        ).inc()
        return await generate_spec(
            llm,
            description=description,
            file_path=file_path,
            language=language,
            plan_context=plan_context,
            test_layout=test_layout,
            mode=mode,
            user_locale=user_locale,
        )

    user_content = build_spec_user_prompt(
        description=description,
        file_path=file_path,
        language=language,
        plan_context=plan_context,
        test_layout=test_layout,
        mode=mode,
        user_locale=user_locale,
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": SPEC_TOOL_LOOP_SYSTEM.format(
                language=language or "python",
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
                {
                    "spec": "",
                    "tests": "",
                },
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
                    {"spec": "", "tests": ""},
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
                    return (
                        {"spec": "", "tests": ""},
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
                        "content": _tool_payload(exec_result),
                    }
                )
            continue

        spec_text, tests_text = parse_spec_response(resp.content or "")
        if not _spec_parse_ok(spec_text, tests_text, resp.content or ""):
            messages.append(
                {
                    "role": "user",
                    "content": _SPEC_REPAIR + " Responde solo con SPEC: y TESTS:, sin herramientas.",
                }
            )
            continue
        agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="completed"
        ).inc()
        if not spec_text and not tests_text:
            logger.warning(
                "Spec tool loop: final message had no SPEC/TESTS blocks (file=%s)",
                (file_path or "")[:60],
            )
        return {"spec": spec_text, "tests": tests_text}, total_pt, total_ct

    agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
    agent_tool_loop_outcomes_total.labels(
        service=SERVICE_NAME, outcome="exhausted"
    ).inc()
    empty = {
        "spec": "",
        "tests": "",
    }
    logger.warning(
        "Spec tool loop exceeded max_steps=%s without final SPEC/TESTS (file=%s)",
        max_steps,
        (file_path or "")[:60],
    )
    return empty, total_pt, total_ct
