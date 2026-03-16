from __future__ import annotations

import asyncio
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pydantic import Field

from shared.tools import (
    ToolInput,
    ToolDefinition,
    ToolRegistry,
    ToolExecutionResult,
)


REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/workspace")).resolve()


class ReadFileInput(ToolInput):
    path: str = Field(
        description="Ruta relativa al repo del archivo a leer",
        examples=["services/dev_service/main.py"],
    )
    max_bytes: int = Field(
        default=32_000,
        ge=1,
        le=256_000,
        description="Máximo de bytes a devolver del archivo",
    )


class ListProjectFilesInput(ToolInput):
    directory: str = Field(
        default=".",
        description="Directorio base relativo al repo",
        examples=["services/dev_service", "frontend/src"],
    )
    pattern: str = Field(
        default="*.py",
        description="Patrón de glob (por ejemplo *.py, *.tsx)",
    )
    max_results: int = Field(
        default=200,
        ge=1,
        le=2000,
        description="Máximo de rutas a devolver",
    )


class RunTestsInput(ToolInput):
    command: str = Field(
        default="pytest",
        description="Comando de tests a ejecutar (relativo al repo)",
        examples=["pytest", "npm test", "pytest services/dev_service"],
    )
    timeout_s: float = Field(
        default=120.0,
        ge=1.0,
        le=600.0,
        description="Timeout máximo para la ejecución de los tests",
    )


class RunLintsInput(ToolInput):
    command: str = Field(
        default="ruff .",
        description=(
            "Comando de linting a ejecutar (relativo al repo), por ejemplo "
            "'ruff .', 'npm run lint' o 'npx eslint .'."
        ),
        examples=["ruff .", "npm run lint"],
    )
    timeout_s: float = Field(
        default=180.0,
        ge=1.0,
        le=600.0,
        description="Timeout máximo para la ejecución del linter",
    )


