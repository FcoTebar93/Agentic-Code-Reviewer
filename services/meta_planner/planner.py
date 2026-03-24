"""
Core planning logic.

Takes a user prompt and uses the LLM adapter to decompose it into
a list of concrete development tasks (TaskSpec).

The LLM is asked for both a REASONING block (visible in the event feed)
and a TASKS block (structured JSON). This surfaces the architect's
decision-making to the frontend.
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

logger = logging.getLogger(__name__)

SERVICE_NAME = "meta_planner"

ADMADC_TOOL_LOOP_MARKER = "[ADMADC_TOOL_LOOP]"

_PLANNER_PARSE_REPAIR = (
    "The TASKS section must be a valid JSON array of objects with keys description, file_path, language "
    "(and optionally edit_scope, group_id). Repeat the full answer with corrected REASONING: and TASKS:."
)

_PLANNER_TOOL_NAMES = (
    "semantic_search_memory",
    "query_events",
    "failure_patterns",
)

PLANNER_SENIOR_GUIDELINES = """
Delivery quality and dependencies:
- For non-trivial work, add focused tasks when they materially reduce risk: for example shared validation or error
  contracts, typing/schema boundaries, small refactors that unblock correct implementation, or hardening after HOT SPOTS—
  not every plan needs these; avoid busywork on trivial requests.
- When tasks depend on each other, order the TASKS JSON array in a dependency-safe sequence (e.g. shared models,
  protocols, or public API surfaces before callers and UI that consume them).
- In REASONING, briefly state implementation or review order when it matters (what should land first and why), and how
  grouped tasks relate within the same group_id.
"""


PLANNING_PROMPT_TEMPLATE = (
    """You are a senior software architect acting as the PLANNER in a multi-agent CI pipeline.

Given the following user request, decompose it into a list of concrete development tasks that are:
- SMALL and FOCUSED (each task should have a single clear goal).
- SCOPED to a TINY set of files (ideally 1 file, exceptionally up to 3 closely-related files inside the same module/directory).
- HOMOGENEOUS in shape so that downstream agents can process, test and review them independently.

You also have access to selected memories from past plans and pipeline runs.
These may include previous user prompts, planner reasoning, pipeline conclusions,
and QA/security outcomes. Use them only if they are truly relevant; otherwise,
ignore them.

If the MEMORY CONTEXT includes QA or security failures (qa.failed / security.blocked),
you MUST explicitly understand what failed (which QA or security rules were violated)
and adjust the new plan so that future Dev/QA/Security steps fix those issues and
comply with the referenced rules. Avoid repeating the same mistakes across plans.

If the MEMORY CONTEXT contains aggregated "Historical failure patterns" by module,
you MUST:
- Treat modules with frequent QA_FAILED / SECURITY_BLOCKED counts as HOT SPOTS.
- Pay attention to any severity hints (for example: low/medium/high/critical) and prioritise
  HOT SPOTS with higher severity when deciding where to add new tasks.
- Prefer creating explicit tasks to add or harden tests and safeguards around those modules
  (for example: more unit/integration tests, stricter input validation, better error handling).
- Avoid introducing new cross-cutting changes that touch many unrelated modules at once.

For large or cross-cutting changes, break the work into several smaller tasks grouped
by module/directory, instead of a single huge task that touches many different parts
of the repository.
"""
    + PLANNER_SENIOR_GUIDELINES
    + """
MEMORY CONTEXT:
{memory_context}

RESPONSE LANGUAGE:
{response_language_rules}

First, explain your reasoning: why these tasks, what architectural decisions you made,
how you are using MEMORY CONTEXT (especially failure patterns and severity hints), how tasks relate to each other,
and (when relevant) the intended order of work or review across dependent tasks.

Then output the task list. For simple requests (e.g. "create a Hello World in X"),
output a SINGLE task with one file_path. Do not duplicate the same file_path.

Format your response EXACTLY as:
REASONING: <your architectural reasoning in 2-4 sentences>
TASKS: <JSON array of objects with keys: description, file_path, language and, optionally, edit_scope and group_id>

