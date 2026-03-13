"""
Code generation logic using the LLM adapter.

Each developer agent:
1. Reads the planner's reasoning and explicitly responds to it.
2. Implements the task with production-quality code.
3. Returns both REASONING (referencing the planner) and the CODE.

This creates a visible chain of inter-agent communication in the event feed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shared.contracts.events import TaskSpec
from shared.llm_adapter import LLMProvider, LLMResponse
from shared.observability.metrics import llm_tokens
from shared.utils import infer_framework_hint
from services.dev_service.prompts import CODE_GEN_PROMPT, CODE_GEN_PROMPT_NO_PRIOR

logger = logging.getLogger(__name__)


@dataclass
class CodeResult:
    code: str
    reasoning: str


SERVICE_NAME = "dev_service"


async def generate_code(
    llm: LLMProvider,
    task: TaskSpec,
    plan_reasoning: str = "",
    short_term_memory: str = "",
) -> tuple[CodeResult, int, int]:
    """Use the LLM to generate code for a single task. Returns (result, prompt_tokens, completion_tokens)."""
    is_patch_like = getattr(task, "edit_scope", "file") != "file"
    framework_hint = infer_framework_hint(task.language, task.file_path)
    stm_block = short_term_memory.strip()
    if framework_hint:
        prefix = f"FRAMEWORK HINT: {framework_hint}\n\n"
        stm_block = prefix + (stm_block or "")
    if plan_reasoning.strip():
        prompt = CODE_GEN_PROMPT.format(
            language=task.language,
            plan_reasoning=plan_reasoning,
            description=task.description,
            file_path=task.file_path,
            short_term_memory=stm_block or "None.",
        )
    else:
        prompt = CODE_GEN_PROMPT_NO_PRIOR.format(
            language=task.language,
            description=task.description,
            file_path=task.file_path,
        )

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
