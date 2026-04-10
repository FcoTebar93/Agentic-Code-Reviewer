"""Tests del endpoint /workspace del github_service."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import HTTPException

import services.github_service.main as github_main
from services.github_service.config import GitHubConfig
from services.github_service.main import workspace_info


def _cfg(
    workspace: str,
    *,
    enabled: bool,
    token: str = "",
) -> GitHubConfig:
    return GitHubConfig(
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        github_token="",
        workspace_dir=workspace,
        log_level="INFO",
        git_author_name="ADMADC Bot",
        git_author_email="admadc@localhost",
        workspace_info_enabled=enabled,
        workspace_info_token=token,
    )


def test_disabled_404(tmp_path: Path) -> None:
    async def _run() -> None:
        github_main.cfg = _cfg(str(tmp_path), enabled=False)
        try:
            await workspace_info()
            raise AssertionError("Expected HTTPException 404")
        except HTTPException as exc:
            assert exc.status_code == 404

    asyncio.run(_run())


def test_bad_token_403(tmp_path: Path) -> None:
    async def _run() -> None:
        github_main.cfg = _cfg(str(tmp_path), enabled=True, token="secret-token")
        try:
            await workspace_info(x_workspace_token="wrong-token")
            raise AssertionError("Expected HTTPException 403")
        except HTTPException as exc:
            assert exc.status_code == 403

    asyncio.run(_run())


def test_ok_lists_files(tmp_path: Path) -> None:
    async def _run() -> None:
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        github_main.cfg = _cfg(str(tmp_path), enabled=True, token="secret-token")
        result = await workspace_info(x_workspace_token="secret-token")
        assert result["workspace"] == str(tmp_path)
        assert result["contents"] == ["a.txt", "b.txt"]

    asyncio.run(_run())
