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

from shared.contracts.events import TaskSpec
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
from shared.utils import infer_framework_hint
from services.dev_service.prompts import (
    CODE_GEN_PROMPT,
    CODE_GEN_PROMPT_NO_PRIOR,
    TOOL_LOOP_SYSTEM,
)

logger = logging.getLogger(__name__)


@dataclass
class CodeResult:
    code: str
    reasoning: str


SERVICE_NAME = "dev_service"

_READ_ONLY_TOOLS = ("read_file", "list_project_files", "search_in_repo")
_CI_TOOLS = ("run_tests", "run_lints")


def _tool_loop_tool_names(include_ci: bool) -> list[str]:
    names = list(_READ_ONLY_TOOLS)
    if include_ci:
        names.extend(_CI_TOOLS)
    return names


def _build_codegen_user_content(
    task: TaskSpec,
    plan_reasoning: str,
    short_term_memory: str,
) -> str:
    framework_hint = infer_framework_hint(task.language, task.file_path)
    stm_block = short_term_memory.strip()
    if framework_hint:
        stm_block = f"FRAMEWORK HINT: {framework_hint}\n\n" + (stm_block or "")
    if plan_reasoning.strip():
        return CODE_GEN_PROMPT.format(
            language=task.language,
            plan_reasoning=plan_reasoning,
            description=task.description,
            file_path=task.file_path,
            short_term_memory=stm_block or "None.",
        )
    return CODE_GEN_PROMPT_NO_PRIOR.format(
        language=task.language,
        description=task.description,
        file_path=task.file_path,
    )


def _tool_message_payload(result: ToolExecutionResult) -> str:
    if result.success:
        return json.dumps(result.output, default=str)
    return json.dumps({"success": False, "error": result.error or "unknown"})


async def generate_code(
    llm: LLMProvider,
    task: TaskSpec,
    plan_reasoning: str = "",
    short_term_memory: str = "",
) -> tuple[CodeResult, int, int]:
    """Use the LLM to generate code for a single task. Returns (result, prompt_tokens, completion_tokens)."""
    prompt = _build_codegen_user_content(task, plan_reasoning, short_term_memory)

    response: LLMResponse = await llm.generate_text(prompt)
    pt = response.prompt_tokens or 0
    ct = response.completion_tokens or 0
    if pt or ct:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)
    result = _parse_response(response.content)

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
        return await generate_code(llm, task, plan_reasoning, short_term_memory)

    user_content = _build_codegen_user_content(task, plan_reasoning, short_term_memory)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": TOOL_LOOP_SYSTEM.format(language=task.language),
        },
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
