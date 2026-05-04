"""Plantillas de puertas deterministas (lint/tests/mypy) por archivo."""

from __future__ import annotations

from services.dev_service.deterministic_gates import format_gate_command


def test_format_file_parent_stem() -> None:
    cmd = format_gate_command(
        "ruff check {file} && mypy {parent}",
        r"services\dev_service\main.py",
    )
    assert "services/dev_service/main.py" in cmd
    assert "services/dev_service" in cmd


def test_format_stem_only() -> None:
    assert "main" in format_gate_command("echo {stem}", "foo/bar/main.py")
