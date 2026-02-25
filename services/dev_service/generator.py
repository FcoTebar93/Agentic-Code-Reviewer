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

logger = logging.getLogger(__name__)

CODE_GEN_PROMPT = """You are an expert {language} developer working inside a multi-agent pipeline.

The planning agent has already analysed the project and provided the following reasoning:
---
PLANNER'S REASONING:
{plan_reasoning}
---

Your task is:
{description}

Target file: {file_path}

You also have access to a short memory window of recent events for this plan
(planner decisions, previous code generations, QA/security results, etc.).
Use this context to stay consistent with prior steps, but ignore anything that
is clearly irrelevant.

SHORT-TERM MEMORY:
{short_term_memory}

Instructions:
1. Start your response by explicitly referencing and responding to the planner's reasoning above.
2. Explain the implementation approach you chose and why, addressing any decisions the planner raised.
3. Write complete, production-quality {language} code.

Format your response EXACTLY as:
REASONING: <2-4 sentences that (a) acknowledge the planner's analysis, (b) explain your implementation decisions>
CODE:
<the complete code, no markdown fences>
"""

CODE_GEN_PROMPT_NO_PRIOR = """You are an expert {language} developer.

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


SERVICE_NAME = "dev_service"


async def generate_code(
    llm: LLMProvider,
    task: TaskSpec,
    plan_reasoning: str = "",
    short_term_memory: str = "",
) -> CodeResult:
    """Use the LLM to generate code for a single task.

    If plan_reasoning is provided, the prompt instructs the developer agent
    to explicitly respond to the planner's reasoning, creating a visible
    inter-agent dialogue.
    """
    if plan_reasoning.strip():
        prompt = CODE_GEN_PROMPT.format(
            language=task.language,
            plan_reasoning=plan_reasoning,
            description=task.description,
            file_path=task.file_path,
            short_term_memory=short_term_memory.strip() or "None.",
        )
    else:
        prompt = CODE_GEN_PROMPT_NO_PRIOR.format(
            language=task.language,
            description=task.description,
            file_path=task.file_path,
        )

    response: LLMResponse = await llm.generate_text(prompt)
    if response.prompt_tokens or response.completion_tokens:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(
            response.prompt_tokens
        )
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(
            response.completion_tokens
        )
    result = _parse_response(response.content)

    logger.info(
        "Generated %d chars of %s code for %s. Reasoning: %s",
        len(result.code), task.language, task.file_path, result.reasoning[:80],
    )
    return result


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
