"""
Security scanner: static analysis of aggregated PR code.

Design: pure regex-based, no LLM calls.
Rationale: security checks must be deterministic and reproducible.
LLM adds non-determinism that is unacceptable for a security gate.
Each violation maps to a named rule for auditability.

Pipeline conclusion:
  The security_service is the last agent in the chain.
  Its reasoning field serves as the final pipeline summary, referencing
  the dev→QA→security reasoning chain for every file in the PR.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from services.security_service.config import SECURITY_RULES

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    approved: bool
    violations: list[str]
    files_scanned: int
    reasoning: str = ""


def scan_files(files: list[dict]) -> ScanResult:
    """
    Scan all files in a PR payload for security violations.

    Args:
        files: list of dicts with keys: file_path, code, language, reasoning.
               The `reasoning` field carries the concatenated dev+QA reasoning
               chain from upstream agents.

    Returns:
        ScanResult whose `reasoning` is the full pipeline conclusion.
    """
    all_violations: list[str] = []
    files_scanned = 0

    for file_entry in files:
        file_path = file_entry.get("file_path", "<unknown>")
        code = file_entry.get("code", "")
        if not code:
            continue

        files_scanned += 1
        file_violations = _scan_single_file(file_path, code)
        all_violations.extend(file_violations)

    approved = len(all_violations) == 0
    rules_checked = len(SECURITY_RULES)

    reasoning = _build_pipeline_conclusion(
        files=files,
        files_scanned=files_scanned,
        rules_checked=rules_checked,
        approved=approved,
        violations=all_violations,
    )

    if approved:
        logger.info("Security scan PASSED (%d files scanned)", files_scanned)
    else:
        logger.warning(
            "Security scan FAILED (%d files, %d violations): %s",
            files_scanned,
            len(all_violations),
            all_violations,
        )

    return ScanResult(
        approved=approved,
        violations=all_violations,
        files_scanned=files_scanned,
        reasoning=reasoning,
    )


def _build_pipeline_conclusion(
    files: list[dict],
    files_scanned: int,
    rules_checked: int,
    approved: bool,
    violations: list[str],
) -> str:
    """
    Build the final pipeline conclusion that references the full reasoning chain.

    This text appears in the HITL approval card and in the event feed as
    the security_service reasoning — it is the last word from the agent pipeline.
    """
    lines: list[str] = ["=== Pipeline Agent Chain ===", ""]

    for f in files:
        if not f.get("code"):
            continue
        file_path = f.get("file_path", "unknown")
        prior_reasoning = (f.get("reasoning") or "").strip()
        if prior_reasoning:
            lines.append(f"📄 {file_path}")
            for chain_line in prior_reasoning.splitlines():
                lines.append(f"   {chain_line}")
            lines.append("")

    lines.append("=== Security Analysis ===")
    lines.append("")
    lines.append(
        f"Scanned {files_scanned} file(s) against {rules_checked} security rules "
        "(hardcoded secrets, dangerous functions, path traversal, shell/SQL injection)."
    )

    if approved:
        lines.append("")
        lines.append(
            "✅ CONCLUSION: All files passed the full agent pipeline "
            "(Planning → Development → QA → Security). "
            "No violations found. Code is approved for human review and deployment."
        )
    else:
        lines.append("")
        lines.append(
            f"❌ CONCLUSION: {len(violations)} security violation(s) detected. "
            "Deployment blocked pending remediation:"
        )
        for v in violations:
            lines.append(f"   • {v}")

    return "\n".join(lines)


def _scan_single_file(file_path: str, code: str) -> list[str]:
    violations = []
    for rule_name, pattern in SECURITY_RULES:
        if pattern.search(code):
            violations.append(
                f"[{file_path}] Rule '{rule_name}': pattern matched"
            )
            logger.debug("Rule %s triggered in %s", rule_name, file_path)
    return violations
