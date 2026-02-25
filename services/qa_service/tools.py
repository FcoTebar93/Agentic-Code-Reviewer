from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from pydantic import Field

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
        description="Lenguaje del código a analizar (actualmente solo 'python' soportado)",
    )
    code: str = Field(
        description="Código fuente completo a lintar",
    )
    file_path: str = Field(
        default="tmp.py",
        description="Ruta lógica del archivo (para mensajes de error)",
    )


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

            proc = subprocess.run(
                ["python", "-m", "ruff", "check", str(target)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            issues: list[dict[str, Any]] = []
            for line in proc.stdout.splitlines():
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

    return registry

