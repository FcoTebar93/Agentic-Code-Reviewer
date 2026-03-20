import type { BaseEvent } from "../types/events";

export const STATUS_DOT: Record<string, string> = {
  connected: "bg-emerald-500",
  connecting: "bg-amber-400 animate-pulse",
  disconnected: "bg-red-500 animate-pulse",
};

export function extractPlanId(evt: BaseEvent): string | null {
  const p =
    (evt.payload?.plan_id as string | undefined) ??
    (evt.payload?.original_plan_id as string | undefined);
  if (typeof p === "string" && p.trim()) return p.trim();
  return null;
}

export function sortByTimestampDesc(events: BaseEvent[]): BaseEvent[] {
  return [...events].sort((a, b) => {
    const ta = Date.parse(a.timestamp);
    const tb = Date.parse(b.timestamp);
    if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
    return tb - ta;
  });
}