Conventions:
- Use edit_scope=\"file\" when possible, or \"module\" when a change spans a small, coherent package.
- Use group_id to group related tasks by module/directory (for example: \"services/dev_service\", \"frontend/src/components\").
- List TASKS in dependency-safe order when one change must exist before another can be implemented correctly.

User request:
{prompt}
"""
)


PLANNER_TOOL_LOOP_SYSTEM = (
    """You are a senior software architect (PLANNER) in a multi-agent CI pipeline.

Call memory tools when you need past events, semantic recall, or failure-by-module patterns.
Keep tasks small (ideally one file), avoid huge cross-cutting changes, and respect QA/security hotspots from tool data.

"""
    + PLANNER_SENIOR_GUIDELINES
    + """
{response_language_rules}

Final message must have NO tool calls, exactly:
REASONING: <architectural reasoning in 2-4 sentences (include task order when dependencies exist)>
TASKS: <JSON array in dependency-safe order when applicable; keys: description, file_path, language and optionally edit_scope, group_id>
"""
)


PLANNER_TOOL_LOOP_USER = ADMADC_TOOL_LOOP_MARKER + """

User request:
{prompt}

Pre-fetched memory summary (use tools if you need more; may be partial):
{memory_seed}
"""


@dataclass
class PlanResult:
    tasks: list[TaskSpec]
    reasoning: str


async def decompose_tasks(
    llm: LLMProvider,
    user_prompt: str,
    memory_context: str = "",
    user_locale: str = "en",
) -> tuple[PlanResult, int, int]:
    """Call the LLM to break a user prompt into TaskSpecs with reasoning. Returns (result, prompt_tokens, completion_tokens)."""
    prompt = PLANNING_PROMPT_TEMPLATE.format(
        prompt=user_prompt,
        memory_context=memory_context.strip() or "None.",
        response_language_rules=natural_language_rules_for_locale(user_locale),
    )
    response: LLMResponse = await llm.generate_text(prompt)

    pt = response.prompt_tokens or 0
    ct = response.completion_tokens or 0
    if pt or ct:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)

    reasoning, tasks, json_ok = _parse_response(response.content)
    if not json_ok:
        repair = f"{prompt}\n\n{_PLANNER_PARSE_REPAIR}"
        response2: LLMResponse = await llm.generate_text(repair)
        pt2 = response2.prompt_tokens or 0
        ct2 = response2.completion_tokens or 0
        pt += pt2
        ct += ct2
        if pt2 or ct2:
            llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt2)
            llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct2)
        reasoning, tasks, _ = _parse_response(response2.content)
    logger.info(
        "Decomposed prompt into %d tasks. Reasoning: %s",
        len(tasks),
        reasoning[:80],
    )
    return PlanResult(tasks=tasks, reasoning=reasoning), pt, ct


def _tool_payload(result: ToolExecutionResult) -> str:
    if result.success:
        return json.dumps(result.output, default=str)
    return json.dumps({"success": False, "error": result.error or "unknown"})


async def decompose_tasks_with_tool_loop(
    llm: LLMProvider,
    registry: ToolRegistry,
    user_prompt: str,
    memory_seed: str = "",
    *,
    max_steps: int = 8,
    plan_id: str | None = None,
    redis_url: str | None = None,
    user_locale: str = "en",
) -> tuple[PlanResult, int, int]:
    """
    Multi-turn planning with memory_service tools before REASONING/TASKS.
    """
    tools = tools_openai_from_registry(registry, _PLANNER_TOOL_NAMES)
    if not tools:
        logger.warning("Planner tool loop: no tools in registry; single-shot planning")
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="fallback_single_shot"
        ).inc()
        return await decompose_tasks(
            llm, user_prompt, memory_context=memory_seed, user_locale=user_locale
        )

    user_content = PLANNER_TOOL_LOOP_USER.format(
        prompt=user_prompt,
        memory_seed=(memory_seed.strip() or "None."),
    )
    system_content = PLANNER_TOOL_LOOP_SYSTEM.format(
        response_language_rules=natural_language_rules_for_locale(user_locale),
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
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
            reasoning, tasks, _ = _parse_response("")
            return PlanResult(tasks=tasks, reasoning=reasoning), total_pt, total_ct
        if budget.max_tokens_plan > 0:
            allowed = await plan_tool_loop_try_add_tokens(
                redis_url, plan_id, pt + ct, budget.max_tokens_plan
            )
            if not allowed:
                agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
                agent_tool_loop_outcomes_total.labels(
                    service=SERVICE_NAME, outcome="budget_exceeded"
                ).inc()
                reasoning, tasks, _ = _parse_response("")
                return PlanResult(tasks=tasks, reasoning=reasoning), total_pt, total_ct

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
                    reasoning, tasks, _ = _parse_response("")
                    return PlanResult(tasks=tasks, reasoning=reasoning), total_pt, total_ct
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

        reasoning, tasks, json_ok = _parse_response(resp.content or "")
        if not json_ok:
            messages.append({"role": "user", "content": _PLANNER_PARSE_REPAIR})
            continue
        agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
        agent_tool_loop_outcomes_total.labels(
            service=SERVICE_NAME, outcome="completed"
        ).inc()
        logger.info(
            "Planner tool-loop decomposed into %d tasks. Reasoning: %s",
            len(tasks),
            reasoning[:80],
        )
        return PlanResult(tasks=tasks, reasoning=reasoning), total_pt, total_ct

    agent_tool_loop_llm_rounds.labels(service=SERVICE_NAME).observe(float(llm_rounds))
    agent_tool_loop_outcomes_total.labels(
        service=SERVICE_NAME, outcome="exhausted"
    ).inc()
    reasoning, tasks, _ = _parse_response("")
    logger.warning("Planner tool loop exhausted max_steps=%s", max_steps)
    return PlanResult(tasks=tasks, reasoning=reasoning), total_pt, total_ct


def _parse_response(raw: str) -> tuple[str, list[TaskSpec], bool]:
    """
    Parse LLM output into (reasoning, TaskSpec list, json_ok).

    json_ok False indica que hubo que usar el fallback de una sola tarea.
    """
    if not (raw or "").strip():
        return "", [], True
    reasoning = ""
    tasks_raw = raw.strip()

    if "REASONING:" in raw:
        parts = raw.split("TASKS:", 1)
        reasoning_part = parts[0].replace("REASONING:", "").strip()
        reasoning = reasoning_part
        tasks_raw = parts[1].strip() if len(parts) > 1 else "[]"

    cleaned = tasks_raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:])
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        items = json.loads(cleaned)
        if isinstance(items, list):
            specs = [
                TaskSpec(
                    description=item.get("description", ""),
                    file_path=item.get("file_path", "unknown.py"),
                    language=item.get("language", "python"),
                    edit_scope=item.get("edit_scope", "file"),
                    group_id=item.get("group_id", "") or "",
                )
                for item in items
                if isinstance(item, dict)
            ]
            return reasoning, specs, bool(specs)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse LLM task list as JSON, creating fallback task")

    return (
        reasoning,
        [
            TaskSpec(
                description=f"Implement: {tasks_raw[:200]}",
                file_path="src/main.py",
                language="python",
            )
        ],
        False,
    )
