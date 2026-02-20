"""
Code generation logic using the LLM adapter.
"""

from __future__ import annotations

import logging

from shared.contracts.events import TaskSpec
from shared.llm_adapter import LLMProvider

logger = logging.getLogger(__name__)

CODE_GEN_PROMPT = """You are an expert {language} developer.

Write production-quality code for the following task:
{description}

The code should be written for file: {file_path}

Return ONLY the code. No explanations, no markdown fences.
"""


async def generate_code(llm: LLMProvider, task: TaskSpec) -> str:
    """Use the LLM to generate code for a single task."""
    prompt = CODE_GEN_PROMPT.format(
        language=task.language,
        description=task.description,
        file_path=task.file_path,
    )
    response = await llm.generate_text(prompt)

    code = response.content.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:])
        if code.endswith("```"):
            code = code[:-3].strip()

    logger.info(
        "Generated %d chars of %s code for %s",
        len(code), task.language, task.file_path,
    )
    return code
