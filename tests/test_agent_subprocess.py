"""Tests para shared.agent_subprocess (parse, allowlist, run_sync)."""

from __future__ import annotations

import sys

from shared.agent_subprocess import (
    parse_and_validate_repo_cli_command,
    run_sync_hardened,
    validate_repo_cli_argv,
)


def test_validate_pytest() -> None:
    ok, err = validate_repo_cli_argv(["pytest", "-q", "tests/unit"])
    assert ok and err == ""


def test_validate_python_dash_m() -> None:
    ok, err = validate_repo_cli_argv([sys.executable, "-m", "pytest", "-q"])
    assert ok and err == ""


def test_validate_rejects_python_without_dash_m() -> None:
    ok, err = validate_repo_cli_argv([sys.executable, "script.py"])
    assert not ok


def test_validate_rejects_npm_install() -> None:
    ok, err = validate_repo_cli_argv(["npm", "install"])
    assert not ok
    assert "npm" in err.lower()


def test_validate_npx_eslint() -> None:
    ok, err = validate_repo_cli_argv(["npx", "eslint", "."])
    assert ok and err == ""


def test_validate_rejects_npx_arbitrary() -> None:
    ok, err = validate_repo_cli_argv(["npx", "curl", "evil"])
    assert not ok


def test_parse_rejects_semicolon() -> None:
    argv, err = parse_and_validate_repo_cli_command("pytest -q; rm -rf /")
    assert argv is None
    assert err


def test_parse_rejects_subshell() -> None:
    argv, err = parse_and_validate_repo_cli_command("pytest $(whoami)")
    assert argv is None


def test_parse_accepts_quoted_args() -> None:
    argv, err = parse_and_validate_repo_cli_command('pytest "tests/a b/test_foo.py"')
    assert argv is not None
    assert err == ""
    assert "tests/a b/test_foo.py" in argv


def test_run_sync_hardened_truncates_stdout() -> None:
    r = run_sync_hardened(
        [sys.executable, "-c", "print('x' * 5000)"],
        timeout_s=10.0,
        max_stdout_bytes=200,
        max_stderr_bytes=1024,
    )
    assert r.returncode == 0
    assert len(r.stdout.encode("utf-8")) <= 200


def test_run_sync_hardened_missing_cmd() -> None:
    r = run_sync_hardened(
        ["this_binary_should_not_exist_7f3a9c2e"],
        timeout_s=5.0,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    assert r.returncode == -1
    assert "agent_subprocess" in r.stderr or r.stderr
