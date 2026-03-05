import { useEffect, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { PipelineGraph } from "./components/PipelineGraph";
import { EventFeed } from "./components/EventFeed";
import { PlanForm } from "./components/PlanForm";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { PlanMetrics } from "./components/PlanMetrics";
import { Card, SectionHeader } from "./components/ui/Card";
import { StatRow } from "./components/ui/StatRow";
import { HeaderBar } from "./components/ui/HeaderBar";
import { PlanFilterChips } from "./components/ui/PlanFilterChips";
import type { BaseEvent } from "./types/events";

const WS_URL = import.meta.env.VITE_GATEWAY_WS_URL ?? "ws://localhost:8080/ws";
const HTTP_BASE = import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";

const STATUS_DOT: Record<string, string> = {
  connected: "bg-emerald-500",
  connecting: "bg-amber-400 animate-pulse",
  disconnected: "bg-red-500 animate-pulse",
};

function extractPlanId(evt: BaseEvent): string | null {
  const p =
    (evt.payload?.plan_id as string | undefined) ??
    (evt.payload?.original_plan_id as string | undefined);
  if (typeof p === "string" && p.trim()) return p.trim();
  return null;
}

function sortByTimestampDesc(events: BaseEvent[]): BaseEvent[] {
  return [...events].sort((a, b) => {
    const ta = Date.parse(a.timestamp);
    const tb = Date.parse(b.timestamp);
    if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
    return tb - ta;
  });
}

async function callApprovalEndpoint(
  approvalId: string,
  action: "approve" | "reject"
) {
  const resp = await fetch(
    `${HTTP_BASE}/api/approvals/${approvalId}/${action}`,
    { method: "POST" }
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status}: ${body}`);
  }
}

export default function App() {
  const { events, pendingApprovals, status } = useWebSocket(WS_URL);
  const [visibleEvents, setVisibleEvents] = useState<BaseEvent[]>(events);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [knownPlanIds, setKnownPlanIds] = useState<string[]>([]);

  const filteredEvents = sortByTimestampDesc(
    activePlanId === null
      ? visibleEvents
      : visibleEvents.filter((e) => extractPlanId(e) === activePlanId)
  );
  const latestEvent = filteredEvents[0] ?? null;

  const activePlanMode =
    activePlanId === null
      ? null
      : (() => {
          const planCreated = filteredEvents.find(
            (e) => e.event_type === "plan.created" && extractPlanId(e) === activePlanId
          );
          const mode = planCreated?.payload?.mode as string | undefined;
          return typeof mode === "string" && mode.trim() ? mode : null;
        })();

  // Mantener visibleEvents sincronizado con los eventos del socket
  useEffect(() => {
    setVisibleEvents(events);

    const ids: string[] = [];
    for (const ev of events) {
      const pid = extractPlanId(ev);
      if (pid && !ids.includes(pid)) {
        ids.push(pid);
      }
    }
    setKnownPlanIds(ids);
    setActivePlanId((prev) => {
      if (prev && ids.includes(prev)) return prev;
      if (prev === null && ids.length > 0) return ids[0];
      if (!prev && ids.length > 0) return ids[0];
      return prev;
    });
  }, [events]);

  return (
    <div className="min-h-screen bg-black text-neutral-50 flex flex-col">
      <HeaderBar
        title="ADMADC"
        subtitle="Autonomous Deterministic Multi-Agent Dev Company"
        right={
          <>
            {pendingApprovals.length > 0 && (
              <span className="bg-amber-500/20 text-amber-400 border border-amber-500/40 text-xs font-mono rounded-full px-2.5 py-0.5 animate-pulse">
                {pendingApprovals.length} approval{pendingApprovals.length !== 1 ? "s" : ""} pending
              </span>
            )}
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${STATUS_DOT[status]}`} />
              <span className="text-xs font-mono text-neutral-500">{status}</span>
            </div>
          </>
        }
      />

      <main className="flex-1 grid grid-cols-[1fr_380px] gap-4 p-4 min-h-0">
        <div className="flex flex-col gap-4 min-h-0">
          <PipelineGraph latestEvent={latestEvent} />
          <div className="flex-1 min-h-0">
            <div className="flex items-center justify-between mb-1 gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider">
                  Event Feed
                </span>
                <PlanFilterChips
                  planIds={knownPlanIds}
                  activePlanId={activePlanId}
                  onChange={setActivePlanId}
                />
              </div>
              {visibleEvents.length > 0 && (
                <button
                  onClick={() => {
                    setVisibleEvents([]);
                    setActivePlanId(null);
                    setKnownPlanIds([]);
                  }}
                  className="text-[10px] font-mono text-neutral-500 hover:text-neutral-300 transition-colors"
                >
                  clear logs
                </button>
              )}
            </div>
            <EventFeed events={filteredEvents} />
          </div>
        </div>

        <div className="flex flex-col gap-4 overflow-y-auto">
          <PlanForm />

          <PlanMetrics planId={activePlanId} />

          <ApprovalQueue
            approvals={pendingApprovals}
            onApprove={(id) => callApprovalEndpoint(id, "approve")}
            onReject={(id) => callApprovalEndpoint(id, "reject")}
          />

          <Card>
            <SectionHeader>Stats</SectionHeader>
            <dl className="space-y-2">
              <StatRow label="Total events" value={visibleEvents.length} />
              <StatRow
                label="Pending approvals"
                value={
                  <span
                    className={
                      pendingApprovals.length > 0
                        ? "text-amber-400"
                        : "text-neutral-200"
                    }
                  >
                    {pendingApprovals.length}
                  </span>
                }
              />
              {activePlanMode && (
                <StatRow
                  label="Active plan mode"
                  value={
                    <span
                      className={
                        activePlanMode === "ahorro"
                          ? "text-emerald-400"
                          : "text-neutral-300"
                      }
                    >
                      {activePlanMode}
                    </span>
                  }
                />
              )}
              <StatRow
                label="Last event"
                value={
                  <span className="text-neutral-200 truncate max-w-[180px] inline-block">
                    {latestEvent?.event_type ?? "—"}
                  </span>
                }
              />
              <StatRow
                label="Producer"
                value={latestEvent?.producer ?? "—"}
              />
            </dl>
          </Card>

          <Card>
            <SectionHeader>Quick Links</SectionHeader>
            <div className="space-y-1.5">
              {[
                { label: "Grafana", url: "http://localhost:3000" },
                { label: "Prometheus", url: "http://localhost:9090" },
                { label: "RabbitMQ UI", url: "http://localhost:15672" },
                { label: "Gateway API", url: "http://localhost:8080/docs" },
                { label: "Pending Approvals API", url: "http://localhost:8080/api/approvals" },
              ].map(({ label, url }) => (
                <a
                  key={label}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between text-xs font-mono text-neutral-400 hover:text-white transition-colors"
                >
                  <span>{label}</span>
                  <span className="text-neutral-600">↗</span>
                </a>
              ))}
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
