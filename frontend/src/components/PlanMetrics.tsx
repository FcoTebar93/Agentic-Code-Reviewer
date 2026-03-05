import { useEffect, useState } from "react";
import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import { Badge } from "./ui/Badge";

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

  const pipelineStatus = metrics?.pipeline_status ?? "unknown";
  const statusBadgeClass =
    pipelineStatus === "approved"
      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/40"
      : pipelineStatus === "qa_failed"
        ? "bg-red-500/15 text-red-400 border-red-500/40"
        : pipelineStatus === "security_blocked"
          ? "bg-amber-500/15 text-amber-400 border-amber-500/40"
          : pipelineStatus === "in_progress"
            ? "bg-neutral-500/20 text-neutral-300 border-neutral-500/40"
            : "bg-neutral-500/15 text-neutral-400 border-neutral-600";

  if (!planId) {
    return (
      <Card>
        <SectionHeader>Plan Metrics</SectionHeader>
        <p className="text-neutral-500 text-xs font-mono">
          Run a plan or select a plan in the feed to see token usage and pipeline state.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <SectionHeader>Plan Metrics</SectionHeader>
      <p className="text-neutral-500 text-xs font-mono truncate mb-2" title={planId}>
        plan_id: {planId.slice(0, 8)}…
      </p>
      {loading && (
        <p className="text-neutral-500 text-xs font-mono">Loading…</p>
      )}
      {error && (
        <p className="text-amber-400 text-xs font-mono">{error}</p>
      )}
      {!loading && !error && metrics && (
        <dl className="space-y-2">
          <div className="flex items-center justify-between pt-0 pb-1 border-b border-neutral-800">
            <dt className="text-neutral-500 text-xs font-mono">Pipeline</dt>
            <dd>
              <Badge className={statusBadgeClass}>
                {pipelineStatus.replace(/_/g, " ")}
              </Badge>
            </dd>
          </div>
          <StatRow
            label="Total tokens"
            value={metrics.total_tokens.toLocaleString()}
          />
          <StatRow
            label="Prompt"
            value={metrics.total_prompt_tokens.toLocaleString()}
          />
          <StatRow
            label="Completion"
            value={metrics.total_completion_tokens.toLocaleString()}
          />
          <div className="pt-1 border-t border-neutral-800 mt-1">
            <StatRow
              label="Duration"
              value={formatDuration(metrics.duration_seconds)}
            />
          </div>
          <StatRow
            label="Retries (QA)"
            value={metrics.qa_retry_count ?? 0}
            subtle
          />
          <StatRow
            label="QA failed"
            value={
              <span
                className={`${
                  (metrics.qa_failed_count ?? 0) > 0
                    ? "text-red-400"
                    : "text-neutral-200"
                }`}
              >
                {metrics.qa_failed_count ?? 0}
              </span>
            }
            subtle
          />
          <StatRow
            label="Security blocked"
            value={
              <span
                className={`${
                  (metrics.security_blocked_count ?? 0) > 0
                    ? "text-amber-400"
                    : "text-neutral-200"
                }`}
              >
                {metrics.security_blocked_count ?? 0}
              </span>
            }
            subtle
          />
          <StatRow
            label="Replans"
            value={
              <>
                {metrics.replan_suggestions_count ?? 0}
                    {typeof metrics.replan_confirmed_count === "number" &&
                  metrics.replan_confirmed_count > 0 && (
                    <span className="text-neutral-500">
                      {" "}
                      (confirmed {metrics.replan_confirmed_count})
                    </span>
                  )}
              </>
            }
            subtle
          />
          {(metrics.first_event_at || metrics.last_event_at) && (
            <>
              <div className="pt-1 border-t border-neutral-800">
                <StatRow
                  label="First event"
                  value={
                    <span className="text-neutral-400 truncate max-w-[140px] inline-block">
                      {metrics.first_event_at
                        ? new Date(
                            metrics.first_event_at
                          ).toLocaleString(undefined, {
                            dateStyle: "short",
                            timeStyle: "short",
                          })
                        : "—"}
                    </span>
                  }
                  subtle
                />
              </div>
              <StatRow
                label="Last event"
                value={
                  <span className="text-neutral-400 truncate max-w-[140px] inline-block">
                    {metrics.last_event_at
                      ? new Date(
                          metrics.last_event_at
                        ).toLocaleString(undefined, {
                          dateStyle: "short",
                          timeStyle: "short",
                        })
                      : "—"}
                  </span>
                }
                subtle
              />
            </>
          )}
          {typeof metrics.estimated_cost_total_usd === "number" &&
            metrics.estimated_cost_total_usd > 0 && (
              <>
                <div className="pt-1 border-t border-neutral-800 mt-1">
                  <StatRow
                    label="Estimated cost (USD)"
                    value={formatUsd(metrics.estimated_cost_total_usd)}
                  />
                </div>
                <StatRow
                  label="Prompt / Completion"
                  value={
                    <>
                      {formatUsd(metrics.estimated_cost_prompt_usd)} /{" "}
                      {formatUsd(metrics.estimated_cost_completion_usd)}
                    </>
                  }
                  subtle
                />
              </>
            )}
          {metrics.by_service.length > 0 && (
            <div className="pt-2 border-t border-neutral-800">
              <dt className="text-neutral-500 text-xs font-mono mb-1.5">By service</dt>
              <dd className="space-y-1">
                {metrics.by_service.map((s: ByService) => (
                  <div
                    key={s.service}
                    className="flex justify-between text-xs font-mono"
                  >
                    <span className="text-neutral-400 truncate max-w-[140px]">
                      {s.service}
                    </span>
                    <span className="text-neutral-300 text-right">
                      {(s.total_tokens ??
                        s.prompt_tokens + s.completion_tokens
                      ).toLocaleString()}
                      {typeof s.estimated_cost_total_usd === "number" &&
                        s.estimated_cost_total_usd > 0 && (
                          <span className="block text-[10px] text-neutral-500">
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
    </Card>
  );
}
