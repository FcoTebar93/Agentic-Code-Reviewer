from __future__ import annotations

from pathlib import Path

from shared.utils.repo_style_hints import build_repo_style_hints


def test_build_repo_style_hints_prefers_tool_section_in_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = \"x\"\n\n[tool.ruff]\nline-length = 88\n",
        encoding="utf-8",
    )
    out = build_repo_style_hints(
        tmp_path,
        language="python",
        file_path="src/foo.py",
        max_total_chars=2000,
    )
    assert "[tool.ruff]" in out
    assert "line-length = 88" in out


def test_build_repo_style_hints_respects_max_total_chars(tmp_path: Path) -> None:
    (tmp_path / ".editorconfig").write_text("root = true\n", encoding="utf-8")
    (tmp_path / "ruff.toml").write_text("line-length = 99\n", encoding="utf-8")
    out = build_repo_style_hints(
        tmp_path,
        language="python",
        file_path="a.py",
        max_total_chars=120,
    )
    assert len(out) <= 200
    assert "truncated" in out or ".editorconfig" in out


def test_build_repo_style_hints_empty_when_not_a_directory(tmp_path: Path) -> None:
    p = tmp_path / "nope.txt"
    p.write_text("x", encoding="utf-8")
    assert build_repo_style_hints(p) == ""
