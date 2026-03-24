from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx
from pydantic import Field

from shared.agent_subprocess import run_sync_hardened
from shared.tools import (
    ToolInput,
    ToolDefinition,
    ToolRegistry,
)


REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/workspace")).resolve()
MEMORY_SERVICE_URL = os.environ.get("MEMORY_SERVICE_URL", "http://memory_service:8000")


def _safe_join(path: str) -> Path:
    p = (REPO_ROOT / path).resolve()
    if not str(p).startswith(str(REPO_ROOT)):
        raise ValueError("Path escapes repository root")
    return p


class LintInput(ToolInput):
    language: str = Field(
        default="python",
        description=(
            "Language of the code to analyse. Python is fully supported; "
            "JavaScript/TypeScript/Java are supported via external tools when available."
        ),
    )
    code: str = Field(
        description="Código fuente completo a lintar",
    )
    file_path: str = Field(
        default="tmp.py",
        description="Ruta lógica del archivo (para mensajes de error)",
    )


class ReadFileInput(ToolInput):
    path: str = Field(
        description="Ruta relativa al repo del archivo a leer",
    )
    max_bytes: int = Field(
        default=32_000,
        ge=1,
        le=256_000,
        description="Máximo de bytes a devolver del archivo",
    )


def read_file_tool(args: ReadFileInput) -> dict[str, Any]:
    target = _safe_join(args.path)
    if not target.exists() or not target.is_file():
        return {"exists": False, "path": str(target), "content": "", "truncated": False}

    data = target.read_bytes()
    truncated = len(data) > args.max_bytes
    if truncated:
        data = data[: args.max_bytes]

    text = data.decode("utf-8", errors="replace")
    return {
        "exists": True,
        "path": str(target),
        "content": text,
        "truncated": truncated,
        "size_bytes": target.stat().st_size,
    }


class SearchInRepoInput(ToolInput):
    pattern: str = Field(
        description="Patrón de texto o regex a buscar en el repo",
    )
    directory: str = Field(
        default=".",
        description="Directorio base relativo al repo donde buscar",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=2000,
        description="Máximo de coincidencias a devolver",
    )


class QueryEventsInput(ToolInput):
    event_type: str | None = Field(
        default=None,
        description="Tipo de evento (por ejemplo 'qa.failed', 'plan.created')",
    )
    plan_id: str | None = Field(
        default=None,
        description="Filtrar por plan_id concreto si se desea",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Máximo de eventos a devolver",
    )


class FailurePatternsInput(ToolInput):
    module_prefix: str | None = Field(
        default=None,
        description="Prefijo de módulo/carpeta para filtrar (por ejemplo 'services/dev_service')",
    )
    limit: int = Field(
        default=200,
        ge=10,
        le=1000,
        description="Máximo de eventos base a considerar al construir patrones",
    )


class FormatCodeInput(ToolInput):
    language: str = Field(
        default="python",
        description=(
            "Lenguaje del código a formatear. "
            "Actualmente soportado: python, javascript, typescript."
        ),
    )
    code: str = Field(
        description="Código fuente completo a formatear",
    )
    file_path: str = Field(
        default="tmp.py",
        description="Ruta lógica del archivo (para mensajes y heurísticas del formateador)",
    )


def python_lint_tool(args: LintInput) -> dict[str, Any]:
    """
    Ejecuta ruff sobre el código proporcionado y devuelve una lista estructurada
    de issues. Solo soporta lenguaje 'python'.
    """
    if args.language.lower() != "python":
        return {
            "supported": False,
            "issues": [],
            "note": "python_lint_tool solo soporta language='python' por ahora",
        }

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / (args.file_path or "tmp.py")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.code, encoding="utf-8")

            proc = run_sync_hardened(
                ["python", "-m", "ruff", "check", str(target)],
                cwd=str(tmp_path),
                timeout_s=15.0,
                max_stdout_bytes=256_000,
                max_stderr_bytes=64_000,
            )
            issues: list[dict[str, Any]] = []
            for line in (proc.stdout or "").splitlines():
                parts = line.split(":", 3)
                if len(parts) < 4:
                    continue
                _, line_s, col_s, rest = parts
                try:
                    line_i = int(line_s)
                    col_i = int(col_s)
                except ValueError:
                    continue
                rest = rest.lstrip()
                if " " in rest:
                    code, msg = rest.split(" ", 1)
                else:
                    code, msg = rest, ""
                issues.append(
                    {
                        "line": line_i,
                        "column": col_i,
                        "code": code.strip(),
                        "message": msg.strip(),
                    }
                )

            return {
                "supported": True,
                "issues": issues,
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-2000:],
            }
    except Exception as exc:
        return {
            "supported": True,
            "issues": [],
            "exit_code": -1,
            "stdout": "",
            "stderr": f"python_lint_tool failed: {exc}",
        }


