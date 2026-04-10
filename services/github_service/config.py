from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubConfig:
    rabbitmq_url: str
    github_token: str
    workspace_dir: str
    log_level: str
    git_author_name: str
    git_author_email: str
    workspace_info_enabled: bool
    workspace_info_token: str

    @classmethod
    def from_env(cls) -> GitHubConfig:
        workspace_info_enabled = os.environ.get("GITHUB_WORKSPACE_INFO_ENABLED", "false")
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            workspace_dir=os.environ.get("GITHUB_WORKSPACE", "/app/workspace"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            git_author_name=os.environ.get("GIT_AUTHOR_NAME", "ADMADC Bot"),
            git_author_email=os.environ.get("GIT_AUTHOR_EMAIL", "admadc@localhost"),
            workspace_info_enabled=workspace_info_enabled.lower() in ("1", "true", "yes"),
            workspace_info_token=os.environ.get("GITHUB_WORKSPACE_INFO_TOKEN", ""),
        )
