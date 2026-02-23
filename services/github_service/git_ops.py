"""
Git operations via subprocess.

Uses the git CLI directly for reliability and predictability.
All operations are synchronous (run in executor) to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


async def run_git(*args: str, cwd: str) -> str:
    """Run a git command asynchronously via subprocess."""
    cmd = ["git"] + list(args)
    logger.debug("Running: %s (cwd=%s)", " ".join(cmd), cwd)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode().strip()

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"git {args[0]} failed (rc={proc.returncode}): {err}")

    return output


async def clone_repo(repo_url: str, workspace_dir: str, token: str = "") -> str:
    """Clone a repo into workspace_dir. Returns the local path."""
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    local_path = os.path.join(workspace_dir, repo_name)

    if os.path.exists(local_path):
        logger.info("Repo already cloned at %s, pulling latest", local_path)
        await run_git("pull", "--ff-only", cwd=local_path)
        return local_path

    auth_url = repo_url
    if token and "github.com" in repo_url:
        auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")

    os.makedirs(workspace_dir, exist_ok=True)
    await run_git("clone", auth_url, local_path, cwd=workspace_dir)
    logger.info("Cloned %s to %s", repo_url, local_path)
    return local_path


async def create_branch(repo_path: str, branch_name: str) -> None:
    await run_git("checkout", "-b", branch_name, cwd=repo_path)
    logger.info("Created branch %s", branch_name)


async def write_files(
    repo_path: str, files: list[dict]
) -> list[str]:
    """Write generated code files into the repo. Returns list of written paths."""
    written = []
    for f in files:
        file_path = os.path.join(repo_path, f["file_path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        Path(file_path).write_text(f["code"], encoding="utf-8")
        written.append(f["file_path"])
    logger.info("Wrote %d files", len(written))
    return written


async def commit_and_push(
    repo_path: str, branch_name: str, message: str, file_paths: list[str]
) -> None:
    for fp in file_paths:
        await run_git("add", fp, cwd=repo_path)
    await run_git("commit", "-m", message, cwd=repo_path)
    await run_git("push", "-u", "origin", branch_name, cwd=repo_path)
    logger.info("Pushed branch %s", branch_name)


async def open_pull_request(
    repo_url: str,
    branch_name: str,
    title: str,
    body: str,
    token: str,
) -> dict:
    """Create a PR via GitHub REST API. Returns {pr_url, pr_number}."""
    parts = repo_url.rstrip("/").replace(".git", "").split("/")
    owner, repo = parts[-2], parts[-1]

    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "title": title,
        "head": branch_name,
        "base": "main",
        "body": body,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    pr_url = data["html_url"]
    pr_number = data["number"]
    logger.info("Opened PR #%d: %s", pr_number, pr_url)
    return {"pr_url": pr_url, "pr_number": pr_number}