def search_in_repo_tool(args: SearchInRepoInput) -> dict[str, Any]:
    base_dir = _safe_join(args.directory)
    if not base_dir.exists() or not base_dir.is_dir():
        return {"directory": str(base_dir), "matches": []}

    try:
        pattern = re.compile(args.pattern)
    except re.error:
        pattern = re.compile(re.escape(args.pattern))

    matches: list[dict[str, Any]] = []
    for path in base_dir.rglob("*"):
        if len(matches) >= args.max_results:
            break
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                try:
                    rel = path.relative_to(REPO_ROOT)
                except ValueError:
                    rel = path
                matches.append(
                    {
                        "file": str(rel),
                        "line": i,
                        "snippet": line.strip(),
                    }
                )
                if len(matches) >= args.max_results:
                    break

    return {
        "directory": str(base_dir),
        "pattern": args.pattern,
        "matches": matches,
    }


async def query_events_tool(args: QueryEventsInput) -> dict[str, Any]:
    """
    Consulta eventos recientes al memory_service (fachada HTTP sobre PostgreSQL).
    """
    params: dict[str, Any] = {"limit": args.limit}
    if args.event_type:
        params["event_type"] = args.event_type
    if args.plan_id:
        params["plan_id"] = args.plan_id

    async with httpx.AsyncClient(base_url=MEMORY_SERVICE_URL, timeout=10.0) as client:
        resp = await client.get("/events", params=params)
        resp.raise_for_status()
        data = resp.json()
    return {"events": data}


async def failure_patterns_tool(args: FailurePatternsInput) -> dict[str, Any]:
    """
    Consulta los patrones agregados de fallos históricos desde memory_service.
    """
    async with httpx.AsyncClient(base_url=MEMORY_SERVICE_URL, timeout=10.0) as client:
        resp = await client.get(
            "/patterns/failures",
            params={"limit": args.limit},
        )
        resp.raise_for_status()
        data = resp.json()

    patterns = data.get("patterns") or []
    if args.module_prefix:
        prefix = args.module_prefix.replace("\\", "/").lower()
        patterns = [
            p
            for p in patterns
            if isinstance(p, dict)
            and str(p.get("module", "")).replace("\\", "/").lower().startswith(prefix)
        ]
    return {"patterns": patterns}


def js_ts_lint_tool(args: LintInput) -> dict[str, Any]:
    """
    Ejecuta ESLint sobre código JS/TS en un archivo temporal.
    Requiere que eslint esté disponible (por ejemplo vía `npx eslint`).
    """
    lang = args.language.lower()
    if lang not in {"javascript", "js", "typescript", "ts"}:
        return {
            "supported": False,
            "issues": [],
            "note": "js_ts_lint_tool solo soporta JavaScript/TypeScript",
        }

    try:
        probe = run_sync_hardened(
            ["npx", "eslint", "--version"],
            timeout_s=30.0,
            max_stdout_bytes=8_192,
            max_stderr_bytes=8_192,
        )
        if probe.timed_out or probe.returncode != 0:
            return {
                "supported": False,
                "issues": [],
                "note": "eslint no está disponible (npx eslint); omitiendo lint JS/TS",
            }

        ext = ".ts" if lang in {"typescript", "ts"} else ".js"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / (args.file_path or f"tmp{ext}")
            if not str(target).endswith(ext):
                target = target.with_suffix(ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.code, encoding="utf-8")

            proc = run_sync_hardened(
                ["npx", "eslint", "--format", "json", str(target)],
                cwd=str(tmp_path),
                timeout_s=30.0,
                max_stdout_bytes=512_000,
                max_stderr_bytes=128_000,
            )

            issues: list[dict[str, Any]] = []
            stdout = proc.stdout.strip()
            if stdout:
                try:
                    data = json.loads(stdout)
                    for file_report in data:
                        for msg in file_report.get("messages", []):
                            issues.append(
                                {
                                    "line": int(msg.get("line", 0) or 0),
                                    "column": int(msg.get("column", 0) or 0),
                                    "severity": int(msg.get("severity", 0) or 0),
                                    "rule_id": msg.get("ruleId", "") or "",
                                    "message": str(msg.get("message", "")).strip(),
                                }
                            )
                except Exception:
                    return {
                        "supported": True,
                        "issues": [],
                        "exit_code": proc.returncode,
                        "stdout": stdout[-4000:],
                        "stderr": proc.stderr[-2000:],
                        "note": "eslint output could not be parsed as JSON",
                    }

            return {
                "supported": True,
                "issues": issues,
                "exit_code": proc.returncode,
                "stdout": stdout[-4000:],
                "stderr": proc.stderr[-2000:],
            }
    except Exception as exc:
        return {
            "supported": True,
            "issues": [],
            "exit_code": -1,
            "stdout": "",
            "stderr": f"js_ts_lint_tool failed: {exc}",
        }


