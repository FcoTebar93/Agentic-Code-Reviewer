from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubConfig:
    rabbitmq_url: str
    github_token: str
    workspace_dir: str
    log_level: str

    @classmethod
    def from_env(cls) -> GitHubConfig:
        return cls(
            rabbitmq_url=os.environ["RABBITMQ_URL"],
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            workspace_dir=os.environ.get("GITHUB_WORKSPACE", "/app/workspace"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
