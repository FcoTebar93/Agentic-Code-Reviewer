import { useState } from "react";
import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import { Badge } from "./ui/Badge";
import { usePlanDetail } from "../hooks/usePlanDetail";
import type { PlanDetail, SecurityOutcome } from "../types/planDetail";
import { ModuleList } from "./plan/ModuleList";
import { TaskList } from "./plan/TaskList";
import { CodePreview } from "./plan/CodePreview";
import { QAList } from "./plan/QAList";
import { SecuritySummary } from "./plan/SecuritySummary";
import { ManualReplan } from "./plan/ManualReplan";
import { PipelineTrace } from "./plan/PipelineTrace";
import type { ReplanPrefill } from "./plan/replanPrefill";
import { useTranslation } from "react-i18next";
import {
  translateGenericStatus,
  translatePipelineStatus,
  translateSeverity,
} from "../i18n/formatters";
import { APP_BUTTON_SECONDARY, APP_EMPTY_STATE, APP_META_TEXT, cx } from "./ui/theme";

export function PlanDetailCard({ planId }: { planId: string | null }) {
  const { t } = useTranslation();
  const { data, loading, error } = usePlanDetail(planId);

  if (!planId) {
    return (
      <Card>
        <SectionHeader>{t("planDetail.title")}</SectionHeader>
        <p className={APP_EMPTY_STATE}>
          {t("planDetail.empty")}
        </p>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <SectionHeader>{t("planDetail.title")}</SectionHeader>
        <p className={APP_META_TEXT}>{t("planDetail.loading")}</p>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <SectionHeader>{t("planDetail.title")}</SectionHeader>
        <p className="app-surface-soft border-amber-500/30 px-3 py-2 text-xs font-mono text-amber-300">
          {error ?? t("planDetail.loadingError")}
        </p>
      </Card>
    );
  }

  return <PlanDetailLoaded data={data} />;
}

function parseSecurityOutcome(
  o: PlanDetail["security_outcome"],
): SecurityOutcome | null {
  return Object.keys(o).length > 0 ? (o as SecurityOutcome) : null;
}

function PlanDetailLoaded({ data }: { data: PlanDetail }) {
  const { t } = useTranslation();
  const pipelineStatus = data.metrics.pipeline_status ?? "unknown";
  const qaHighSeverityCount = data.qa_outcomes.filter(
    (o) => o.severity_hint === "high" || o.severity_hint === "critical",
  ).length;

  const securityOutcome = parseSecurityOutcome(data.security_outcome);

  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [replanPrefill, setReplanPrefill] = useState<ReplanPrefill | null>(null);
  const filteredTasks = selectedModuleId
    ? data.tasks.filter((t) => (t.group_id || "root") === selectedModuleId)
    : data.tasks;

  const filteredQaOutcomes = selectedModuleId
    ? data.qa_outcomes.filter((o) => {
        const task = data.tasks.find((t) => t.task_id === o.task_id);
        const gid = task?.group_id || "root";
        return gid === selectedModuleId;
      })
    : data.qa_outcomes;

  const selectedTask =
    filteredTasks.find((t) => t.task_id === selectedTaskId) ??
    filteredTasks[0] ??
    null;

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

  return (
    <Card>
      <SectionHeader>{t("planDetail.title")}</SectionHeader>
      <div className="flex items-center gap-2 mb-2">
        <p
          className={cx(APP_META_TEXT, "flex-1 min-w-0 truncate")}
          title={data.plan_id}
        >
          plan_id: {data.plan_id.slice(0, 8)}…
        </p>
        <button
          type="button"
          className={cx(APP_BUTTON_SECONDARY, "min-h-0 shrink-0 px-2.5 py-1 text-[10px]")}
          onClick={() => void navigator.clipboard.writeText(data.plan_id)}
        >
          {t("planDetail.copyId")}
        </button>
      </div>
      <div className="flex items-center justify-between mb-2">
        <span className={APP_META_TEXT}>
          {t("planDetail.pipeline")}
        </span>
        <Badge className={statusBadgeClass}>
          {translatePipelineStatus(t, pipelineStatus)}
        </Badge>
      </div>
      <dl className="space-y-2 mb-3">
        <StatRow
          label={t("planDetail.tasks")}
          value={data.tasks.length}
        />
        <StatRow
          label={t("planDetail.qaIssuesHigh")}
          value={
            <span
              className={
                qaHighSeverityCount > 0
                  ? "text-[var(--color-danger-red)]"
                  : "text-[var(--color-polar-white)]"
              }
            >
              {qaHighSeverityCount}
            </span>
          }
          subtle
        />
        <StatRow
          label={t("planDetail.lastSecurityResult")}
          value={
            securityOutcome
              ? securityOutcome.approved
                ? translateGenericStatus(t, "approved")
                : translateGenericStatus(t, "blocked")
              : "—"
          }
          subtle
        />
        {securityOutcome && (
          <StatRow
            label={t("planDetail.securitySeverity")}
            value={translateSeverity(
              t,
              securityOutcome.severity_hint || "medium",
            )}
            subtle
          />
        )}
        {data.replans.items.length > 0 && (
          <StatRow
            label={t("planDetail.replansSuggested")}
            value={data.replans.items.length}
            subtle
          />
        )}
      </dl>

      {data.modules && data.modules.length > 0 && (
        <ModuleList
          modules={data.modules}
          selectedModuleId={selectedModuleId}
          onSelectModule={setSelectedModuleId}
        />
      )}

      <PipelineTrace
        rows={data.pipeline_trace}
        selectedTaskId={selectedTaskId}
      />

      <TaskList
        tasks={filteredTasks}
        qaOutcomes={filteredQaOutcomes}
        selectedTaskId={selectedTaskId}
        onSelectTask={setSelectedTaskId}
      />
      <CodePreview task={selectedTask} />
      <QAList
        qaOutcomes={filteredQaOutcomes}
        onSuggestReplan={(module, severity, issues, qaAttempt) => {
          const sev =
            severity === "critical" || severity === "high" ? severity : "medium";
          const cleanModule = module || "unknown";
          const reasonLines: string[] = [];
          reasonLines.push(
            t("planDetail.qaReplanReason", {
              module: cleanModule,
              attempt: qaAttempt,
              severity: translateSeverity(t, sev),
            }),
          );
          if (issues.length) {
            reasonLines.push(
              `${t("planDetail.detectedIssues")}:\n${issues
                .slice(0, 3)
                .map((i) => `- ${i}`)
                .join("\n")}`,
            );
          }
          const reason = reasonLines.join("\n\n");
          const suggestions = issues
            .slice(0, 5)
            .map((i) => t("planDetail.reviewAndCover", { issue: i }));

          setReplanPrefill({
            severity: sev,
            targetGroupIds: cleanModule ? [cleanModule] : [],
            reason,
            suggestions: suggestions.join("\n"),
          });
        }}
      />
      <SecuritySummary security={data.security_outcome} />
      <ManualReplan plan={data} prefill={replanPrefill ?? undefined} />
    </Card>
  );
}
