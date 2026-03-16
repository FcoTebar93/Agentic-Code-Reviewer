from __future__ import annotations


CODE_GEN_PROMPT = """You are an expert {language} developer working inside a multi-agent pipeline.

Downstream in this pipeline there are:
- A QA reviewer agent that will re-evaluate your changes using static analysis tools (ruff, ESLint, Bandit, Semgrep, javac, etc.).
- CI tools that can run tests and linters (for example `run_tests` and `run_lints` commands) and auto-formatters (like `black` for Python).

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

Your code MUST be:
- Lint-clean as far as reasonably possible (avoid patterns that will trigger ruff/ESLint or security tools like Bandit/Semgrep).
- Idiomatically formatted for the language (assume a formatter such as black/prettier may run, so avoid fighting its conventions).

SHORT-TERM MEMORY:
{short_term_memory}

If the target file clearly belongs to a known framework, adapt your implementation:
- For FastAPI (Python): implement endpoints with proper Pydantic models, status codes, dependency injection,
  and robust error handling; keep business logic out of the FastAPI layer when posible.
- For Django views (Python): respect URL/view conventions, use forms/serializers where appropriate
  and avoid duplicating ORM logic.
- For React/Next.js components (JS/TS): create idiomatic function components, keep state minimal,
  use hooks appropriately and avoid heavy logic inside JSX; prefer small, focused components.

Instructions:
1. Start your response by explicitly referencing and responding to the planner's reasoning above.
2. Explain the implementation approach you chose and why, addressing any decisions the planner raised.
3. Write complete, production-quality {language} code.
4. Make sure the code would pass basic linters and security checks for this language (naming, unused variables, unreachable code, dangerous APIs, missing validation, etc.).
5. If the SHORT-TERM MEMORY mentions previous QA or security failures, explicitly address each listed issue
   and adjust your implementation so it complies with the QA and security rules referenced there.
6. If this task was created as a QA retry or patch, haz solo los cambios mínimos necesarios para corregir
   los problemas indicados, manteniendo intacto el resto del archivo siempre que sea posible.

Format your response EXACTLY as:
REASONING: <2-4 sentences that (a) acknowledge the planner's analysis, (b) explain your implementation decisions>
CODE:
<the complete code, no markdown fences>
"""


CODE_GEN_PROMPT_NO_PRIOR = """You are an expert {language} developer.

Write production-quality code for the following task:
{description}

The code should be written for file: {file_path}

Downstream in this pipeline there are QA and CI agents that will:
- Run language-appropriate linters and security tools (ruff, ESLint, Bandit, Semgrep, javac, etc.).
- Optionally run tests and auto-formatters (e.g. black/prettier).

Your code must therefore be:
- Correct and robust (with error handling and validation where appropriate).
- Reasonably lint-clean and formatted according to common conventions for {language}.

First explain your reasoning: what approach you chose, why, and any trade-offs considered.
Then provide the complete code.

Format your response EXACTLY as:
REASONING: <your design reasoning in 2-3 sentences>
CODE:
<the complete code, no markdown fences>
"""

