"""
Ejecución endurecida de subprocesos para herramientas de agentes.

- Sin shell (solo argv explícitos).
- Timeouts obligatorios en las APIs de alto nivel.
- Límite de tamaño de stdout/stderr (UTF-8) para evitar fugas de memoria.
- Para comandos introducidos como string (dev agent): shlex + bloqueo de metacaracteres + allowlist.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
        return v if v > 0 else default
    except ValueError:
        return default


DEFAULT_SYNC_TIMEOUT_S = _float_env("AGENT_SUBPROCESS_DEFAULT_TIMEOUT_S", 120.0)
DEFAULT_MAX_STDOUT_BYTES = _int_env("AGENT_SUBPROCESS_MAX_STDOUT_BYTES", 512_000)
DEFAULT_MAX_STDERR_BYTES = _int_env("AGENT_SUBPROCESS_MAX_STDERR_BYTES", 256_000)

MAX_CLI_STRING_CHARS = 4_000
MAX_ARGV_LEN = 64
MAX_SINGLE_ARG_CHARS = 4_096

PYTHON_CLI_MODULES = frozenset(
    {"pytest", "ruff", "bandit", "black", "semgrep", "mypy"}
)
NPX_ALLOWED = frozenset({"eslint", "prettier", "tsc"})
NPM_LIKE_SUBCOMMANDS = frozenset({"test", "run", "exec", "ci"})
YARN_PNPM_SUBCOMMANDS = NPM_LIKE_SUBCOMMANDS | {"lint"}


@dataclass(frozen=True)
class SubprocessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _truncate_utf8(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _normalize_prog_name(argv0: str) -> str:
    base = os.path.basename(argv0).lower()
    if base.endswith(".exe"):
        base = base[: -len(".exe")]
    return base


def validate_repo_cli_argv(argv: Sequence[str]) -> tuple[bool, str]:
    """
    Allowlist para comandos de repo que el agente dev puede pasar como string parseado.
    No aplica a argv construidos internamente por QA/security (solo run_sync_hardened).
    """
    if not argv:
        return False, "comando vacío"
    if len(argv) > MAX_ARGV_LEN:
        return False, "demasiados argumentos"
    for a in argv:
        if len(a) > MAX_SINGLE_ARG_CHARS:
            return False, "argumento demasiado largo"
        if "\x00" in a:
            return False, "byte nulo en argumento"

    prog = _normalize_prog_name(argv[0])

    if prog in ("python", "python3"):
        if len(argv) < 3 or argv[1] != "-m":
            return False, "solo se permite la forma python -m <módulo>"
        mod = argv[2]
        if mod not in PYTHON_CLI_MODULES:
            return False, f"módulo python -m no permitido: {mod}"
        return True, ""

    if prog == "pytest":
        return True, ""

    if prog == "ruff":
        return True, ""

    if prog == "npm":
        if len(argv) < 2 or argv[1] not in NPM_LIKE_SUBCOMMANDS:
            return False, "npm solo permite subcomandos: test, run, exec, ci"
        return True, ""

    if prog in ("pnpm", "yarn"):
        if len(argv) < 2 or argv[1] not in YARN_PNPM_SUBCOMMANDS:
            return False, f"{prog} solo permite subcomandos: {', '.join(sorted(YARN_PNPM_SUBCOMMANDS))}"
        return True, ""

    if prog == "npx":
        if len(argv) < 2:
            return False, "npx requiere el nombre del paquete/binario"
        if argv[1] not in NPX_ALLOWED:
            return False, f"npx solo permite: {', '.join(sorted(NPX_ALLOWED))}"
        return True, ""

    return False, f"programa no permitido: {prog}"


def parse_and_validate_repo_cli_command(command: str) -> tuple[list[str] | None, str]:
    """
    Parsea un comando de una sola línea sin shell y valida la allowlist.
    Devuelve (argv, "") o (None, mensaje de error).
    """
    raw = command.strip()
    if not raw:
        return None, "comando vacío"
    if len(raw) > MAX_CLI_STRING_CHARS:
        return None, "comando demasiado largo"
    if any(c in raw for c in "\n\r\x00"):
        return None, "caracteres de control no permitidos"
    if "|" in raw or ";" in raw or "&" in raw:
        return None, "operadores de shell no permitidos (;|&)"
    if "`" in raw or "$(" in raw:
        return None, "sustitución de shell no permitida"
    if ">" in raw or "<" in raw:
        return None, "redirecciones no permitidas"
    if raw.startswith(("-", "=")):
        return None, "inicio de comando inválido"

    posix = os.name != "nt"
    try:
        parts = shlex.split(raw, posix=posix)
    except ValueError as e:
        return None, f"error al parsear: {e}"

    if not parts:
        return None, "comando vacío tras parsear"

    def _strip_outer_quotes(s: str) -> str:
        t = s.strip()
        if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
            return t[1:-1]
        return t

    parts = [_strip_outer_quotes(p) for p in parts]

    ok, err = validate_repo_cli_argv(parts)
    if not ok:
        return None, err
    return parts, ""


def cwd_must_be_under_repo(cwd: Path, repo_root: Path) -> tuple[bool, str]:
    try:
        c = cwd.resolve()
        r = repo_root.resolve()
        c_s = str(c)
        r_s = str(r)
        if c_s == r_s or c_s.startswith(r_s + os.sep):
            return True, ""
    except (OSError, ValueError):
        pass
    return False, "cwd fuera del directorio raíz del repositorio"


def run_sync_hardened(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout_s: float | None = None,
    max_stdout_bytes: int | None = None,
    max_stderr_bytes: int | None = None,
    env: Mapping[str, str] | None = None,
) -> SubprocessResult:
    """
    subprocess.run sin shell, con timeout y recorte de salida.
    """
    argv_list = [str(x) for x in argv]
    if not argv_list:
        return SubprocessResult(-1, "", "agent_subprocess: argv vacío", False)

    t = DEFAULT_SYNC_TIMEOUT_S if timeout_s is None else timeout_s
    mo = DEFAULT_MAX_STDOUT_BYTES if max_stdout_bytes is None else max_stdout_bytes
    me = DEFAULT_MAX_STDERR_BYTES if max_stderr_bytes is None else max_stderr_bytes
    cwd_s = str(cwd) if cwd is not None else None
    env_dict = dict(env) if env is not None else None

    try:
        completed = subprocess.run(
            argv_list,
            cwd=cwd_s,
            capture_output=True,
            text=True,
            timeout=t,
            env=env_dict,
            shell=False,
        )
        return SubprocessResult(
            int(completed.returncode if completed.returncode is not None else -1),
            _truncate_utf8(completed.stdout or "", mo),
            _truncate_utf8(completed.stderr or "", me),
            False,
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if e.stdout is not None else ""
        err = (e.stderr or "") if e.stderr is not None else ""
        return SubprocessResult(
            -1,
            _truncate_utf8(out, mo),
            _truncate_utf8(err + "\n[agent_subprocess: timeout]", me),
            True,
        )
    except Exception as e:
        return SubprocessResult(-1, "", f"agent_subprocess: {e}", False)


async def run_async_hardened(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout_s: float | None = None,
    max_stdout_bytes: int | None = None,
    max_stderr_bytes: int | None = None,
    env: Mapping[str, str] | None = None,
) -> SubprocessResult:
    """
    asyncio.create_subprocess_exec sin shell, con timeout y recorte de salida.
    """
    argv_list = [str(x) for x in argv]
    if not argv_list:
        return SubprocessResult(-1, "", "agent_subprocess: argv vacío", False)

    t = DEFAULT_SYNC_TIMEOUT_S if timeout_s is None else timeout_s
    mo = DEFAULT_MAX_STDOUT_BYTES if max_stdout_bytes is None else max_stdout_bytes
    me = DEFAULT_MAX_STDERR_BYTES if max_stderr_bytes is None else max_stderr_bytes
    cwd_s = str(cwd) if cwd is not None else None
    env_dict = dict(env) if env is not None else None

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv_list,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd_s,
            env=env_dict,
        )
    except Exception as e:
        return SubprocessResult(-1, "", f"agent_subprocess: {e}", False)

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=t)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        stdout_b, stderr_b = await proc.communicate()
        out = (stdout_b or b"").decode("utf-8", errors="replace")
        err = (stderr_b or b"").decode("utf-8", errors="replace")
        return SubprocessResult(
            -1,
            _truncate_utf8(out, mo),
            _truncate_utf8(err + "\n[agent_subprocess: timeout]", me),
            True,
        )

    out = (stdout_b or b"").decode("utf-8", errors="replace")
    err = (stderr_b or b"").decode("utf-8", errors="replace")
    rc = int(proc.returncode if proc.returncode is not None else -1)
    return SubprocessResult(
        rc,
        _truncate_utf8(out, mo),
        _truncate_utf8(err, me),
        False,
    )
