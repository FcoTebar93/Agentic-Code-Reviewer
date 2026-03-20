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
import type { ReplanPrefill } from "./plan/replanPrefill";

export function PlanDetailCard({ planId }: { planId: string | null }) {
  const { data, loading, error } = usePlanDetail(planId);

  if (!planId) {
    return (
      <Card>
        <SectionHeader>Plan Detail</SectionHeader>
        <p className="text-neutral-500 text-xs font-mono">
          Selecciona un plan en el feed para ver más detalles.
        </p>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <SectionHeader>Plan Detail</SectionHeader>
        <p className="text-neutral-500 text-xs font-mono">Cargando…</p>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <SectionHeader>Plan Detail</SectionHeader>
        <p className="text-amber-400 text-xs font-mono">
          {error ?? "No se pudo cargar el detalle del plan."}
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
      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/40"
      : pipelineStatus === "qa_failed"
        ? "bg-red-500/15 text-red-400 border-red-500/40"
        : pipelineStatus === "security_blocked"
          ? "bg-amber-500/15 text-amber-400 border-amber-500/40"
          : pipelineStatus === "in_progress"
            ? "bg-neutral-500/20 text-neutral-300 border-neutral-500/40"
            : "bg-neutral-500/15 text-neutral-400 border-neutral-600";

  return (
    <Card>
      <SectionHeader>Plan Detail</SectionHeader>
      <p
        className="text-neutral-500 text-xs font-mono truncate mb-2"
        title={data.plan_id}
      >
        plan_id: {data.plan_id.slice(0, 8)}…
      </p>
      <div className="flex items-center justify-between mb-2">
        <span className="text-neutral-500 text-xs font-mono">Pipeline</span>
        <Badge className={statusBadgeClass}>
          {pipelineStatus.replace(/_/g, " ")}
        </Badge>
      </div>
      <dl className="space-y-2 mb-3">
        <StatRow
          label="Tareas"
          value={data.tasks.length}
        />
        <StatRow
          label="QA issues (high+)"
          value={
            <span
              className={
                qaHighSeverityCount > 0 ? "text-red-400" : "text-neutral-200"
              }
            >
              {qaHighSeverityCount}
            </span>
          }
          subtle
        />
        <StatRow
          label="Último resultado seguridad"
          value={
            securityOutcome
              ? securityOutcome.approved
                ? "approved"
                : "blocked"
              : "—"
          }
          subtle
        />
        {securityOutcome && (
          <StatRow
            label="Severidad seguridad"
            value={securityOutcome.severity_hint || "medium"}
            subtle
          />
        )}
        {data.replans.items.length > 0 && (
          <StatRow
            label="Replans sugeridos"
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
            `Fallos de QA repetidos en módulo ${cleanModule} (intento ${qaAttempt}, severidad ${sev}).`,
          );
          if (issues.length) {
            reasonLines.push(
              `Ejemplos de issues detectados:\n${issues
                .slice(0, 3)
                .map((i) => `- ${i}`)
                .join("\n")}`,
            );
          }
          const reason = reasonLines.join("\n\n");
          const suggestions = issues
            .slice(0, 5)
            .map((i) => `Revisar y cubrir en tests: ${i}`);

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
