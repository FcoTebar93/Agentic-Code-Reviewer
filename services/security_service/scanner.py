"""
Security scanner: static analysis of aggregated PR code.

Design: pure regex-based, no LLM calls.
Rationale: security checks must be deterministic and reproducible.
LLM adds non-determinism that is unacceptable for a security gate.
Each violation maps to a named rule for auditability.
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
        files: list of dicts with keys: file_path, code, language.

    Returns:
        ScanResult with approved=True only if zero violations found.
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

    if approved:
        reasoning = (
            f"Scanned {files_scanned} file(s) against {rules_checked} security rules "
            "(hardcoded secrets, dangerous functions, path traversal, shell/SQL injection). "
            "No violations found. Code is safe for repository publication."
        )
        logger.info("Security scan PASSED (%d files scanned)", files_scanned)
    else:
        reasoning = (
            f"Scanned {files_scanned} file(s) against {rules_checked} security rules. "
            f"Found {len(all_violations)} violation(s). "
            "Publication blocked until violations are resolved."
        )
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


def _scan_single_file(file_path: str, code: str) -> list[str]:
    violations = []
    for rule_name, pattern in SECURITY_RULES:
        if pattern.search(code):
            violations.append(
                f"[{file_path}] Rule '{rule_name}': pattern matched"
            )
            logger.debug("Rule %s triggered in %s", rule_name, file_path)
    return violations
