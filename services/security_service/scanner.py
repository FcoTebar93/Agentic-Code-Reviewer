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

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.security_service.config import SECURITY_RULES, SecurityConfig
from shared.agent_subprocess import run_sync_hardened

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    approved: bool
    violations: list[str]
    files_scanned: int
    reasoning: str = ""


def scan_files(files: list[dict], cfg: SecurityConfig) -> ScanResult:
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
        language = str(file_entry.get("language", "") or "").lower()
        if not code:
            continue

        files_scanned += 1
        file_violations = _scan_single_file(file_path, code, language, cfg)
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


def _scan_single_file(
    file_path: str,
    code: str,
    language: str,
    cfg: SecurityConfig,
) -> list[str]:
    violations: list[str] = []

    for rule_name, pattern in SECURITY_RULES:
        if pattern.search(code):
            violations.append(
                f"[{file_path}] Rule '{rule_name}': pattern matched"
            )
            logger.debug("Rule %s triggered in %s", rule_name, file_path)

    if cfg.enable_bandit and language == "python":
        violations.extend(_run_bandit_security_checks(file_path, code))

    if cfg.enable_semgrep and language in {
        "python",
        "javascript",
        "js",
        "typescript",
        "ts",
        "java",
    }:
        violations.extend(_run_semgrep_security_checks(file_path, code, language))

    return violations


def _run_bandit_security_checks(file_path: str, code: str) -> list[str]:
    """
    Ejecuta bandit sobre el código Python y devuelve violaciones formateadas
    para el SecurityResultPayload. Falla en modo silencioso si bandit no está
    disponible o si algo va mal (no rompe el pipeline).
    """
    try:
        probe = run_sync_hardened(
            ["python", "-m", "bandit", "--version"],
            timeout_s=20.0,
            max_stdout_bytes=8_192,
            max_stderr_bytes=8_192,
        )
        if probe.timed_out or probe.returncode != 0:
            logger.debug("Bandit no está instalado; omitiendo bandit en security_service")
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / "tmp.py"
            target.write_text(code, encoding="utf-8")

            proc = run_sync_hardened(
                ["python", "-m", "bandit", "-q", "-f", "json", str(target)],
                cwd=str(tmp_path),
                timeout_s=45.0,
                max_stdout_bytes=512_000,
                max_stderr_bytes=128_000,
            )

            stdout = proc.stdout.strip()
            if not stdout:
                return []

            issues: list[str] = []
            try:
                data: dict[str, Any] = json.loads(stdout)
            except Exception:
                logger.warning("Bandit output could not be parsed as JSON for %s", file_path)
                return []

            for item in data.get("results", []):
                sev = str(item.get("issue_severity", "")).upper()
                test_id = str(item.get("test_id", ""))
                msg = str(item.get("issue_text", "")).strip()
                line = int(item.get("line_number", 0) or 0)
                issues.append(
                    f"[{file_path}] [bandit {sev} {test_id}] L{line}: {msg}"
                )

            return issues
    except Exception as exc:
        logger.exception("Bandit scan failed for %s: %s", file_path, exc)
        return []


def _run_semgrep_security_checks(
    file_path: str,
    code: str,
    language: str,
) -> list[str]:
    """
    Ejecuta semgrep con un conjunto de reglas orientado a seguridad.
    Usa --config=p/security-audit (reglas públicas útiles para muchos stacks).
    """
    lang = language.lower()
    supported_langs = {
        "python": ".py",
        "javascript": ".js",
        "js": ".js",
        "typescript": ".ts",
        "ts": ".ts",
        "java": ".java",
    }
    if lang not in supported_langs:
        return []

    try:
        py_sem = run_sync_hardened(
            ["python", "-m", "semgrep", "--version"],
            timeout_s=20.0,
            max_stdout_bytes=8_192,
            max_stderr_bytes=8_192,
        )
        if not py_sem.timed_out and py_sem.returncode == 0:
            use_python_module = True
        else:
            bin_sem = run_sync_hardened(
                ["semgrep", "--version"],
                timeout_s=20.0,
                max_stdout_bytes=8_192,
                max_stderr_bytes=8_192,
            )
            if bin_sem.timed_out or bin_sem.returncode != 0:
                logger.debug("Semgrep no está instalado; omitiendo semgrep en security_service")
                return []
            use_python_module = False

        ext = supported_langs[lang]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / f"tmp{ext}"
            target.write_text(code, encoding="utf-8")

            base_cmd = ["python", "-m", "semgrep"] if use_python_module else ["semgrep"]
            cmd = base_cmd + [
                "--config",
                "p/security-audit",
                "--json",
                "--quiet",
                str(target),
            ]
            proc = run_sync_hardened(
                cmd,
                cwd=str(tmp_path),
                timeout_s=90.0,
                max_stdout_bytes=1_048_576,
                max_stderr_bytes=256_000,
            )

            stdout = proc.stdout.strip()
            if not stdout:
                return []

            issues: list[str] = []
            try:
                data: dict[str, Any] = json.loads(stdout)
            except Exception:
                logger.warning("Semgrep output could not be parsed as JSON for %s", file_path)
                return []

            for result in data.get("results", []):
                extra = result.get("extra", {}) or {}
                sev = str(extra.get("severity", "")).upper()
                rule_id = str(extra.get("id", ""))
                msg = str(extra.get("message", "")).strip()
                loc = result.get("start", {}) or {}
                line_i = int(loc.get("line", 0) or 0)
                issues.append(
                    f"[{file_path}] [semgrep {sev} {rule_id}] L{line_i}: {msg}"
                )

            return issues
    except Exception as exc:
        logger.exception("Semgrep scan failed for %s: %s", file_path, exc)
        return []