def java_lint_tool(args: LintInput) -> dict[str, Any]:
    """
    Ejecuta javac sobre el código proporcionado para detectar errores de compilación.
    No realiza análisis profundo, pero ayuda a detectar problemas básicos.
    """
    if args.language.lower() != "java":
        return {
            "supported": False,
            "issues": [],
            "note": "java_lint_tool solo soporta language='java'",
        }

    try:
        if not shutil.which("javac"):
            return {
                "supported": False,
                "issues": [],
                "note": "javac no está disponible en PATH; omitiendo lint Java",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / (args.file_path or "Tmp.java")
            if not str(target).endswith(".java"):
                target = target.with_suffix(".java")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.code, encoding="utf-8")

            proc = run_sync_hardened(
                ["javac", str(target)],
                cwd=str(tmp_path),
                timeout_s=30.0,
                max_stdout_bytes=256_000,
                max_stderr_bytes=256_000,
            )

            issues: list[dict[str, Any]] = []
            stderr = proc.stderr or ""
            for line in stderr.splitlines():
                parts = line.split(":", 3)
                if len(parts) < 4:
                    continue
                _, line_s, _col_s, msg = parts
                try:
                    line_i = int(line_s)
                except ValueError:
                    continue
                issues.append(
                    {
                        "line": line_i,
                        "column": 0,
                        "severity": "ERROR",
                        "code": "javac",
                        "message": msg.strip(),
                    }
                )

            return {
                "supported": True,
                "issues": issues,
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": stderr[-4000:],
            }
    except Exception as exc:
        return {
            "supported": True,
            "issues": [],
            "exit_code": -1,
            "stdout": "",
            "stderr": f"java_lint_tool failed: {exc}",
        }


def semgrep_tool(args: LintInput) -> dict[str, Any]:
    """
    Ejecuta semgrep como analizador multi-lenguaje sobre el archivo temporal.
    Usa --config=p/ci para una configuración general de buenas prácticas.
    """
    lang = args.language.lower()
    supported_langs = {
        "python": ".py",
        "javascript": ".js",
        "js": ".js",
        "typescript": ".ts",
        "ts": ".ts",
        "java": ".java",
    }
    if lang not in supported_langs:
        return {
            "supported": False,
            "issues": [],
            "note": f"semgrep_tool no soporta language='{args.language}' todavía",
        }

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
                return {
                    "supported": False,
                    "issues": [],
                    "note": "semgrep no está instalado; omitiendo análisis semgrep",
                }
            use_python_module = False

        ext = supported_langs[lang]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / (args.file_path or f"tmp{ext}")
            if not str(target).endswith(ext):
                target = target.with_suffix(ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.code, encoding="utf-8")

            base_cmd = ["python", "-m", "semgrep"] if use_python_module else ["semgrep"]
            cmd = base_cmd + [
                "--config",
                "p/ci",
                "--json",
                "--quiet",
                str(target),
            ]
            proc = run_sync_hardened(
                cmd,
                cwd=str(tmp_path),
                timeout_s=60.0,
                max_stdout_bytes=1_048_576,
                max_stderr_bytes=256_000,
            )

            issues: list[dict[str, Any]] = []
            stdout = proc.stdout.strip()
            if stdout:
                try:
                    data = json.loads(stdout)
                    for result in data.get("results", []):
                        extra = result.get("extra", {}) or {}
                        sev = str(extra.get("severity", "")).upper()
                        rule_id = str(extra.get("id", ""))
                        msg = str(extra.get("message", "")).strip()
                        loc = result.get("start", {}) or {}
                        line_i = int(loc.get("line", 0) or 0)
                        issues.append(
                            {
                                "line": line_i,
                                "column": 0,
                                "severity": sev,
                                "code": rule_id,
                                "message": msg,
                            }
                        )
                except Exception:
                    return {
                        "supported": True,
                        "issues": [],
                        "exit_code": proc.returncode,
                        "stdout": stdout[-4000:],
                        "stderr": proc.stderr[-2000:],
                        "note": "semgrep output could not be parsed as JSON",
                    }

            return {
                "supported": True,
                "issues": issues,
                "exit_code": proc.returncode,
                "stdout": stdout[-4000:],
                "stderr": proc.stderr[-2000:],
            }
    except Exception as exc:
        return {
            "supported": True,
            "issues": [],
            "exit_code": -1,
            "stdout": "",
            "stderr": f"semgrep_tool failed: {exc}",
        }


