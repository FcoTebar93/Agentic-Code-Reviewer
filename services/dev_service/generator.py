"""
Code generation logic using the LLM adapter.

The LLM is asked to provide both a REASONING block (design decisions,
approach chosen, libraries considered) and the actual CODE block.
This makes the developer agent's thinking visible in the event feed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shared.contracts.events import TaskSpec
from shared.llm_adapter import LLMProvider

logger = logging.getLogger(__name__)

CODE_GEN_PROMPT = """You are an expert {language} developer.

Write production-quality code for the following task:
{description}

The code should be written for file: {file_path}

First explain your reasoning: what approach you chose, why, and any trade-offs considered.
Then provide the complete code.

Format your response EXACTLY as:
REASONING: <your design reasoning in 2-3 sentences>
CODE:
<the complete code, no markdown fences>
"""


@dataclass
class CodeResult:
    code: str
    reasoning: str


async def generate_code(llm: LLMProvider, task: TaskSpec) -> CodeResult:
    """Use the LLM to generate code for a single task, with reasoning."""
    prompt = CODE_GEN_PROMPT.format(
        language=task.language,
        description=task.description,
        file_path=task.file_path,
    )
    response = await llm.generate_text(prompt)
    result = _parse_response(response.content)

    logger.info(
        "Generated %d chars of %s code for %s. Reasoning: %s",
        len(result.code), task.language, task.file_path, result.reasoning[:60],
    )
    return result


def _parse_response(raw: str) -> CodeResult:
    """
    Parse REASONING/CODE sections from the LLM response.
    Falls back gracefully if the format is not followed.
    """
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
