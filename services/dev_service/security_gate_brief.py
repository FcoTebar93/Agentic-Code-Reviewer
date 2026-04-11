"""
Texto breve para el prompt del Dev, alineado con SECURITY_RULES del security_service.

Si añades reglas en services/security_service/config.py, el listado de ids aquí se actualiza solo.
"""

from __future__ import annotations

from services.security_service.config import SECURITY_RULES


def security_gate_brief() -> str:
    ids = [rid for rid, _ in SECURITY_RULES]
    lines = [
        "Before any PR, security_service runs the same deterministic checks. "
        "Do not introduce code that would match these rules:",
        *[f"- {rid}" for rid in ids],
        "In practice: secrets only via environment or existing secret managers; no eval/exec/pickle.loads on "
        "untrusted data; no shell=True with interpolated user input; validate paths; parameterized SQL; "
        "avoid permissive CORS (*) and DEBUG=True in production defaults unless the task explicitly requires them.",
    ]
    return "\n".join(lines)
