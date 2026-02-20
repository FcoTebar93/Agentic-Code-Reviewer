"""
Versioned event contracts for the ADMADC event bus.

Every message flowing through RabbitMQ MUST conform to one of these contracts.
BaseEvent provides the envelope; specific event types define typed payloads.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    PLAN_REQUESTED = "plan.requested"
    PLAN_CREATED = "plan.created"
    TASK_ASSIGNED = "task.assigned"
    CODE_GENERATED = "code.generated"
    PR_REQUESTED = "pr.requested"
    PR_CREATED = "pr.created"
    MEMORY_STORE = "memory.store"
    MEMORY_QUERY = "memory.query"


class BaseEvent(BaseModel):
    """
    Canonical envelope for all events in the system.

    Determinism guarantees:
    - event_id is a UUID4 generated at creation time
    - idempotency_key is derived from (event_type + payload hash) so
      identical logical operations produce the same key
    - timestamp uses UTC with explicit timezone
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    version: str = "1.0"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    producer: str
    idempotency_key: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.idempotency_key:
            raw = f"{self.event_type.value}:{_stable_hash(self.payload)}"
            self.idempotency_key = hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Phase 1 pipeline payloads
# ---------------------------------------------------------------------------


class PlanRequestedPayload(BaseModel):
    user_prompt: str
    project_name: str
    repo_url: str = ""


class TaskSpec(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    file_path: str
    language: str = "python"


class PlanCreatedPayload(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_prompt: str
    tasks: list[TaskSpec]


class TaskAssignedPayload(BaseModel):
    plan_id: str
    task: TaskSpec


class CodeGeneratedPayload(BaseModel):
    plan_id: str
    task_id: str
    file_path: str
    code: str
    language: str = "python"


class PRRequestedPayload(BaseModel):
    plan_id: str
    repo_url: str
    branch_name: str
    files: list[CodeGeneratedPayload]
    commit_message: str


class PRCreatedPayload(BaseModel):
    plan_id: str
    pr_url: str
    pr_number: int
    branch_name: str


# ---------------------------------------------------------------------------
# Typed event constructors (factory helpers)
# ---------------------------------------------------------------------------


def plan_requested(
    producer: str, payload: PlanRequestedPayload
) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.PLAN_REQUESTED,
        producer=producer,
        payload=payload.model_dump(),
    )


def plan_created(producer: str, payload: PlanCreatedPayload) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.PLAN_CREATED,
        producer=producer,
        payload=payload.model_dump(),
    )


def task_assigned(producer: str, payload: TaskAssignedPayload) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.TASK_ASSIGNED,
        producer=producer,
        payload=payload.model_dump(),
    )


def code_generated(
    producer: str, payload: CodeGeneratedPayload
) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.CODE_GENERATED,
        producer=producer,
        payload=payload.model_dump(),
    )


def pr_requested(producer: str, payload: PRRequestedPayload) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.PR_REQUESTED,
        producer=producer,
        payload=payload.model_dump(),
    )


def pr_created(producer: str, payload: PRCreatedPayload) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.PR_CREATED,
        producer=producer,
        payload=payload.model_dump(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stable_hash(data: dict[str, Any]) -> str:
    """Produce a deterministic hash of a dict by sorting keys recursively."""
    import json

    normalized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()
