"""Agrupación heurística por ruta de archivo."""

from __future__ import annotations

from shared.utils.path_grouping import infer_group_id


def test_infer_group_id_empty() -> None:
    assert infer_group_id("") == "root"
    assert infer_group_id("   ") == "root"


def test_infer_group_id_single_segment() -> None:
    assert infer_group_id("main.py") == "main.py"


def test_infer_group_id_two_segments() -> None:
    assert infer_group_id("src/utils.py") == "src/utils.py"


def test_infer_group_id_deep_path() -> None:
    assert infer_group_id("a/b/c/d/e.py") == "a/b/c"


def test_infer_group_id_windows_separators() -> None:
    assert infer_group_id("services\\gateway\\routes\\x.py") == "services/gateway/routes"
