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
import { APP_EMPTY_STATE, APP_META_TEXT } from "./ui/theme";

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
      ? "border-[var(--color-system-green)]/40 bg-[var(--color-system-green)]/14 text-[var(--color-system-green)]"
      : pipelineStatus === "qa_failed"
        ? "border-[var(--color-danger-red)]/40 bg-[var(--color-danger-red)]/14 text-[var(--color-danger-red)]"
        : pipelineStatus === "security_blocked"
          ? "border-[var(--color-warning-yellow)]/40 bg-[var(--color-warning-yellow)]/14 text-[var(--color-warning-yellow)]"
          : pipelineStatus === "in_progress"
            ? "border-[var(--color-neon-violet)]/34 bg-[var(--color-neon-violet)]/12 text-[var(--color-faded-rose)]"
            : "border-[var(--color-slate-border)] bg-[rgba(40,42,54,0.42)] text-[var(--color-silver-text)]/70";

  if (!planId) {
    return (
      <Card>
        <SectionHeader>{t("planMetrics.title")}</SectionHeader>
        <p className={APP_EMPTY_STATE}>
          {t("planMetrics.empty")}
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <SectionHeader>{t("planMetrics.title")}</SectionHeader>
      <p className={`${APP_META_TEXT} mb-2 truncate`} title={planId}>
        plan_id: {planId.slice(0, 8)}…
      </p>
      {loading && (
        <p className={APP_META_TEXT}>{t("planMetrics.loading")}</p>
      )}
      {error && (
        <p className="app-surface-soft border-amber-500/30 px-3 py-2 text-xs font-mono text-amber-300">{error}</p>
      )}
      {!loading && !error && metrics && (
        <dl className="space-y-2">
          <div className="app-divider flex items-center justify-between border-b pb-1 pt-0">
            <dt className={APP_META_TEXT}>
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
          <div className="app-divider mt-1 border-t pt-1">
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
                    ? "text-[var(--color-danger-red)]"
                    : "text-[var(--color-polar-white)]"
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
                    ? "text-[var(--color-warning-yellow)]"
                    : "text-[var(--color-polar-white)]"
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
                    <span className="app-meta-text">
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
              <div className="app-divider border-t pt-1">
                <StatRow
                  label={t("planMetrics.firstEvent")}
                  value={
                    <span className="inline-block max-w-[140px] truncate text-[var(--color-silver-text)]/78">
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
                  <span className="inline-block max-w-[140px] truncate text-[var(--color-silver-text)]/78">
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
                <div className="app-divider mt-1 border-t pt-1">
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
            <div className="app-divider border-t pt-2">
              <dt className="app-section-title mb-1.5 text-[10px]">
                {t("planMetrics.byService")}
              </dt>
              <dd className="space-y-1">
                {metrics.by_service.map((s: PlanMetricsByService) => (
                  <div
                    key={s.service}
                    className="app-surface-soft flex justify-between gap-3 px-3 py-2 text-xs font-mono"
                  >
                    <span className="max-w-[140px] truncate text-[var(--color-silver-text)]/78">
                      {s.service}
                    </span>
                    <span className="text-right text-[var(--color-polar-white)]">
                      {(s.total_tokens ??
                        s.prompt_tokens + s.completion_tokens
                      ).toLocaleString(locale)}
                      {typeof s.estimated_cost_total_usd === "number" &&
                        s.estimated_cost_total_usd > 0 && (
                          <span className="app-meta-text block text-[10px]">
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
