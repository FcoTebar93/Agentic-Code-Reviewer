"""
QA review logic: static pattern analysis + LLM-based code review.

Each QA agent:
1. Reads the developer's reasoning and explicitly responds to it.
2. Performs static and semantic review of the code.
3. Returns REASONING that references the developer's decisions.

This creates a visible inter-agent dialogue: dev explains choices, QA responds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from shared.llm_adapter import LLMProvider, LLMResponse
from shared.observability.metrics import llm_tokens
from shared.policies import rules_for_language, Rule
from services.qa_service.config import DANGEROUS_PATTERNS
from services.qa_service.prompts import QA_REVIEW_PROMPT, QA_REVIEW_PROMPT_NO_PRIOR

logger = logging.getLogger(__name__)

@dataclass
class ReviewResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    reasoning: str = ""
    structured_feedback: dict | None = None


SERVICE_NAME = "qa_service"


async def review_code(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
) -> tuple[ReviewResult, int, int]:
    """
    Run static checks then LLM review. Returns (result, prompt_tokens, completion_tokens).
    """
    static_issues = _static_check(code)
    if static_issues:
        reasoning = (
            f"Static analysis detected {len(static_issues)} dangerous pattern(s) "
            "before LLM review. Immediate rejection applied regardless of "
            "developer's stated rationale."
        )
        logger.warning("Static check FAILED for %s: %s", file_path, static_issues)
        return (
            ReviewResult(
                passed=False,
                issues=static_issues,
                reasoning=reasoning,
                structured_feedback={
                    "functionality": [],
                    "style": [],
                    "security": [
                        {
                            "severity": "critical",
                            "title": "Patrones estáticos peligrosos detectados antes del QA LLM",
                            "details": "; ".join(static_issues),
                        }
                    ],
                },
            ),
            0,
            0,
        )

    return await _llm_review(
        llm,
        code,
        file_path,
        language,
        task_description,
        dev_reasoning,
        short_term_memory=short_term_memory,
        static_analysis_report=static_analysis_report,
    )


def _static_check(code: str) -> list[str]:
    """Detect known dangerous patterns. O(n*m) but code is small."""
    issues: list[str] = []
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            issues.append(f"Dangerous pattern detected: `{pattern}`")

    suspicious_snippets = _heuristic_suspicious_snippets(code)
    issues.extend(suspicious_snippets)
    return issues


def _heuristic_suspicious_snippets(code: str) -> list[str]:
    """
    Heurística ligera de \"código sospechoso\" independiente de linters:
    - accesos a red,
    - acceso directo a sistema de ficheros,
    - acceso a variables de entorno/secrets.
    Esto NO bloquea por sí solo, pero se adjunta como issue de seguridad de alta prioridad.
    """
    lowered = code.lower()
    findings: list[str] = []

    network_markers = ("requests.", "httpx.", "fetch(", "axios.", "urlopen(")
    if any(m in lowered for m in network_markers):
        findings.append(
            "Suspicious network access detected (HTTP client usage). "
            "Verifica timeouts, validación de entradas y manejo de errores."
        )

    fs_markers = ("open(", "os.remove(", "os.unlink(", "shutil.", "fs.", "pathlib.")
    if any(m in lowered for m in fs_markers):
        findings.append(
            "Suspicious filesystem access detected. Comprueba rutas, permisos y riesgos de path traversal."
        )

    secrets_markers = ("os.environ", "process.env", "secret", "api_key", "password")
    if any(m in lowered for m in secrets_markers):
        findings.append(
            "Possible secrets or environment variable usage detected. "
            "Asegura que no se exponen credenciales ni se registran valores sensibles."
        )

    return findings


async def _llm_review(
    llm: LLMProvider,
    code: str,
    file_path: str,
    language: str,
    task_description: str,
    dev_reasoning: str = "",
    short_term_memory: str = "",
    static_analysis_report: str = "",
) -> tuple[ReviewResult, int, int]:
    qa_rules_block = _build_qa_rules_block(language)

    if dev_reasoning.strip():
        prompt = QA_REVIEW_PROMPT.format(
            language=language,
            file_path=file_path,
            code=code,
            description=task_description,
            dev_reasoning=dev_reasoning,
            short_term_memory=short_term_memory.strip() or "None.",
            static_analysis_report=static_analysis_report.strip()
            or "No static analysis issues or warnings were reported by tools.",
            qa_rules_block=qa_rules_block,
        )
    else:
        prompt = QA_REVIEW_PROMPT_NO_PRIOR.format(
            language=language,
            file_path=file_path,
            code=code,
            description=task_description,
            static_analysis_report=static_analysis_report.strip()
            or "No static analysis issues or warnings were reported by tools.",
            qa_rules_block=qa_rules_block,
        )

    response: LLMResponse = await llm.generate_text(prompt)

    pt = response.prompt_tokens or 0
    ct = response.completion_tokens or 0
    if pt or ct:
        llm_tokens.labels(service=SERVICE_NAME, direction="prompt").inc(pt)
        llm_tokens.labels(service=SERVICE_NAME, direction="completion").inc(ct)

    result = _parse_review_response(response.content)
    return result, pt, ct


def _build_qa_rules_block(language: str) -> str:
    """
    Build the textual QA rules block for the given language, prioritising
    high-severity rules (blocker/error) to keep the prompt focused.
    """
    qa_rules: list[Rule] = rules_for_language(language, category="qa")
    if not qa_rules:
        return "No specific rules."

    important = [r for r in qa_rules if r.severity.value in ("blocker", "error")]
    source = important or qa_rules
    lines = [f"- [{r.id}] ({r.severity.value}): {r.description}" for r in source]
    return "\n".join(lines)


def _parse_review_response(content: str) -> ReviewResult:
    """Parse the structured LLM response into a ReviewResult with reasoning and sections."""
    lines = content.strip().splitlines()
    passed = True
    issues: list[str] = []
    reasoning = ""
    in_issues = False
    current_section: Literal["functionality", "style", "security", "other"] = "other"
    structured: dict[str, list[dict]] = {
        "functionality": [],
        "style": [],
        "security": [],
    }

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("REASONING:"):
            reasoning = stripped[len("REASONING:"):].strip()
            in_issues = False
        elif upper.startswith("VERDICT:"):
            verdict = upper.replace("VERDICT:", "").strip()
            passed = verdict == "PASS"
            in_issues = False
        elif upper.startswith("ISSUES:"):
            in_issues = True
            inline = stripped[len("ISSUES:"):].strip()
            if inline.lower() not in ("none", ""):
                issues.append(inline)
        elif in_issues and stripped.startswith("- "):
            issue = stripped.lstrip("- ").strip()
            if issue.lower() not in ("none", ""):
                issues.append(issue)
                sev = "info"
                category = "other"
                if issue.startswith("[") and "]" in issue:
                    header, _, rest = issue[1:].partition("]")
                    parts = header.split("|", 1)
                    if parts:
                        sev = parts[0].strip().lower() or "info"
                    if len(parts) > 1:
                        category = parts[1].strip().lower() or "other"
                    title = rest.strip() or issue
                else:
                    title = issue

                if "seguridad" in category or "security" in category:
                    current_section = "security"
                elif "funcional" in category or "functional" in category:
                    current_section = "functionality"
                elif "estilo" in category or "style" in category:
                    current_section = "style"
                else:
                    current_section = "other"

                target_key = (
                    current_section
                    if current_section in {"functionality", "style", "security"}
                    else "security" if "sec" in category else "functionality"
                )
                structured.setdefault(target_key, []).append(
                    {
                        "severity": sev,
                        "category": category,
                        "title": title,
                    }
                )

    if not passed and not issues:
        issues.append("LLM reviewer returned FAIL without specific issues")

    logger.info(
        "LLM review result: %s, issues=%d. Reasoning: %s",
        "PASS" if passed else "FAIL",
        len(issues),
        reasoning[:80],
    )
    return ReviewResult(
        passed=passed,
        issues=issues,
        reasoning=reasoning,
        structured_feedback=structured,
    )
