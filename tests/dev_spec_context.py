"""Contexto dev: recorte de spec y presupuesto."""

from __future__ import annotations

from services.dev_service.main import _build_dev_context


def test_spec_respects_spec_max_chars() -> None:
    body = "B" * 4000
    ctx = _build_dev_context(
        "",
        "",
        "",
        spec_block=body,
        spec_max_chars=800,
        max_chars=9000,
    )
    assert "TASK SPEC & TESTS:" in ctx
    chunk = ctx.split("TASK SPEC & TESTS:\n", 1)[1].split("\n\n")[0]
    assert len(chunk) == 800


def test_total_context_truncated_to_max_chars() -> None:
    ctx = _build_dev_context(
        "E" * 3000,
        "",
        "",
        spec_block="S" * 500,
        spec_max_chars=500,
        max_chars=400,
    )
    assert len(ctx) <= 400
