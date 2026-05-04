from __future__ import annotations

from shared.utils.code_change_guard import large_change_note


def test_large_change_none_for_small_edit() -> None:
    prev = "def f():\n    return 1\n"
    new = "def f():\n    return 2\n"
    assert large_change_note(prev, new, soft_line_limit=50) is None


def test_large_change_warns_new_big_file() -> None:
    prev = ""
    new = "\n".join(f"# {i}" for i in range(150))
    msg = large_change_note(prev, new, soft_line_limit=50)
    assert msg is not None
    assert "150" in msg or "lines" in msg


def test_very_large_output_message() -> None:
    prev = "x\n" * 30
    new = "y\n" * 250
    msg = large_change_note(prev, new, soft_line_limit=50)
    assert msg is not None
    assert "Very large output" in msg
