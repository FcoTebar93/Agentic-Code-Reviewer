import { useEffect, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { PipelineGraph } from "./components/PipelineGraph";
import { EventFeed } from "./components/EventFeed";
import { PlanForm } from "./components/PlanForm";
import { ApprovalQueue } from "./components/ApprovalQueue";

const WS_URL = import.meta.env.VITE_GATEWAY_WS_URL ?? "ws://localhost:8080/ws";
const HTTP_BASE = import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";

const STATUS_DOT: Record<string, string> = {
  connected: "bg-green-400",
  connecting: "bg-yellow-400 animate-pulse",
  disconnected: "bg-red-500 animate-pulse",
};

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
  const [visibleEvents, setVisibleEvents] = useState(events);
  const latestEvent = visibleEvents[0] ?? null;

  // Mantener visibleEvents sincronizado con los eventos del socket
  useEffect(() => {
    setVisibleEvents(events);
  }, [events]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between flex-none">
        <div className="flex items-center gap-3">
          <span className="text-indigo-400 font-mono font-bold text-lg tracking-tight">
            ADMADC
          </span>
          <span className="text-slate-600 text-sm font-mono">
            Autonomous Deterministic Multi-Agent Dev Company
          </span>
        </div>
        <div className="flex items-center gap-3">
          {pendingApprovals.length > 0 && (
            <span className="bg-orange-500 text-white text-xs font-mono rounded-full px-2.5 py-0.5 animate-pulse">
              {pendingApprovals.length} approval{pendingApprovals.length !== 1 ? "s" : ""} pending
            </span>
          )}
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${STATUS_DOT[status]}`} />
            <span className="text-xs font-mono text-slate-500">{status}</span>
          </div>
        </div>
      </header>

      {/* Main layout */}
      <main className="flex-1 grid grid-cols-[1fr_380px] gap-4 p-4 min-h-0">
        {/* Left column */}
        <div className="flex flex-col gap-4 min-h-0">
          <PipelineGraph latestEvent={latestEvent} />
          <div className="flex-1 min-h-0">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono text-slate-500">
                Event Feed
              </span>
              {visibleEvents.length > 0 && (
                <button
                  onClick={() => setVisibleEvents([])}
                  className="text-[10px] font-mono text-slate-500 hover:text-slate-200 transition-colors"
                >
                  clear logs
                </button>
              )}
            </div>
            <EventFeed events={visibleEvents} />
          </div>
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-4 overflow-y-auto">
          <PlanForm />

          {/* HITL Approval Queue */}
          <ApprovalQueue
            approvals={pendingApprovals}
            onApprove={(id) => callApprovalEndpoint(id, "approve")}
            onReject={(id) => callApprovalEndpoint(id, "reject")}
          />

          {/* Stats card */}
          <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
            <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3">
              Stats
            </h2>
            <dl className="space-y-2">
              <div className="flex justify-between">
                <dt className="text-slate-500 text-xs font-mono">Total events</dt>
                <dd className="text-slate-200 text-xs font-mono">
                  {visibleEvents.length}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500 text-xs font-mono">Pending approvals</dt>
                <dd className="text-xs font-mono">
                  <span
                    className={
                      pendingApprovals.length > 0
                        ? "text-orange-400"
                        : "text-slate-200"
                    }
                  >
                    {pendingApprovals.length}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500 text-xs font-mono">Last event</dt>
                <dd className="text-slate-200 text-xs font-mono truncate max-w-[180px]">
                  {latestEvent?.event_type ?? "—"}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500 text-xs font-mono">Producer</dt>
                <dd className="text-slate-200 text-xs font-mono">
                  {latestEvent?.producer ?? "—"}
                </dd>
              </div>
            </dl>
          </div>

          {/* Quick links */}
          <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
            <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3">
              Quick Links
            </h2>
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
                  className="flex items-center justify-between text-xs font-mono text-slate-400 hover:text-indigo-400 transition-colors"
                >
                  <span>{label}</span>
                  <span className="text-slate-600">↗</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
