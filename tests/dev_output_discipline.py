"""Regresión: prompts del dev incluyen disciplina de parche y una sola salida CODE."""
from __future__ import annotations

from services.dev_service.prompts import (
    CODE_GEN_PROMPT,
    OUTPUT_DISCIPLINE,
    TOOL_LOOP_SYSTEM,
)


def test_output_discipline_keywords() -> None:
    assert "one compilation unit" in OUTPUT_DISCIPLINE
    assert "minimal" in OUTPUT_DISCIPLINE.lower()
    assert "REPO STYLE" in OUTPUT_DISCIPLINE


def test_main_prompts_embed_discipline() -> None:
    assert OUTPUT_DISCIPLINE.strip()[:40] in CODE_GEN_PROMPT
    assert OUTPUT_DISCIPLINE.strip()[:40] in TOOL_LOOP_SYSTEM
