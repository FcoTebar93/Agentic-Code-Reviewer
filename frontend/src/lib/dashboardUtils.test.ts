import { describe, expect, it } from "vitest";
import { extractPlanId, sortByTimestampDesc } from "./dashboardUtils";
import type { BaseEvent } from "../types/events";

function ev(event_type: string, timestamp: string, payload: object): BaseEvent {
  return {
    event_id: `${event_type}-${timestamp}`,
    event_type,
    version: "1.0",
    timestamp,
    producer: "test",
    idempotency_key: "k",
    payload,
  } as BaseEvent;
}

describe("dashboardUtils", () => {
  it("extrae plan_id y fallback a original_plan_id", () => {
    expect(extractPlanId(ev("x", "2026-01-01T00:00:00Z", { plan_id: "p1" }))).toBe(
      "p1",
    );
    expect(
      extractPlanId(ev("x", "2026-01-01T00:00:00Z", { original_plan_id: "p2" })),
    ).toBe("p2");
    expect(extractPlanId(ev("x", "2026-01-01T00:00:00Z", {}))).toBeNull();
  });

  it("ordena eventos por timestamp descendente", () => {
    const events = [
      ev("a", "2026-01-01T00:00:01Z", { plan_id: "p1" }),
      ev("b", "2026-01-01T00:00:03Z", { plan_id: "p1" }),
      ev("c", "2026-01-01T00:00:02Z", { plan_id: "p1" }),
    ];
    const sorted = sortByTimestampDesc(events);
    expect(sorted.map((e) => e.event_type)).toEqual(["b", "c", "a"]);
  });
});

