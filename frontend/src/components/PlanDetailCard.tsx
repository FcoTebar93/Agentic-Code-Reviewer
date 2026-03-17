import React from "react";
import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import { Badge } from "./ui/Badge";
import { usePlanDetail } from "../hooks/usePlanDetail";
import type { PlanDetail } from "../types/planDetail";

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

  const [selectedModuleId, setSelectedModuleId] = React.useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = React.useState<string | null>(null);
  const [replanPrefill, setReplanPrefill] = React.useState<{
    severity: string;
    targetGroupIds: string[];
    reason: string;
    suggestions: string;
  } | null>(null);
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

      {data.modules && data.modules.length > 0 && (
        <ModuleSummaryList
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
      <ManualReplanSection plan={data} prefill={replanPrefill ?? undefined} />
    </Card>
  );
}

const ModuleSummaryList: React.FC<{
  modules: NonNullable<PlanDetail["modules"]>;
  selectedModuleId: string | null;
  onSelectModule: (groupId: string | null) => void;
}> = ({ modules, selectedModuleId, onSelectModule }) => {
  if (!modules.length) return null;

  const maxQa = Math.max(...modules.map((m) => m.qa_failed_count || 0), 0);

  function severityColor(sev: string): string {
    if (sev === "critical") return "text-red-400";
    if (sev === "high") return "text-amber-300";
    if (sev === "medium") return "text-neutral-300";
    return "text-neutral-500";
  }

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        Módulos del plan
      </p>
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          onClick={() => onSelectModule(null)}
          className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
            selectedModuleId === null
              ? "bg-neutral-100 text-black border-neutral-100"
              : "bg-black text-neutral-300 border-neutral-700 hover:border-neutral-500"
          }`}
        >
          Todos
        </button>
        {modules.map((m) => {
          const active = selectedModuleId === m.group_id;
          const qaBadge =
            m.qa_failed_count > 0
              ? `${m.qa_failed_count} QA fail${m.qa_failed_count > 1 ? "s" : ""}`
              : "0 QA fails";
          const sevClass = severityColor(m.max_severity_hint || "low");

          const intensity =
            maxQa > 0 ? Math.min(1, m.qa_failed_count / maxQa) : 0;
          const bgHot =
            intensity > 0
              ? "bg-red-500/10 border-red-500/40"
              : "bg-neutral-900/40 border-neutral-700";

          return (
            <button
              key={m.group_id}
              type="button"
              onClick={() => onSelectModule(m.group_id)}
              className={`text-[10px] font-mono px-2 py-1 rounded-full border flex items-center gap-1 ${
                active
                  ? "bg-neutral-100 text-black border-neutral-100"
                  : bgHot + " text-neutral-200 hover:border-neutral-400"
              }`}
            >
              <span className="truncate max-w-[120px]">
                {m.group_id || "root"}
              </span>
              <span className="text-[9px] text-neutral-400">
                {m.tasks_count}t · {qaBadge}
              </span>
              <span className={`text-[9px] ${sevClass}`}>
                {m.max_severity_hint}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

const TaskList: React.FC<{
  tasks: PlanDetail["tasks"];
  qaOutcomes: PlanDetail["qa_outcomes"];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
}> = ({ tasks, qaOutcomes, selectedTaskId, onSelectTask }) => {
  if (!tasks.length) return null;

  const qaByTask = new Map(
    qaOutcomes.map((o) => [o.task_id, o] as const),
  );

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        Tareas por archivo
      </p>
      <div className="space-y-1 max-h-40 overflow-auto pr-1">
        {tasks.map((t) => {
          const qa = qaByTask.get(t.task_id);
          const severity =
            qa?.severity_hint && qa.severity_hint !== "medium"
              ? qa.severity_hint
              : null;
          const isActive = selectedTaskId === t.task_id;
          return (
            <div
              key={t.task_id}
              onClick={() => onSelectTask(t.task_id)}
              className={`text-xs border rounded px-2 py-1.5 flex flex-col gap-0.5 cursor-pointer ${
                isActive
                  ? "border-neutral-300 bg-neutral-900/60"
                  : "border-neutral-800 hover:border-neutral-600"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate max-w-[160px]">
                  {t.file_path || "(sin ruta)"}
                </span>
                <span className="text-[10px] text-neutral-500">
                  {t.status || "unknown"}
                </span>
              </div>
              <div className="text-[10px] text-neutral-500 flex justify-between gap-2">
                <span className="truncate max-w-[130px]">
                  {t.language} · {t.group_id || "root"}
                </span>
                <span>qa_attempt: {t.qa_attempt}</span>
              </div>
              {severity && (
                <div className="text-[10px] text-red-400">
                  QA severidad: {severity}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const CodePreview: React.FC<{ task: PlanDetail["tasks"][number] | null }> = ({
  task,
}) => {
  if (!task) return null;

  const hasCode = typeof task.code === "string" && task.code.trim().length > 0;

  const history = Array.isArray(task.code_history)
    ? [...task.code_history]
    : [];
  history.sort((a, b) => (a.qa_attempt ?? 0) - (b.qa_attempt ?? 0));
  const hasHistoryDiff = history.length >= 2;

  const originalCode =
    (hasHistoryDiff ? history[0]?.code : "") || task.code || "";
  const latestCode =
    (hasHistoryDiff ? history[history.length - 1]?.code : "") ||
    task.code ||
    "";

  const [view, setView] = React.useState<"actual" | "original" | "diff">(
    "actual",
  );

  if (!hasCode) {
    return (
      <div className="mt-3 border-t border-neutral-800 pt-2">
        <p className="text-neutral-500 text-[10px] font-mono mb-1">
          Code preview
        </p>
        <p className="text-[10px] text-neutral-600 font-mono">
          No hay snapshot de código almacenado para esta tarea (puede que sea
          anterior a esta versión del gateway).
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <div className="flex items-center justify-between mb-1">
        <p className="text-neutral-500 text-[10px] font-mono">
          Code preview · {task.file_path || "(sin ruta)"}
        </p>
        <div className="flex gap-1 text-[10px] font-mono">
          <button
            type="button"
            onClick={() => setView("actual")}
            className={`px-2 py-0.5 rounded border ${
              view === "actual"
                ? "border-neutral-300 text-neutral-100"
                : "border-neutral-700 text-neutral-500 hover:border-neutral-500"
            }`}
          >
            Actual
          </button>
          {hasHistoryDiff && (
            <>
              <button
                type="button"
                onClick={() => setView("original")}
                className={`px-2 py-0.5 rounded border ${
                  view === "original"
                    ? "border-neutral-300 text-neutral-100"
                    : "border-neutral-700 text-neutral-500 hover:border-neutral-500"
                }`}
              >
                Original
              </button>
              <button
                type="button"
                onClick={() => setView("diff")}
                className={`px-2 py-0.5 rounded border ${
                  view === "diff"
                    ? "border-neutral-300 text-neutral-100"
                    : "border-neutral-700 text-neutral-500 hover:border-neutral-500"
                }`}
              >
                Diff
              </button>
            </>
          )}
        </div>
      </div>
      <div className="mb-1 flex justify-between items-center text-[10px] text-neutral-500 font-mono">
        <span>
          {task.language} · group {task.group_id || "root"}
        </span>
        <span>qa_attempt: {task.qa_attempt}</span>
      </div>
      {view === "actual" && (
        <pre className="max-h-56 overflow-auto bg-black border border-neutral-800 rounded px-2 py-2 text-[11px] font-mono text-neutral-100 whitespace-pre">
          {latestCode}
        </pre>
      )}
      {view === "original" && hasHistoryDiff && (
        <pre className="max-h-56 overflow-auto bg-black border border-neutral-800 rounded px-2 py-2 text-[11px] font-mono text-neutral-100 whitespace-pre">
          {originalCode}
        </pre>
      )}
      {view === "diff" && hasHistoryDiff && (
        <pre className="max-h-56 overflow-auto bg-black border border-neutral-800 rounded px-2 py-2 text-[11px] font-mono text-neutral-100 whitespace-pre">
          {buildLineDiff(originalCode, latestCode)}
        </pre>
      )}
    </div>
  );
};

function buildLineDiff(original: string, latest: string): string {
  const origLines = original.split("\n");
  const newLines = latest.split("\n");
  const maxLen = Math.max(origLines.length, newLines.length);
  const out: string[] = [];

  for (let i = 0; i < maxLen; i++) {
    const o = origLines[i] ?? "";
    const n = newLines[i] ?? "";
    if (o === n) {
      out.push("  " + o);
    } else {
      if (o) out.push("- " + o);
      if (n) out.push("+ " + n);
    }
  }

  return out.join("\n");
}

const QAList: React.FC<{
  qaOutcomes: PlanDetail["qa_outcomes"];
  onSuggestReplan: (
    module: string,
    severity: string,
    issues: string[],
    qaAttempt: number,
  ) => void;
}> = ({ qaOutcomes, onSuggestReplan }) => {
  if (!qaOutcomes.length) return null;
  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        QA outcomes
      </p>
      <div className="space-y-1 max-h-40 overflow-auto pr-1">
        {qaOutcomes.map((o) => (
          <div
            key={o.task_id}
            className="text-xs border border-neutral-800 rounded px-2 py-1.5"
          >
            <div className="flex justify-between text-[10px] text-neutral-500 mb-0.5">
              <span>
                task {o.task_id.slice(0, 8)} · módulo {o.module || "unknown"}
              </span>
              <span>intento {o.qa_attempt}</span>
            </div>
            <div className="text-[10px] mb-0.5">
              severidad:{" "}
              <span className="font-medium">{o.severity_hint}</span>
            </div>
            <div className="flex justify-end mb-1">
              {o.module && (
                <button
                  type="button"
                  onClick={() =>
                    onSuggestReplan(
                      o.module,
                      o.severity_hint,
                      o.issues ?? [],
                      o.qa_attempt,
                    )
                  }
                  className="text-[10px] font-mono px-2 py-0.5 rounded border border-amber-500/60 text-amber-300 hover:bg-amber-500/10 transition-colors"
                >
                  Replan módulo
                </button>
              )}
            </div>
            <ul className="list-disc ml-4 text-[10px] space-y-0.5">
              {o.issues.slice(0, 3).map((iss, idx) => (
                <li key={idx}>{iss}</li>
              ))}
              {o.issues.length > 3 && (
                <li>… {o.issues.length - 3} issues más.</li>
              )}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
};

const SecuritySummary: React.FC<{
  security: PlanDetail["security_outcome"];
}> = ({ security }) => {
  const hasSecurity = Object.keys(security || {}).length > 0;
  if (!hasSecurity) return null;
  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        Seguridad
      </p>
      <div className="text-xs space-y-0.5">
        <div>
          Aprobado:{" "}
          <span className="font-medium">
            {security.approved ? "sí" : "no"}
          </span>{" "}
          · severidad:{" "}
          <span className="font-medium">
            {security.severity_hint || "medium"}
          </span>
        </div>
        <div>
          Files escaneados: <span>{security.files_scanned}</span>
        </div>
        {security.violations && security.violations.length > 0 && (
          <ul className="list-disc ml-4 text-[10px] space-y-0.5">
            {security.violations.slice(0, 4).map((v, idx) => (
              <li key={idx}>{v}</li>
            ))}
            {security.violations.length > 4 && (
              <li>… {security.violations.length - 4} violaciones más.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
};

const HTTP_BASE =
  import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";

const ManualReplanSection: React.FC<{
  plan: PlanDetail;
  prefill?: {
    severity: string;
    targetGroupIds: string[];
    reason: string;
    suggestions: string;
  };
}> = ({ plan, prefill }) => {
  const [severity, setSeverity] = React.useState<string>("medium");
  const [selectedGroups, setSelectedGroups] = React.useState<string[]>([]);
  const [reason, setReason] = React.useState<string>("");
  const [suggestions, setSuggestions] = React.useState<string>("");
  const [submitting, setSubmitting] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!prefill) return;
    setSeverity(prefill.severity || "medium");
    setSelectedGroups(
      Array.isArray(prefill.targetGroupIds) ? prefill.targetGroupIds : [],
    );
    setReason(prefill.reason || "");
    setSuggestions(prefill.suggestions || "");
    setMessage(
      "Formulario de replan pre-rellenado desde QA (revisa y confirma si tiene sentido).",
    );
  }, [prefill?.severity, prefill?.reason, prefill?.suggestions, prefill?.targetGroupIds]);

  const uniqueGroups = Array.from(
    new Set(
      plan.tasks
        .map((t) => t.group_id)
        .filter((g) => typeof g === "string" && g.trim().length > 0),
    ),
  ).slice(0, 10);

  if (!plan.plan_id || uniqueGroups.length === 0) {
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setMessage(null);

    try {
      const body = {
        original_plan_id: plan.plan_id,
        severity,
        reason:
          reason.trim() ||
          "Manual replan triggered from UI based on QA/Security outcomes.",
        summary: `Manual replanning requested for plan ${plan.plan_id.slice(
          0,
          8,
        )}`,
        suggestions: suggestions
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        target_group_ids: selectedGroups.length ? selectedGroups : uniqueGroups,
      };
      const resp = await fetch(`${HTTP_BASE}/api/replan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`${resp.status}: ${txt}`);
      }
      setMessage("Replan solicitado correctamente (esperando nuevo plan).");
      setReason("");
      setSuggestions("");
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Error al solicitar replan.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function toggleGroup(groupId: string) {
    setSelectedGroups((prev) =>
      prev.includes(groupId)
        ? prev.filter((g) => g !== groupId)
        : [...prev, groupId],
    );
  }

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        Manual replan
      </p>
      <form onSubmit={handleSubmit} className="space-y-2 text-xs">
        <div className="flex gap-2 items-center">
          <label className="text-[10px] text-neutral-500 font-mono">
            Severidad
          </label>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="bg-black border border-neutral-700 rounded px-2 py-1 text-[11px] font-mono text-neutral-100 flex-1"
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
        </div>
        <div>
          <p className="text-[10px] text-neutral-500 font-mono mb-1">
            Grupos objetivo (módulos)
          </p>
          <div className="flex flex-wrap gap-1">
            {uniqueGroups.map((g) => {
              const active = selectedGroups.includes(g);
              return (
                <button
                  key={g}
                  type="button"
                  onClick={() => toggleGroup(g)}
                  className={`text-[10px] px-2 py-0.5 rounded-full border font-mono ${
                    active
                      ? "bg-neutral-100 text-black border-neutral-100"
                      : "bg-black text-neutral-300 border-neutral-700 hover:border-neutral-500"
                  }`}
                >
                  {g}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <label className="block text-[10px] text-neutral-500 font-mono mb-1">
            Motivo (opcional)
          </label>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-100 placeholder:text-neutral-600 resize-none"
            placeholder="Ej: Fallos repetidos de QA en estos módulos, necesito reforzar tests y validación..."
          />
        </div>
        <div>
          <label className="block text-[10px] text-neutral-500 font-mono mb-1">
            Sugerencias (una por línea, opcional)
          </label>
          <textarea
            rows={2}
            value={suggestions}
            onChange={(e) => setSuggestions(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-100 placeholder:text-neutral-600 resize-none"
            placeholder="- Añadir tests de validación de formularios&#10;- Endurecer controles de acceso en endpoints sensibles"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-neutral-100 hover:bg-neutral-300 disabled:bg-neutral-800 disabled:text-neutral-500 text-black font-mono text-[11px] font-medium rounded px-3 py-1.5 transition-colors"
        >
          {submitting ? "Solicitando replan..." : "Solicitar replan para este plan"}
        </button>
        {message && (
          <p className="text-[10px] font-mono mt-1 text-neutral-400">
            {message}
          </p>
        )}
      </form>
    </div>
  );
};



