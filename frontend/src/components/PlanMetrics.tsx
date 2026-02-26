import { useEffect, useState } from "react";

const HTTP_BASE = import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";

interface ByService {
  service: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens?: number;
  estimated_cost_prompt_usd?: number;
  estimated_cost_completion_usd?: number;
  estimated_cost_total_usd?: number;
}

interface PlanMetricsPayload {
  plan_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  estimated_cost_prompt_usd?: number;
  estimated_cost_completion_usd?: number;
  estimated_cost_total_usd?: number;
  pipeline_status?: string;
  first_event_at?: string | null;
  last_event_at?: string | null;
  duration_seconds?: number;
  qa_retry_count?: number;
  qa_failed_count?: number;
  security_blocked_count?: number;
  replan_suggestions_count?: number;
  replan_confirmed_count?: number;
  by_service: ByService[];
}
 
export function PlanMetrics({ planId }: { planId: string | null }) {
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

  const formatUsd = (value: number | undefined) => {
    if (value === undefined) return "—";
    if (!Number.isFinite(value)) return "—";
    return `$${value.toFixed(4)}`;
  };

  const formatDuration = (seconds?: number) => {
    if (seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) {
      return "—";
    }
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    if (mins < 60) return `${mins}m ${secs}s`;
    const hours = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hours}h ${remMins}m`;
  };

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
          {/* Pipeline health */}
          <div className="flex justify-between pt-1 border-t border-slate-700 mt-1">
            <dt className="text-slate-500 text-xs font-mono">Pipeline status</dt>
            <dd className="text-slate-200 text-xs font-mono">
              {metrics.pipeline_status ?? "unknown"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 text-xs font-mono">Duration</dt>
            <dd className="text-slate-200 text-xs font-mono">
              {formatDuration(metrics.duration_seconds)}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 text-[10px] font-mono">Retries (QA)</dt>
            <dd className="text-slate-200 text-[10px] font-mono">
              {metrics.qa_retry_count ?? 0}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 text-[10px] font-mono">Replans</dt>
            <dd className="text-slate-200 text-[10px] font-mono">
              {metrics.replan_suggestions_count ?? 0}
              {typeof metrics.replan_confirmed_count === "number" &&
                metrics.replan_confirmed_count > 0 && (
                  <span className="text-slate-500"> (confirmed {metrics.replan_confirmed_count})</span>
                )}
            </dd>
          </div>
          {typeof metrics.estimated_cost_total_usd === "number" &&
            metrics.estimated_cost_total_usd > 0 && (
              <>
                <div className="flex justify-between pt-1 border-t border-slate-700 mt-1">
                  <dt className="text-slate-500 text-xs font-mono">
                    Estimated cost (USD)
                  </dt>
                  <dd className="text-slate-200 text-xs font-mono">
                    {formatUsd(metrics.estimated_cost_total_usd)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500 text-[10px] font-mono">
                    Prompt / Completion
                  </dt>
                  <dd className="text-slate-200 text-[10px] font-mono">
                    {formatUsd(metrics.estimated_cost_prompt_usd)} /{" "}
                    {formatUsd(metrics.estimated_cost_completion_usd)}
                  </dd>
                </div>
              </>
            )}
          {metrics.by_service.length > 0 && (
            <div className="pt-2 border-t border-slate-700">
              <dt className="text-slate-500 text-xs font-mono mb-1.5">By service</dt>
              <dd className="space-y-1">
                {metrics.by_service.map((s: ByService) => (
                  <div
                    key={s.service}
                    className="flex justify-between text-xs font-mono"
                  >
                    <span className="text-slate-400 truncate max-w-[140px]">
                      {s.service}
                    </span>
                    <span className="text-slate-300 text-right">
                      {(s.total_tokens ??
                        s.prompt_tokens + s.completion_tokens
                      ).toLocaleString()}
                      {typeof s.estimated_cost_total_usd === "number" &&
                        s.estimated_cost_total_usd > 0 && (
                          <span className="block text-[10px] text-slate-500">
                            {formatUsd(s.estimated_cost_total_usd)}
                          </span>
                        )}
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
