import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import { Badge } from "./ui/Badge";
import { usePlanDetail } from "../hooks/usePlanDetail";

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

  const pipelineStatus = data.metrics.pipeline_status ?? "unknown";
  const qaHighSeverityCount = data.qa_outcomes.filter(
    (o) => o.severity_hint === "high" || o.severity_hint === "critical",
  ).length;

  const hasSecurity = Object.keys(data.security_outcome || {}).length > 0;

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
      <dl className="space-y-2">
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
            hasSecurity
              ? data.security_outcome.approved
                ? "approved"
                : "blocked"
              : "—"
          }
          subtle
        />
        {hasSecurity && (
          <StatRow
            label="Severidad seguridad"
            value={data.security_outcome.severity_hint || "medium"}
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
    </Card>
  );
}