class SearchInRepoInput(ToolInput):
    pattern: str = Field(
        description="Patrón de texto o regex a buscar en el repo",
        examples=["def my_function", "useUserStore"],
    )
    directory: str = Field(
        default=".",
        description="Directorio base relativo al repo donde buscar",
        examples=["services/dev_service", "frontend/src"],
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=2000,
        description="Máximo de coincidencias a devolver",
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


def _safe_join(path: str) -> Path:
    """Join a user-provided path to REPO_ROOT, preventing escapes."""
    p = (REPO_ROOT / path).resolve()
    if not str(p).startswith(str(REPO_ROOT)):
        raise ValueError("Path escapes repository root")
    return p


def read_file_tool(args: ReadFileInput) -> dict[str, Any]:
    target = _safe_join(args.path)
    if not target.exists() or not target.is_file():
        return {"exists": False, "path": str(target), "content": "", "truncated": False}

    data = target.read_bytes()
    truncated = len(data) > args.max_bytes
    if truncated:
        data = data[: args.max_bytes]

    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = data.decode("utf-8", errors="replace")

    return {
        "exists": True,
        "path": str(target),
        "content": text,
        "truncated": truncated,
        "size_bytes": target.stat().st_size,
    }


def list_project_files_tool(args: ListProjectFilesInput) -> dict[str, Any]:
    base_dir = _safe_join(args.directory)
    if not base_dir.exists() or not base_dir.is_dir():
        return {"directory": str(base_dir), "files": []}

    matches: list[str] = []
    for path in base_dir.rglob(args.pattern):
        if len(matches) >= args.max_results:
            break
        if path.is_file():
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path
            matches.append(str(rel))

    return {"directory": str(base_dir), "pattern": args.pattern, "files": matches}


def _search_in_file(
    path: Path,
    pattern: re.Pattern,
    max_results: int,
    matches: list[dict[str, Any]],
) -> None:
    if len(matches) >= max_results:
        return
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
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
            if len(matches) >= max_results:
                break


def search_in_repo_tool(args: SearchInRepoInput) -> dict[str, Any]:
    """
    Buscar un patrón de texto/regex en los archivos del repositorio.
    Útil para localizar usos de funciones, clases o rutas antes de editar código.
    """
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
        _search_in_file(path, pattern, args.max_results, matches)

    return {
        "directory": str(base_dir),
        "pattern": args.pattern,
        "matches": matches,
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
            try:
                subprocess.run(
                    ["python", "-m", "black", "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except Exception:
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

                proc = subprocess.run(
                    ["python", "-m", "black", str(target)],
                    cwd=str(tmp_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
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
            try:
                subprocess.run(
                    ["npx", "prettier", "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except Exception:
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

                proc = subprocess.run(
                    [
                        "npx",
                        "prettier",
                        "--write",
                        str(target),
                    ],
                    cwd=str(tmp_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
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


async def run_tests_tool(args: RunTestsInput) -> dict[str, Any]:
    """
    Ejecuta un comando de tests dentro del repo de forma controlada.

    Importante: este tool está pensado para ser invocado de forma explícita
    por el agente, no en cada tarea, ya que puede ser costoso.
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            args.command,
            cwd=str(REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=args.timeout_s
            )
            exit_code = proc.returncode
            timed_out = False
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            exit_code = -1
            timed_out = True

        return {
            "command": args.command,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout": (stdout or b"").decode("utf-8", errors="replace")[-8000:],
            "stderr": (stderr or b"").decode("utf-8", errors="replace")[-8000:],
        }
    except Exception as exc:
        return {
            "command": args.command,
            "exit_code": -1,
            "timed_out": False,
            "stdout": "",
            "stderr": f"run_tests_tool failed: {exc}",
        }


async def run_lints_tool(args: RunLintsInput) -> dict[str, Any]:
    """
    Ejecuta un comando de linting dentro del repo de forma controlada.

    Pensado para comandos como 'ruff .', 'npm run lint' o 'npx eslint .'.
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            args.command,
            cwd=str(REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=args.timeout_s
            )
            exit_code = proc.returncode
            timed_out = False
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            exit_code = -1
            timed_out = True

        return {
            "command": args.command,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout": (stdout or b"").decode("utf-8", errors="replace")[-8000:],
            "stderr": (stderr or b"").decode("utf-8", errors="replace")[-8000:],
        }
    except Exception as exc:
        return {
            "command": args.command,
            "exit_code": -1,
            "timed_out": False,
            "stdout": "",
            "stderr": f"run_lints_tool failed: {exc}",
        }


def build_dev_tool_registry() -> ToolRegistry:
    """
    Construct a ToolRegistry pre-populated with tools useful for dev_service.
    """
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Leer el contenido actual de un archivo del repositorio",
            input_model=ReadFileInput,
            func=read_file_tool,
            timeout_s=2.0,
            max_retries=0,
            sandboxed=True,
            tags=["filesystem", "read"],
        )
    )

    registry.register(
        ToolDefinition(
            name="list_project_files",
            description="Listar archivos del proyecto que coinciden con un patrón dado",
            input_model=ListProjectFilesInput,
            func=list_project_files_tool,
            timeout_s=3.0,
            max_retries=0,
            sandboxed=True,
            tags=["filesystem", "discover"],
        )
    )

    registry.register(
        ToolDefinition(
            name="run_tests",
            description="Ejecutar la suite de tests del proyecto o un comando de tests concreto",
            input_model=RunTestsInput,
            func=run_tests_tool,
            timeout_s=600.0,
            max_retries=0,
            sandboxed=False,
            tags=["tests", "ci"],
        )
    )

    registry.register(
        ToolDefinition(
            name="run_lints",
            description=(
                "Ejecutar un comando de linting (ruff, eslint, npm run lint, etc.) "
                "sobre el repositorio"
            ),
            input_model=RunLintsInput,
            func=run_lints_tool,
            timeout_s=600.0,
            max_retries=0,
            sandboxed=False,
            tags=["lint", "ci"],
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

