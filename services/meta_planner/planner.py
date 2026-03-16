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

from shared.contracts.events import TaskSpec
from shared.llm_adapter import LLMProvider, LLMResponse
from shared.observability.metrics import llm_tokens

logger = logging.getLogger(__name__)

SERVICE_NAME = "meta_planner"

PLANNING_PROMPT_TEMPLATE = """You are a senior software architect acting as the PLANNER in a multi-agent CI pipeline.

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

MEMORY CONTEXT:
{memory_context}

First, explain your reasoning: why these tasks, what architectural decisions you made,
how you are using MEMORY CONTEXT (especially failure patterns and severity hints), and how tasks relate
to each other.

Then output the task list. For simple requests (e.g. "create a Hello World in X"),
output a SINGLE task with one file_path. Do not duplicate the same file_path.

Format your response EXACTLY as:
REASONING: <your architectural reasoning in 2-3 sentences>
TASKS: <JSON array of objects with keys: description, file_path, language and, optionally, edit_scope and group_id>

Conventions:
- Use edit_scope=\"file\" when possible, or \"module\" when a change spans a small, coherent package.
- Use group_id to group related tasks by module/directory (for example: \"services/dev_service\", \"frontend/src/components\").

User request:
{prompt}
"""


@dataclass
class PlanResult:
    tasks: list[TaskSpec]
    reasoning: str


async def decompose_tasks(
    llm: LLMProvider,
    user_prompt: str,
    memory_context: str = "",
) -> tuple[PlanResult, int, int]:
    """Call the LLM to break a user prompt into TaskSpecs with reasoning. Returns (result, prompt_tokens, completion_tokens)."""
    prompt = PLANNING_PROMPT_TEMPLATE.format(
        prompt=user_prompt,
        memory_context=memory_context.strip() or "None.",
    )
    response: LLMResponse = await llm.generate_text(prompt)

    pt = response.prompt_tokens or 0
    ct = response.completion_tokens or 0
    if pt or ct:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)

    reasoning, tasks = _parse_response(response.content)
    logger.info(
        "Decomposed prompt into %d tasks. Reasoning: %s",
        len(tasks),
        reasoning[:80],
    )
    return PlanResult(tasks=tasks, reasoning=reasoning), pt, ct


def _parse_response(raw: str) -> tuple[str, list[TaskSpec]]:
    """
    Parse LLM output into (reasoning, TaskSpec list).

    Handles both the structured REASONING/TASKS format and raw JSON fallback.
    """
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
            return reasoning, [
                TaskSpec(
                    description=item.get("description", ""),
                    file_path=item.get("file_path", "unknown.py"),
                    language=item.get("language", "python"),
                    edit_scope=item.get("edit_scope", "file"),
                    group_id=item.get("group_id", "") or "",
                )
                for item in items
            ]
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse LLM task list as JSON, creating fallback task")

    return reasoning, [
        TaskSpec(
            description=f"Implement: {tasks_raw[:200]}",
            file_path="src/main.py",
            language="python",
        )
    ]
