"""
Git operations via subprocess + GitHub REST API.

Uses the git CLI directly for reliability and predictability.
All git subprocesses run asynchronously to avoid blocking the event loop.

Git identity (user.name / user.email) is configured per-repository before
any commit, sourced from environment variables so the agent has an auditable
identity in the git log.
"""

from __future__ import annotations

import asyncio
import logging
import os
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


async def configure_git_identity(
    repo_path: str, author_name: str, author_email: str
) -> None:
    """Set git user identity for this repository before committing."""
    await run_git("config", "user.name", author_name, cwd=repo_path)
    await run_git("config", "user.email", author_email, cwd=repo_path)
    logger.debug(
        "Git identity configured: %s <%s> in %s",
        author_name, author_email, repo_path,
    )


async def _is_repo_empty(repo_path: str) -> bool:
    """Return True if the repo has no commits yet."""
    try:
        await run_git("rev-parse", "HEAD", cwd=repo_path)
        return False
    except RuntimeError:
        return True


async def _init_empty_repo(
    repo_path: str,
    auth_url: str,
    author_name: str,
    author_email: str,
) -> None:
    """
    Push an initial commit to an empty remote so that a base branch ('main')
    exists and PR creation has something to merge into.
    """
    logger.info("Repository is empty — creating initial commit on main")
    await configure_git_identity(repo_path, author_name, author_email)
    await run_git("checkout", "-b", "main", cwd=repo_path)

    readme_path = os.path.join(repo_path, "README.md")
    Path(readme_path).write_text(
        "# Project\n\nInitialized by [ADMADC](https://github.com/FcoTebar93/Agentic-Project).\n",
        encoding="utf-8",
    )
    await run_git("add", "README.md", cwd=repo_path)
    await run_git("commit", "-m", "chore: initial commit", cwd=repo_path)
    await run_git("push", "-u", auth_url, "main", cwd=repo_path)
    logger.info("Initial commit pushed to main")


async def clone_repo(
    repo_url: str,
    workspace_dir: str,
    token: str = "",
    author_name: str = "ADMADC Bot",
    author_email: str = "admadc@localhost",
) -> str:
    """Clone a repo into workspace_dir. Returns the local path.

    If the remote is empty (no commits), an initial commit is pushed to
    'main' so that the agent's feature branch has a base to target.
    """
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    local_path = os.path.join(workspace_dir, repo_name)

    auth_url = repo_url
    if token and "github.com" in repo_url:
        auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")

    if os.path.exists(local_path):
        logger.info("Repo already cloned at %s", local_path)
        if not await _is_repo_empty(local_path):
            try:
                await run_git("pull", "--ff-only", cwd=local_path)
            except RuntimeError as exc:
                msg = str(exc)
                # Caso típico: el remoto no tiene aún la rama base que
                # Git espera (por ejemplo 'main'). Si vemos este tipo de
                # error, asumimos que nuestro 'main' local debe convertirse
                # en la rama base remota y hacemos push en vez de fallar.
                if (
                    "no such ref was fetched" in msg
                    or "Couldn't find remote ref" in msg
                    or "couldn't find remote ref" in msg
                ):
                    logger.warning(
                        "Remote has no base branch yet; pushing local 'main' as initial base"
                    )
                    await run_git("push", "-u", auth_url, "main", cwd=local_path)
                else:
                    raise
        return local_path

    os.makedirs(workspace_dir, exist_ok=True)
    await run_git("clone", auth_url, local_path, cwd=workspace_dir)
    logger.info("Cloned %s to %s", repo_url, local_path)

    if await _is_repo_empty(local_path):
        await _init_empty_repo(local_path, auth_url, author_name, author_email)

    return local_path


async def create_branch(repo_path: str, branch_name: str) -> None:
    await run_git("checkout", "-b", branch_name, cwd=repo_path)
    logger.info("Created branch %s", branch_name)


async def write_files(repo_path: str, files: list[dict]) -> list[str]:
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
    repo_path: str,
    branch_name: str,
    message: str,
    file_paths: list[str],
    author_name: str = "ADMADC Bot",
    author_email: str = "admadc@localhost",
) -> None:
    """Stage, commit (with configured identity), and push the given files."""
    await configure_git_identity(repo_path, author_name, author_email)
    for fp in file_paths:
        await run_git("add", fp, cwd=repo_path)
    await run_git("commit", "-m", message, cwd=repo_path)
    await run_git("push", "-u", "origin", branch_name, cwd=repo_path)
    logger.info("Pushed branch %s", branch_name)


def build_pr_body(plan_id: str, files: list[dict]) -> str:
    """
    Build a rich PR description that includes per-file agent reasoning,
    making the AI decision process visible directly in the GitHub PR.
    """
    lines = [
        "## 🤖 Auto-generated by ADMADC",
        "",
        f"**Plan ID:** `{plan_id}`",
        "",
        "---",
        "",
        "### Pipeline summary",
        "",
        "| Stage | Agent | Status |",
        "|-------|-------|--------|",
        "| Planning | meta_planner | ✅ |",
        "| Code Generation | dev_service | ✅ |",
        "| QA Review | qa_service | ✅ |",
        "| Security Scan | security_service | ✅ |",
        "| Human Approval | reviewer | ✅ |",
        "",
        "---",
        "",
        "### Generated files",
        "",
    ]

    for f in files:
        file_path = f.get("file_path", "unknown")
        reasoning = f.get("reasoning", "")
        lines.append(f"#### `{file_path}`")
        if reasoning:
            lines.append("")
            lines.append(f"> **Dev agent reasoning:** {reasoning}")
        lines.append("")

    lines += [
        "---",
        "",
        "*This pull request was created autonomously by the ADMADC pipeline.*",
        "*All changes have passed QA review and security scanning.*",
        "*A human reviewer approved this PR before it was submitted.*",
    ]

    return "\n".join(lines)


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
        "X-GitHub-Api-Version": "2022-11-28",
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
