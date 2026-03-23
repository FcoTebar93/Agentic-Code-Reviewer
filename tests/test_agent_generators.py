"""Lightweight regression tests for agent generators (no external LLM API)."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("REPO_ROOT", str(_ROOT))


class TestParseSpecResponse(unittest.TestCase):
    def test_basic_blocks(self) -> None:
        from services.spec_service.spec_generator import parse_spec_response

        raw = (
            "SPEC:\n"
            "Comportamiento esperado.\n"
            "\n"
            "TESTS:\n"
            "- [CRITICAL] caso A\n"
            "- [OPTIONAL] caso B\n"
        )
        spec, tests = parse_spec_response(raw)
        self.assertIn("Comportamiento", spec)
        self.assertIn("[CRITICAL]", tests)
        self.assertIn("caso A", tests)


class TestCorrelationPayload(unittest.TestCase):
    def test_plan_task_nested(self) -> None:
        from shared.correlation import plan_task_from_payload

        p, t = plan_task_from_payload(
            {"plan_id": "pl-1", "task": {"task_id": "tk-2"}}
        )
        self.assertEqual(p, "pl-1")
        self.assertEqual(t, "tk-2")


class TestMockToolLoops(unittest.TestCase):
    def test_spec_tool_loop_mock(self) -> None:
        async def _run() -> None:
            from shared.llm_adapter.mock_provider import MockProvider
            from services.spec_service.spec_generator import generate_spec_with_tool_loop
            from services.spec_service.tools import build_spec_tool_registry

            llm = MockProvider()
            reg = build_spec_tool_registry()
            out, pt, ct = await generate_spec_with_tool_loop(
                llm,
                reg,
                description="Implementar utilidad",
                file_path="src/util.py",
                language="python",
                plan_context="ctx",
                test_layout="- pytest",
                mode="normal",
                max_steps=6,
            )
            self.assertTrue(out.get("spec", "").strip())
            self.assertTrue(out.get("tests", "").strip())
            self.assertGreater(pt + ct, 0)

        asyncio.run(_run())

    def test_dev_tool_loop_mock(self) -> None:
        async def _run() -> None:
            from shared.contracts.events import TaskSpec
            from shared.llm_adapter.mock_provider import #MockProvider
            from services.dev_service.generator import generate_code_with_tool_loop
            from services.dev_service.tools import build_dev_tool_registry

            llm = MockProvider()
            reg = build_dev_tool_registry()
            task = TaskSpec(
                description="add helper",
                file_path="src/x.py",
                language="python",
            )
            result, pt, ct = await generate_code_with_tool_loop(
                llm,
                task,
                registry=reg,
                max_steps=6,
            )
            self.assertTrue(result.code.strip())
            self.assertGreater(pt + ct, 0)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
