import { useEffect, useState } from "react";
import { getJson } from "../api/api";
import type { PlanMetrics as PlanMetricsPayload, PlanMetricsByService } from "../types/planDetail";
import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import { Badge } from "./ui/Badge";
import { useTranslation } from "react-i18next";
import {
  formatLocalizedDateTime,
  translatePipelineStatus,
} from "../i18n/formatters";

export function PlanMetrics({ planId }: { planId: string | null }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage || i18n.language || "es";
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
    getJson<PlanMetricsPayload>(
      `/api/plan_metrics/${encodeURIComponent(planId)}`,
    )
      .then((data) => {
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
      return t("planMetrics.noValue");
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
        <SectionHeader>{t("planMetrics.title")}</SectionHeader>
        <p className="text-neutral-500 text-xs font-mono">
          {t("planMetrics.empty")}
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <SectionHeader>{t("planMetrics.title")}</SectionHeader>
      <p className="text-neutral-500 text-xs font-mono truncate mb-2" title={planId}>
        plan_id: {planId.slice(0, 8)}…
      </p>
      {loading && (
        <p className="text-neutral-500 text-xs font-mono">{t("planMetrics.loading")}</p>
      )}
      {error && (
        <p className="text-amber-400 text-xs font-mono">{error}</p>
      )}
      {!loading && !error && metrics && (
        <dl className="space-y-2">
          <div className="flex items-center justify-between pt-0 pb-1 border-b border-neutral-800">
            <dt className="text-neutral-500 text-xs font-mono">
              {t("planMetrics.pipeline")}
            </dt>
            <dd>
              <Badge className={statusBadgeClass}>
                {translatePipelineStatus(t, pipelineStatus)}
              </Badge>
            </dd>
          </div>
          <StatRow
            label={t("planMetrics.totalTokens")}
            value={metrics.total_tokens.toLocaleString(locale)}
          />
          <StatRow
            label={t("planMetrics.prompt")}
            value={metrics.total_prompt_tokens.toLocaleString(locale)}
          />
          <StatRow
            label={t("planMetrics.completion")}
            value={metrics.total_completion_tokens.toLocaleString(locale)}
          />
          <div className="pt-1 border-t border-neutral-800 mt-1">
            <StatRow
              label={t("planMetrics.duration")}
              value={formatDuration(metrics.duration_seconds)}
            />
          </div>
          <StatRow
            label={t("planMetrics.qaRetries")}
            value={metrics.qa_retry_count ?? 0}
            subtle
          />
          <StatRow
            label={t("planMetrics.qaFailed")}
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
            label={t("planMetrics.securityBlocked")}
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
            label={t("planMetrics.replans")}
            value={
              <>
                {metrics.replan_suggestions_count ?? 0}
                {typeof metrics.replan_confirmed_count === "number" &&
                  metrics.replan_confirmed_count > 0 && (
                    <span className="text-neutral-500">
                      {" "}
                      ({t("planMetrics.confirmed", {
                        count: metrics.replan_confirmed_count,
                      })})
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
                  label={t("planMetrics.firstEvent")}
                  value={
                    <span className="text-neutral-400 truncate max-w-[140px] inline-block">
                      {metrics.first_event_at
                        ? formatLocalizedDateTime(
                            metrics.first_event_at,
                            locale,
                            {
                              dateStyle: "short",
                              timeStyle: "short",
                            },
                          )
                        : t("planMetrics.noValue")}
                    </span>
                  }
                  subtle
                />
              </div>
              <StatRow
                label={t("planMetrics.lastEvent")}
                value={
                  <span className="text-neutral-400 truncate max-w-[140px] inline-block">
                    {metrics.last_event_at
                      ? formatLocalizedDateTime(
                          metrics.last_event_at,
                          locale,
                          {
                            dateStyle: "short",
                            timeStyle: "short",
                          },
                        )
                      : t("planMetrics.noValue")}
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
                    label={t("planMetrics.estimatedCost")}
                    value={formatUsd(metrics.estimated_cost_total_usd)}
                  />
                </div>
                <StatRow
                  label={t("planMetrics.promptCompletion")}
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
              <dt className="text-neutral-500 text-xs font-mono mb-1.5">
                {t("planMetrics.byService")}
              </dt>
              <dd className="space-y-1">
                {metrics.by_service.map((s: PlanMetricsByService) => (
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
                      ).toLocaleString(locale)}
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
