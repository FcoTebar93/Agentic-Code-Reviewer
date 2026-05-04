"""Tests de parsing de salida LLM del meta_planner."""

from __future__ import annotations

import json

import pytest

from services.meta_planner import planner as planner_mod

_parse = planner_mod._parse_response


def test_empty() -> None:
    r, tasks, ok = _parse("")
    assert r == "" and tasks == [] and ok is True


def test_whitespace() -> None:
    r, tasks, ok = _parse("   \n\t  ")
    assert r == "" and tasks == [] and ok is True


def test_golden() -> None:
    raw = """
REASONING: Split API and tests for clarity.
TASKS: [{"description": "Add handler", "file_path": "app/h.py", "language": "python", "edit_scope": "file", "group_id": "app"}]
"""
    r, tasks, ok = _parse(raw)
    assert "Split API" in r and ok and len(tasks) == 1
    t0 = tasks[0]
    assert t0.description == "Add handler"
    assert t0.file_path == "app/h.py"
    assert t0.language == "python"
    assert t0.edit_scope == "file"
    assert t0.group_id == "app"
    assert t0.task_id


def test_fenced_json() -> None:
    raw = """REASONING: Use fenced block.
TASKS:
```json
[
  {"description": "x", "file_path": "a.ts", "language": "typescript"}
]
```
"""
    _, tasks, ok = _parse(raw)
    assert ok and len(tasks) == 1
    assert tasks[0].file_path == "a.ts"
    assert tasks[0].language == "typescript"


def test_bad_json_fallback() -> None:
    raw = """REASONING: Broken JSON below.
TASKS: [not valid json
"""
    r, tasks, ok = _parse(raw)
    assert "Broken JSON" in r and not ok
    assert len(tasks) == 1
    assert tasks[0].file_path == "src/main.py"
    assert "Implement:" in tasks[0].description


def test_empty_tasks_array() -> None:
    r, tasks, ok = _parse("REASONING: No tasks.\nTASKS: []")
    assert "No tasks" in r and tasks == [] and not ok


def test_object_not_array() -> None:
    _, tasks, ok = _parse('REASONING: Wrong shape.\nTASKS: {"description": "only one"}')
    assert not ok and len(tasks) == 1 and tasks[0].file_path == "src/main.py"


def test_filters_non_dicts() -> None:
    raw = """REASONING: Mixed.
TASKS: [{"description": "ok", "file_path": "f.py", "language": "python"}, "skip", 42]
"""
    _, tasks, ok = _parse(raw)
    assert ok and len(tasks) == 1 and tasks[0].description == "ok"


def test_only_scalars_in_array() -> None:
    _, tasks, ok = _parse('REASONING: x\nTASKS: ["a", 1]')
    assert tasks == [] and not ok


def test_reasoning_only() -> None:
    r, tasks, ok = _parse("REASONING: Forgot TASKS section entirely.")
    assert "Forgot TASKS" in r and tasks == [] and not ok


@pytest.mark.parametrize(
    ("missing_key", "expected_default"),
    [
        ("description", ""),
        ("file_path", "unknown.py"),
        ("language", "python"),
    ],
)
def test_task_defaults(missing_key: str, expected_default: str) -> None:
    obj = {"description": "d", "file_path": "p.py", "language": "python"}
    del obj[missing_key]
    raw = f"REASONING: r\nTASKS: {json.dumps([obj])}"
    _, tasks, ok = _parse(raw)
    assert ok
    t0 = tasks[0]
    if missing_key == "description":
        assert t0.description == expected_default
    elif missing_key == "file_path":
        assert t0.file_path == expected_default
    else:
        assert t0.language == expected_default
