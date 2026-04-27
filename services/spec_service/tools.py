from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from shared.tools import (
    ToolDefinition,
    ToolInput,
    ToolRegistry,
)

REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/workspace")).resolve()


class ReadFileInput(ToolInput):
    path: str = Field(
        description="Ruta relativa al repo del archivo a leer",
        examples=["services/spec_service/main.py", "frontend/src/App.tsx"],
    )
    max_bytes: int = Field(
        default=16_000,
        ge=1,
        le=128_000,
        description="Máximo de bytes a devolver del archivo",
    )


class ListProjectFilesInput(ToolInput):
    directory: str = Field(
        default=".",
        description="Directorio base relativo al repo",
        examples=["services", "frontend/src/components"],
    )
    pattern: str = Field(
        default="*.*",
        description="Patrón de glob (por ejemplo *.py, *.tsx, *.js)",
    )
    max_results: int = Field(
        default=200,
        ge=1,
        le=2000,
        description="Máximo de rutas a devolver",
    )


class SearchInRepoInput(ToolInput):
    pattern: str = Field(
        description="Patrón de texto o regex a buscar en el repo (por ejemplo nombre de función o componente)",
    )
    directory: str = Field(
        default=".",
        description="Directorio base relativo al repo donde buscar",
    )
    max_results: int = Field(
        default=80,
        ge=1,
        le=500,
        description="Máximo de coincidencias a devolver",
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
    """Buscar un patrón de texto/regex en los archivos del repositorio."""
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


def build_spec_tool_registry() -> ToolRegistry:
    """ToolRegistry para spec_service: acceso ligero al repo."""
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Leer el contenido actual de un archivo del repositorio (preview limitado)",
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
            name="search_in_repo",
            description="Buscar un patrón de texto/regex en los archivos del repositorio",
            input_model=SearchInRepoInput,
            func=search_in_repo_tool,
            timeout_s=5.0,
            max_retries=0,
            sandboxed=True,
            tags=["search", "repo"],
        )
    )

    return registry

