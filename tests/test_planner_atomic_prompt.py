"""Regresión: planner pide tareas atómicas y orden contrato→implementación."""m __future__ import annotations

from services.meta_planner.planner import (
    _PLANNER_PARSE_REPAIR,
    PLANNER_SENIOR_GUIDELINES,
    PLANNING_PROMPT_TEMPLATE,
)


def test_senior_guidelines_atomic_and_contracts_first() -> None:
    assert "Atomic tasks" in PLANNER_SENIOR_GUIDELINES
    assert "Lead with stable surfaces" in PLANNER_SENIOR_GUIDELINES
    assert "single primary intent" in PLANNER_SENIOR_GUIDELINES


def test_planning_template_one_change_per_task() -> None:
    assert "ONE main kind of change per task" in PLANNING_PROMPT_TEMPLATE
    assert "public contract" in PLANNING_PROMPT_TEMPLATE


def test_parse_repair_hints_split_and_order() -> None:
    assert "one primary intent" in _PLANNER_PARSE_REPAIR
    assert "contracts before implementation" in _PLANNER_PARSE_REPAIR