def python_security_tool(args: LintInput) -> dict[str, Any]:
    """
    Ejecuta bandit sobre el código proporcionado y devuelve issues de seguridad estructurados.
    Solo soporta lenguaje 'python'. Si bandit no está instalado, se marca como unsupported.
    """
    if args.language.lower() != "python":
        return {
            "supported": False,
            "issues": [],
            "note": "python_security_tool solo soporta language='python' por ahora",
        }

    try:
        probe = run_sync_hardened(
            ["python", "-m", "bandit", "--version"],
            timeout_s=20.0,
            max_stdout_bytes=8_192,
            max_stderr_bytes=8_192,
        )
        if probe.timed_out or probe.returncode != 0:
            return {
                "supported": False,
                "issues": [],
                "note": "bandit no está instalado en el entorno; omitiendo análisis de seguridad",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / (args.file_path or "tmp.py")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.code, encoding="utf-8")

            proc = run_sync_hardened(
                ["python", "-m", "bandit", "-q", "-f", "json", str(target)],
                cwd=str(tmp_path),
                timeout_s=30.0,
                max_stdout_bytes=512_000,
                max_stderr_bytes=128_000,
            )

            issues: list[dict[str, Any]] = []
            stdout = proc.stdout.strip()
            if stdout:
                try:
                    data = json.loads(stdout)
                    for item in data.get("results", []):
                        issues.append(
                            {
                                "line": int(item.get("line_number", 0) or 0),
                                "column": 0,
                                "severity": str(item.get("issue_severity", "")).upper(),
                                "code": str(item.get("test_id", "")),
                                "message": str(item.get("issue_text", "")).strip(),
                            }
                        )
                except Exception:
                    return {
                        "supported": True,
                        "issues": [],
                        "exit_code": proc.returncode,
                        "stdout": stdout[-4000:],
                        "stderr": proc.stderr[-2000:],
                        "note": "bandit output could not be parsed as JSON",
                    }

            return {
                "supported": True,
                "issues": issues,
                "exit_code": proc.returncode,
                "stdout": stdout[-4000:],
                "stderr": proc.stderr[-2000:],
            }
    except Exception as exc:
        return {
            "supported": True,
            "issues": [],
            "exit_code": -1,
            "stdout": "",
            "stderr": f"python_security_tool failed: {exc}",
        }


def format_code_tool(args: FormatCodeInput) -> dict[str, Any]:
    """
    Formatea código en un lenguaje dado usando herramientas estándar del entorno.

    Soporta:
    - Python vía 'python -m black'
    - JavaScript/TypeScript vía 'npx prettier' (cuando está disponible)
    """
    lang = (args.language or "python").lower()

    if lang in {"python", "py"}:
        try:
            probe = run_sync_hardened(
                ["python", "-m", "black", "--version"],
                timeout_s=15.0,
                max_stdout_bytes=8_192,
                max_stderr_bytes=8_192,
            )
            if probe.timed_out or probe.returncode != 0:
                return {
                    "supported": False,
                    "language": args.language,
                    "formatted_code": args.code,
                    "note": "black no está instalado; se omite el formateo automático para Python",
                }

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                target = tmp_path / (args.file_path or "tmp.py")
                if not str(target).endswith(".py"):
                    target = target.with_suffix(".py")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(args.code, encoding="utf-8")

                proc = run_sync_hardened(
                    ["python", "-m", "black", str(target)],
                    cwd=str(tmp_path),
                    timeout_s=25.0,
                    max_stdout_bytes=32_768,
                    max_stderr_bytes=32_768,
                )

                formatted = target.read_text(encoding="utf-8", errors="replace")
                return {
                    "supported": True,
                    "language": "python",
                    "formatted_code": formatted,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[-4000:],
                    "stderr": proc.stderr[-2000:],
                }
        except Exception as exc:
            return {
                "supported": True,
                "language": "python",
                "formatted_code": args.code,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"format_code_tool (python) failed: {exc}",
            }

    if lang in {"javascript", "js", "typescript", "ts"}:
        try:
            probe = run_sync_hardened(
                ["npx", "prettier", "--version"],
                timeout_s=30.0,
                max_stdout_bytes=8_192,
                max_stderr_bytes=8_192,
            )
            if probe.timed_out or probe.returncode != 0:
                return {
                    "supported": False,
                    "language": args.language,
                    "formatted_code": args.code,
                    "note": "prettier (npx prettier) no está disponible; se omite el formateo automático para JS/TS",
                }

            ext = ".ts" if lang in {"typescript", "ts"} else ".js"
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                target = tmp_path / (args.file_path or f"tmp{ext}")
                if not str(target).endswith(ext):
                    target = target.with_suffix(ext)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(args.code, encoding="utf-8")

                proc = run_sync_hardened(
                    [
                        "npx",
                        "prettier",
                        "--write",
                        str(target),
                    ],
                    cwd=str(tmp_path),
                    timeout_s=45.0,
                    max_stdout_bytes=32_768,
                    max_stderr_bytes=32_768,
                )

                formatted = target.read_text(encoding="utf-8", errors="replace")
                return {
                    "supported": True,
                    "language": "typescript" if ext == ".ts" else "javascript",
                    "formatted_code": formatted,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[-4000:],
                    "stderr": proc.stderr[-2000:],
                }
        except Exception as exc:
            return {
                "supported": True,
                "language": args.language,
                "formatted_code": args.code,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"format_code_tool (js/ts) failed: {exc}",
            }

    return {
        "supported": False,
        "language": args.language,
        "formatted_code": args.code,
        "note": (
            "Formateo automático solo soportado para Python (black) y "
            "JavaScript/TypeScript (prettier) por ahora"
        ),
    }


