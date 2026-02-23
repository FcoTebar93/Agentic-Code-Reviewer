// TypeScript mirror of shared/contracts/events.py
// Keep in sync when adding new EventType values in Python.

export type EventType =
  | "plan.requested"
  | "plan.created"
  | "task.assigned"
  | "code.generated"
  | "pr.requested"
  | "pr.created"
  | "pr.pending_approval"
  | "pr.human_approved"
  | "pr.human_rejected"
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

export interface PrApproval {
  approval_id: string;
  plan_id: string;
  branch_name: string;
  files_count: number;
  security_reasoning: string;
  pr_context: Record<string, unknown>;
  decision: string;
  reviewer: string;
}

// Messages sent by the gateway over WebSocket
export type WsMessage =
  | { type: "event"; event: BaseEvent }
  | { type: "history"; event: Record<string, unknown> }
  | { type: "approval"; approval: PrApproval }
  | { type: "approval_decided"; approval: PrApproval };

// Which service produced which event (for graph highlighting)
export const PRODUCER_FOR_EVENT: Record<EventType, string> = {
  "plan.requested": "meta_planner",
  "plan.created": "meta_planner",
  "task.assigned": "meta_planner",
  "code.generated": "dev_service",
  "pr.requested": "qa_service",
  "pr.created": "github_service",
  "pr.pending_approval": "gateway_service",
  "pr.human_approved": "gateway_service",
  "pr.human_rejected": "gateway_service",
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
  "pr.pending_approval": "#f97316",
  "pr.human_approved": "#10b981",
  "pr.human_rejected": "#ef4444",
  "memory.store": "#6b7280",
  "memory.query": "#6b7280",
  "qa.passed": "#10b981",
  "qa.failed": "#ef4444",
  "security.approved": "#10b981",
  "security.blocked": "#ef4444",
};

export const EVENT_LABELS: Record<EventType, string> = {
  "plan.requested": "Plan Requested",
  "plan.created": "Plan Created",
  "task.assigned": "Task Assigned",
  "code.generated": "Code Generated",
  "pr.requested": "PR Requested",
  "pr.created": "PR Created",
  "pr.pending_approval": "Awaiting Human Approval",
  "pr.human_approved": "Human Approved",
  "pr.human_rejected": "Human Rejected",
  "memory.store": "Memory Store",
  "memory.query": "Memory Query",
  "qa.passed": "QA Passed",
  "qa.failed": "QA Failed",
  "security.approved": "Security Approved",
  "security.blocked": "Security Blocked",
};
