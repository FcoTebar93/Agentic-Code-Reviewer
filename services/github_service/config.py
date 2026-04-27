from __future__ import annotations

import os
from dataclasses import dataclass

from shared.utils.env import env_bool, env_str


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
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            github_token=env_str("GITHUB_TOKEN", ""),
            workspace_dir=env_str("GITHUB_WORKSPACE", "/app/workspace"),
            log_level=env_str("LOG_LEVEL", "INFO"),
            git_author_name=env_str("GIT_AUTHOR_NAME", "ADMADC Bot"),
            git_author_email=env_str("GIT_AUTHOR_EMAIL", "admadc@localhost"),
            workspace_info_enabled=env_bool("GITHUB_WORKSPACE_INFO_ENABLED"),
            workspace_info_token=env_str("GITHUB_WORKSPACE_INFO_TOKEN", ""),
        )