def build_qa_tool_registry() -> ToolRegistry:
    """
    Construct a ToolRegistry pre-populated with tools useful for qa_service.
    """
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="python_lint",
            description="Ejecutar ruff sobre código Python y devolver issues estructurados",
            input_model=LintInput,
            func=python_lint_tool,
            timeout_s=15.0,
            max_retries=0,
            sandboxed=True,
            tags=["lint", "python", "static_analysis"],
        )
    )

    registry.register(
        ToolDefinition(
            name="python_security_scan",
            description="Ejecutar bandit sobre código Python y devolver issues de seguridad estructurados",
            input_model=LintInput,
            func=python_security_tool,
            timeout_s=30.0,
            max_retries=0,
            sandboxed=True,
            tags=["security", "python", "static_analysis"],
        )
    )

    registry.register(
        ToolDefinition(
            name="js_ts_lint",
            description="Ejecutar ESLint sobre código JavaScript/TypeScript en un archivo temporal",
            input_model=LintInput,
            func=js_ts_lint_tool,
            timeout_s=30.0,
            max_retries=0,
            sandboxed=True,
            tags=["lint", "javascript", "typescript", "static_analysis"],
        )
    )

    registry.register(
        ToolDefinition(
            name="java_lint",
            description="Ejecutar javac sobre código Java para detectar errores básicos de compilación",
            input_model=LintInput,
            func=java_lint_tool,
            timeout_s=30.0,
            max_retries=0,
            sandboxed=True,
            tags=["lint", "java", "static_analysis"],
        )
    )

    registry.register(
        ToolDefinition(
            name="semgrep_scan",
            description="Ejecutar semgrep como analizador multi-lenguaje usando config p/ci",
            input_model=LintInput,
            func=semgrep_tool,
            timeout_s=60.0,
            max_retries=0,
            sandboxed=True,
            tags=["security", "static_analysis", "multi_language"],
        )
    )

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Leer un archivo de texto del repositorio (solo lectura, rutas relativas al repo)",
            input_model=ReadFileInput,
            func=read_file_tool,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["repo", "read"],
        )
    )

    registry.register(
        ToolDefinition(
            name="search_in_repo",
            description="Buscar un patrón de texto/regex en los archivos del repositorio",
            input_model=SearchInRepoInput,
            func=search_in_repo_tool,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["search", "repo"],
        )
    )

    registry.register(
        ToolDefinition(
            name="query_events",
            description="Consultar eventos recientes del memory_service (por tipo y/o plan_id)",
            input_model=QueryEventsInput,
            func=query_events_tool,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["memory", "events"],
        )
    )

    registry.register(
        ToolDefinition(
            name="failure_patterns",
            description="Consultar patrones históricos de fallos (qa.failed, security.blocked) agregados por módulo",
            input_model=FailurePatternsInput,
            func=failure_patterns_tool,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["memory", "patterns"],
        )
    )

    registry.register(
        ToolDefinition(
            name="format_code",
            description=(
                "Formatear código fuente (actualmente solo Python) usando black. "
                "Devuelve el código formateado sin modificar archivos en disco."
            ),
            input_model=FormatCodeInput,
            func=format_code_tool,
            timeout_s=30.0,
            max_retries=0,
            sandboxed=True,
            tags=["format", "style"],
        )
    )

    return registry

