// TypeScript mirror of shared/contracts/events.py
// Keep in sync when adding new EventType values in Python.

export type EventType =
  | "plan.requested"
  | "plan.created"
  | "task.assigned"
  | "code.generated"
  | "pr.requested"
  | "pr.created"
  | "memory.store"
  | "memory.query"
  | "qa.passed"
  | "qa.failed"
  | "security.approved"
  | "security.blocked";

export interface BaseEvent {
  event_id: string;
  event_type: EventType;
  version: string;
  timestamp: string;
  producer: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
}

// Messages sent by the gateway over WebSocket
export type WsMessage =
  | { type: "event"; event: BaseEvent }
  | { type: "history"; event: Record<string, unknown> };

// Which service produced which event (for graph highlighting)
export const PRODUCER_FOR_EVENT: Record<EventType, string> = {
  "plan.requested": "meta_planner",
  "plan.created": "meta_planner",
  "task.assigned": "meta_planner",
  "code.generated": "dev_service",
  "pr.requested": "qa_service",
  "pr.created": "github_service",
  "memory.store": "memory_service",
  "memory.query": "memory_service",
  "qa.passed": "qa_service",
  "qa.failed": "qa_service",
  "security.approved": "security_service",
  "security.blocked": "security_service",
};

export const EVENT_COLORS: Record<EventType, string> = {
  "plan.requested": "#3b82f6",
  "plan.created": "#3b82f6",
  "task.assigned": "#8b5cf6",
  "code.generated": "#f59e0b",
  "pr.requested": "#06b6d4",
  "pr.created": "#10b981",
  "memory.store": "#6b7280",
  "memory.query": "#6b7280",
  "qa.passed": "#10b981",
  "qa.failed": "#ef4444",
  "security.approved": "#10b981",
  "security.blocked": "#ef4444",
};
