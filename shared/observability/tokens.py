from __future__ import annotations

import logging

from shared.contracts.events import TokensUsedPayload, metrics_tokens_used
from shared.utils import store_event


async def emit_token_usage_event(
    *,
    service_name: str,
    plan_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    http_client,
    logger: logging.Logger,
) -> None:
    """Emit and persist a metrics.tokens_used event when tokens are present."""
    if not (prompt_tokens or completion_tokens):
        return
    tok_event = metrics_tokens_used(
        service_name,
        TokensUsedPayload(
            plan_id=plan_id,
            service=service_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )
    await store_event(
        http_client,
        tok_event,
        logger=logger,
        error_message="Failed to store event %s",
    )
