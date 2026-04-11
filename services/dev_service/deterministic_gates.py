"""
Comandos de puerta determinista (lint/tests/typecheck) acotados al archivo de la tarea.

Placeholders soportados en plantillas de config:
- {file}   ruta relativa posix (p.ej. services/dev_service/main.py)
- {parent} directorio padre (p.ej. services/dev_service)
- {stem}   nombre sin extensión (p.ej. main)
"""

from __future__ import annotations

import re
from pathlib import Path


def normalize_repo_relative_path(file_path: str) -> str:
    fp = (file_path or "").strip().replace("\\", "/").lstrip("./")
    return fp or "."


def format_gate_command(template: str, file_path: str) -> str:
    """Sustituye placeholders; si la plantilla está vacía, devuelve cadena vacía."""
    t = (template or "").strip()
    if not t:
        return ""
    rel = normalize_repo_relative_path(file_path)
    parent = str(Path(rel).parent.as_posix()) if rel not in (".", "") else "."
    stem = Path(rel).stem if rel not in (".", "") else "root"
    out = t
    out = out.replace("{file}", rel)
    out = out.replace("{parent}", parent)
    out = out.replace("{stem}", stem)
    return re.sub(r"\s+", " ", out).strip()
