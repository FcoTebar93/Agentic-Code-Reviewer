import { useEffect, useState } from "react";

const HTTP_BASE = import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";

interface ByService {
  service: string;
  prompt_tokens: number;
  completion_tokens: number;
}

interface PlanMetricsPayload {
  plan_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  by_service: ByService[];
}

interface EventLike {
  payload?: Record<string, unknown>;
}

function getLatestPlanIdFromEvents(events: EventLike[]): string | null {
  for (const ev of events) {
    const planId = ev.payload?.plan_id ?? ev.payload?.original_plan_id;
    if (typeof planId === "string" && planId.trim()) return planId.trim();
  }
  return null;
}

export function PlanMetrics({ events }: { events: EventLike[] }) {
  const planId = getLatestPlanIdFromEvents(events);
  const [metrics, setMetrics] = useState<PlanMetricsPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!planId) {
      setMetrics(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${HTTP_BASE}/api/plan_metrics/${encodeURIComponent(planId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}: ${r.statusText}`);
        return r.json();
      })
      .then((data: PlanMetricsPayload) => {
        if (!cancelled) {
          setMetrics(data);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setMetrics(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [planId]);

  if (!planId) {
    return (
      <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
        <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3">
          Plan Metrics
        </h2>
        <p className="text-slate-500 text-xs font-mono">
          Run a plan to see token usage per plan.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
      <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3">
        Plan Metrics
      </h2>
      <p className="text-slate-500 text-xs font-mono truncate mb-2" title={planId}>
        plan_id: {planId.slice(0, 8)}…
      </p>
      {loading && (
        <p className="text-slate-500 text-xs font-mono">Loading…</p>
      )}
      {error && (
        <p className="text-amber-400 text-xs font-mono">{error}</p>
      )}
      {!loading && !error && metrics && (
        <dl className="space-y-2">
          <div className="flex justify-between">
            <dt className="text-slate-500 text-xs font-mono">Total tokens</dt>
            <dd className="text-slate-200 text-xs font-mono">
              {metrics.total_tokens.toLocaleString()}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 text-xs font-mono">Prompt</dt>
            <dd className="text-slate-200 text-xs font-mono">
              {metrics.total_prompt_tokens.toLocaleString()}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 text-xs font-mono">Completion</dt>
            <dd className="text-slate-200 text-xs font-mono">
              {metrics.total_completion_tokens.toLocaleString()}
            </dd>
          </div>
          {metrics.by_service.length > 0 && (
            <div className="pt-2 border-t border-slate-700">
              <dt className="text-slate-500 text-xs font-mono mb-1.5">By service</dt>
              <dd className="space-y-1">
                {metrics.by_service.map((s) => (
                  <div
                    key={s.service}
                    className="flex justify-between text-xs font-mono"
                  >
                    <span className="text-slate-400 truncate max-w-[140px]">
                      {s.service}
                    </span>
                    <span className="text-slate-300">
                      {(s.prompt_tokens + s.completion_tokens).toLocaleString()}
                    </span>
                  </div>
                ))}
              </dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}
