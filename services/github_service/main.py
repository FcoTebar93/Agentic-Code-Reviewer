"""GitHub Service -- materializes generated code into a repository."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastapi import FastAPI, Header, HTTPException, status

from services.github_service.config import GitHubConfig
from services.github_service.git_ops import (
    build_pr_body,
    clone_repo,
    commit_and_push,
    create_branch,
    open_pull_request,
    write_files,
)
from shared.contracts.events import (
    EventType,
    PrApprovalPayload,
    PRCreatedPayload,
    PRRequestedPayload,
    pr_created,
)
from shared.http.client import create_async_http_client
from shared.logging.logger import setup_logging
from shared.middleware.correlation import install_correlation_middleware
from shared.observability.metrics import (
    metrics_response,
    pr_creation_latency,
    tasks_completed,
)
from shared.utils import EventBus, store_event, subscribe_typed_event

SERVICE_NAME = "github_service"
event_bus: EventBus = cast(EventBus, None)
http_client: httpx.AsyncClient = cast(httpx.AsyncClient, None)
cfg: GitHubConfig = cast(GitHubConfig, None)


@asynccontextmanager
async def lifespan(application: FastAPI):
    global event_bus, http_client, cfg
    logger = setup_logging(SERVICE_NAME)

    cfg = GitHubConfig.from_env()
    http_client = create_async_http_client(
        base_url="http://memory_service:8000",
        default_timeout=30.0,
    )
    event_bus = EventBus(cfg.rabbitmq_url)
    await event_bus.connect()

    asyncio.create_task(_consume_human_approved())
    logger.info(
        "GitHub Service ready (listening for pr.human_approved, git identity: %s <%s>)",
        cfg.git_author_name,
        cfg.git_author_email,
    )
    yield

    logger.info("Shutting down")
    if event_bus:
        await event_bus.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="ADMADC - GitHub Service",
    version="0.3.0",
    description="Handles git operations, branching, and PR creation",
    lifespan=lifespan,
)
install_correlation_middleware(app)
logger = logging.getLogger(SERVICE_NAME)


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return metrics_response()


@app.get("/workspace")
async def workspace_info(x_workspace_token: str | None = Header(default=None)):
    import os

    if not cfg or not cfg.workspace_info_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    if cfg.workspace_info_token and x_workspace_token != cfg.workspace_info_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    workspace = cfg.workspace_dir if cfg else "/app/workspace"
    contents = []
    if os.path.exists(workspace):
        contents = sorted(os.listdir(workspace))[:200]
    return {"workspace": workspace, "contents": contents}


async def _consume_human_approved() -> None:
    """Consume pr.human_approved events published by the gateway after."""
    async def on_payload(approval: PrApprovalPayload) -> None:
        if approval.decision != "approved" or not approval.pr_context:
            logger.warning(
                "Received pr.human_approved with non-approved decision for plan %s",
                approval.plan_id[:8],
            )
            return
        pr_payload = PRRequestedPayload.model_validate(approval.pr_context)
        await _handle_pr_request(pr_payload)

    await subscribe_typed_event(
        event_bus=event_bus,
        queue_name="github_service.human_approved",
        routing_keys=[EventType.PR_HUMAN_APPROVED.value],
        payload_model=PrApprovalPayload,
        on_payload=on_payload,
        max_retries=3,
    )


async def _handle_pr_request(payload: PRRequestedPayload) -> None:
    plan_id = payload.plan_id
    logger.info("Handling PR request for plan %s", plan_id[:8])

    with pr_creation_latency.time():
        files_data = [f.model_dump() for f in payload.files]

        if payload.repo_url and cfg.github_token:
            repo_path = await clone_repo(
                payload.repo_url, cfg.workspace_dir, cfg.github_token,
                author_name=cfg.git_author_name,
                author_email=cfg.git_author_email,
            )
            await create_branch(repo_path, payload.branch_name)
            written = await write_files(repo_path, files_data)
            await commit_and_push(
                repo_path,
                payload.branch_name,
                payload.commit_message,
                written,
                author_name=cfg.git_author_name,
                author_email=cfg.git_author_email,
            )
            pr_body = build_pr_body(plan_id, files_data)
            result = await open_pull_request(
                repo_url=payload.repo_url,
                branch_name=payload.branch_name,
                title=payload.commit_message,
                body=pr_body,
                token=cfg.github_token,
            )

            created_payload = PRCreatedPayload(
                plan_id=plan_id,
                pr_url=result["pr_url"],
                pr_number=result["pr_number"],
                branch_name=payload.branch_name,
            )
            created_event = pr_created(SERVICE_NAME, created_payload)
            await event_bus.publish(created_event)
            await store_event(
                http_client,
                created_event,
                logger=logger,
                error_message="Failed to store event %s in memory_service",
            )
            logger.info(
                "PR #%d created for plan %s — %s",
                result["pr_number"], plan_id[:8], result["pr_url"],
            )

        else:
            import os
            local_dir = os.path.join(cfg.workspace_dir, f"plan-{plan_id[:8]}")
            os.makedirs(local_dir, exist_ok=True)
            written = await write_files(local_dir, files_data)
            logger.info(
                "No repo_url or token — %d file(s) written locally to %s",
                len(written), local_dir,
            )
            created_payload = PRCreatedPayload(
                plan_id=plan_id,
                pr_url=f"file://{local_dir}",
                pr_number=0,
                branch_name=payload.branch_name,
            )
            created_event = pr_created(SERVICE_NAME, created_payload)
            await event_bus.publish(created_event)
            await store_event(
                http_client,
                created_event,
                logger=logger,
                error_message="Failed to store event %s in memory_service",
            )
            logger.info("pr.created published (local workspace) for plan %s", plan_id[:8])

        tasks_completed.labels(service=SERVICE_NAME).inc()


