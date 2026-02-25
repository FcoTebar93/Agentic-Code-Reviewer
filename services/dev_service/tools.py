from __future__ import annotations

import asyncio
import os
import subprocess
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

    return registry

