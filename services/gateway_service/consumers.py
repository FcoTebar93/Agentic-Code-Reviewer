from __future__ import annotations

import json
import logging

from shared.contracts.events import (
    BaseEvent,
    EventType,
    PipelineConclusionPayload,
    PrApprovalPayload,
    SecurityResultPayload,
    pipeline_conclusion,
    pr_pending_approval,
)
from shared.utils import store_event
from services.gateway_service.constants import SERVICE_NAME
from services.gateway_service.runtime import GatewayRuntime


async def consume_all_events(runtime: GatewayRuntime, logger: logging.Logger) -> None:
    """Broadcast every event on the bus to connected WebSocket clients."""

    async def handler(event: BaseEvent) -> None:
        payload = json.dumps(
            {"type": "event", "event": json.loads(event.model_dump_json())}
        )
        await runtime.manager.broadcast(payload)
        logger.debug(
            "Broadcast %s to %d clients",
            event.event_type.value,
            runtime.manager.connection_count,
        )

    await runtime.event_bus.subscribe(
        queue_name="gateway_service.broadcast",
        routing_keys=["#"],
        handler=handler,
        max_retries=1,
    )


async def consume_security_approved(runtime: GatewayRuntime, logger: logging.Logger) -> None:
    """
    Intercept security.approved events to create pending human approvals.
    """

    async def handler(event: BaseEvent) -> None:
        sec = SecurityResultPayload.model_validate(event.payload)
        if not sec.approved or not sec.pr_context:
            return

        files_changed: list[str] = []
        pr_files = sec.pr_context.get("files")
        if isinstance(pr_files, list):
            for f in pr_files:
                if isinstance(f, dict) and "file_path" in f:
                    files_changed.append(str(f["file_path"]))

        conclusion_payload = PipelineConclusionPayload(
            plan_id=sec.plan_id,
            branch_name=sec.branch_name,
            conclusion_text=sec.reasoning,
            files_changed=files_changed,
            approved=sec.approved,
        )
        conclusion_event = pipeline_conclusion(SERVICE_NAME, conclusion_payload)
        await runtime.event_bus.publish(conclusion_event)
        await store_event(
            runtime.http_client,
            conclusion_event,
            logger=logger,
            error_message="Could not store pipeline.conclusion in memory_service (event %s)",
        )

        approval = PrApprovalPayload(
            plan_id=sec.plan_id,
            branch_name=sec.branch_name,
            files_count=sec.files_scanned,
            security_reasoning=sec.reasoning,
            pr_context=sec.pr_context,
        )
        runtime.pending_approvals[approval.approval_id] = approval

        pending_event = pr_pending_approval(SERVICE_NAME, approval)
        await runtime.event_bus.publish(pending_event)

        await runtime.manager.broadcast(
            json.dumps({"type": "approval", "approval": approval.model_dump()})
        )

        logger.info(
            "PR approval pending for plan %s (approval_id %s). "
            "Waiting for human decision.",
            sec.plan_id[:8],
            approval.approval_id[:8],
        )

    await runtime.event_bus.subscribe(
        queue_name="gateway_service.hitl_approvals",
        routing_keys=[EventType.SECURITY_APPROVED.value],
        handler=handler,
        max_retries=1,
    )
