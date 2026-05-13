import type { TFunction } from "i18next";
import type { EventType } from "../types/events";

const EVENT_KEY_MAP: Record<EventType, string> = {
  "plan.requested": "planRequested",
  "plan.created": "planCreated",
  "task.assigned": "taskAssigned",
  "code.generated": "codeGenerated",
  "spec.generated": "specGenerated",
  "pr.requested": "prRequested",
  "pr.created": "prCreated",
  "pr.pending_approval": "prPendingApproval",
  "pr.human_approved": "prHumanApproved",
  "pr.human_rejected": "prHumanRejected",
  "memory.store": "memoryStore",
  "memory.query": "memoryQuery",
  "qa.passed": "qaPassed",
  "qa.failed": "qaFailed",
  "security.approved": "securityApproved",
  "security.blocked": "securityBlocked",
  "pipeline.conclusion": "pipelineConclusion",
  "plan.revision_suggested": "planRevisionSuggested",
  "plan.revision_confirmed": "planRevisionConfirmed",
  "metrics.tokens_used": "metricsTokensUsed",
};

export function translateEventType(
  t: TFunction<"common">,
  eventType: string,
): string {
  const key = EVENT_KEY_MAP[eventType as EventType];
  if (!key) return eventType;
  return t(`events.labels.${key}`);
}

export function translatePipelineStatus(
  t: TFunction<"common">,
  status: string,
): string {
  return t(`statuses.pipeline.${status}`, {
    defaultValue: status.replace(/_/g, " "),
  });
}

export function translateConnectionStatus(
  t: TFunction<"common">,
  status: string,
): string {
  return t(`statuses.connection.${status}`, { defaultValue: status });
}

export function translateSeverity(
  t: TFunction<"common">,
  severity: string,
): string {
  return t(`statuses.severity.${severity}`, { defaultValue: severity });
}

export function translateGenericStatus(
  t: TFunction<"common">,
  value: string,
): string {
  return t(`statuses.generic.${value}`, { defaultValue: value });
}

export function formatLocalizedTime(
  iso: string,
  language: string,
): string {
  try {
    return new Date(iso).toLocaleTimeString(language, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function formatLocalizedDateTime(
  iso: string | null | undefined,
  language: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!iso) return "—";
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString(language, options);
  } catch {
    return iso;
  }
}
