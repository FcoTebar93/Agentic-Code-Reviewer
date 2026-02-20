"""
Core planning logic.

Takes a user prompt and uses the LLM adapter to decompose it into
a list of concrete development tasks (TaskSpec).
"""

from __future__ import annotations

import json
import logging

from shared.contracts.events import TaskSpec
from shared.llm_adapter import LLMProvider

logger = logging.getLogger(__name__)

PLANNING_PROMPT_TEMPLATE = """You are a senior software architect. Given the following user request,
decompose it into a list of concrete development tasks.

Each task must specify:
- description: what the task does
- file_path: the file to create/modify
- language: programming language

Return ONLY a JSON array of objects with keys: description, file_path, language.
Do NOT include any explanation outside the JSON array.

User request:
{prompt}
"""


async def decompose_tasks(
    llm: LLMProvider, user_prompt: str
) -> list[TaskSpec]:
    """Call the LLM to break a user prompt into TaskSpecs."""
    prompt = PLANNING_PROMPT_TEMPLATE.format(prompt=user_prompt)
    response = await llm.generate_text(prompt)

    tasks = _parse_tasks(response.content)
    logger.info("Decomposed prompt into %d tasks", len(tasks))
    return tasks


def _parse_tasks(raw: str) -> list[TaskSpec]:
    """
    Parse LLM output into TaskSpec list.

    Handles both clean JSON and markdown-wrapped responses.
    Falls back to a single generic task if parsing fails.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:])
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        items = json.loads(cleaned)
        if isinstance(items, list):
            return [
                TaskSpec(
                    description=item.get("description", ""),
                    file_path=item.get("file_path", "unknown.py"),
                    language=item.get("language", "python"),
                )
                for item in items
            ]
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse LLM response as JSON, creating fallback task")

    return [
        TaskSpec(
            description=f"Implement: {raw[:200]}",
            file_path="src/main.py",
            language="python",
        )
    ]
