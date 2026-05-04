import { useMemo, useState } from "react";
import type { PipelineTraceRow } from "../../types/planDetail";

const TRACE_LABELS: Record<string, string> = {
  "plan.requested": "Plan solicitado",
  "plan.created": "Plan creado",
  "task.assigned": "Tarea asignada",
  "spec.generated": "Especificación generada",
  "code.generated": "Código generado (Dev)",
  "qa.passed": "QA aprobado",
  "qa.failed": "QA rechazado",
  "pr.requested": "PR solicitado",
  "security.approved": "Seguridad: aprobado",
  "security.blocked": "Seguridad: bloqueado",
  "pr.pending_approval": "PR pendiente de revisión humana",
  "pr.human_approved": "Humano: PR aprobado",
  "pr.human_rejected": "Humano: PR rechazado",
  "pr.created": "PR creado en GitHub",
  "pipeline.conclusion": "Fin del pipeline",
  "plan.revision_suggested": "Replan sugerido",
  "plan.revision_confirmed": "Replan confirmado",
};

function labelForEventType(t: string): string {
  return TRACE_LABELS[t] ?? t;
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso.slice(0, 19);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso.slice(0, 19);
  }
}

function detailLine(details: Record<string, unknown> | undefined): string | null {
  if (!details || typeof details !== "object") return null;
  const parts: string[] = [];
  if (typeof details.file_path === "string" && details.file_path)
    parts.push(details.file_path);
  if (details.task_count !== undefined)
    parts.push(`${details.task_count} tareas`);
  if (details.qa_retry) parts.push("reintento QA");
  if (typeof details.qa_attempt === "number")
    parts.push(`intento QA ${details.qa_attempt}`);
  if (typeof details.tool_steps_count === "number" && details.tool_steps_count > 0)
    parts.push(`${details.tool_steps_count} herramientas (Dev)`);
  if (typeof details.branch_name === "string" && details.branch_name)
    parts.push(`rama ${details.branch_name}`);
  if (details.approved === false) parts.push("no aprobado");
  if (details.approved === true) parts.push("aprobado");
  if (typeof details.issue_count === "number")
    parts.push(`${details.issue_count} issues`);
  if (typeof details.violation_count === "number")
    parts.push(`${details.violation_count} violaciones`);
  if (typeof details.files_changed_count === "number")
    parts.push(`${details.files_changed_count} archivos tocados`);
  if (!parts.length) return null;
  return parts.join(" · ");
}

export function PipelineTrace({
  rows,
  selectedTaskId,
}: {
  rows: PipelineTraceRow[] | undefined;
  selectedTaskId: string | null;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const safeRows = useMemo(() => (Array.isArray(rows) ? rows : []), [rows]);

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (!safeRows.length) {
    return (
      <div className="mt-3 border-t border-neutral-800 pt-2">
        <p className="text-neutral-500 text-[10px] font-mono mb-1">
          Trazabilidad del pipeline
        </p>
        <p className="text-[10px] text-neutral-600 font-mono">
          Sin eventos agregados todavía para este plan.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        Trazabilidad del pipeline ({safeRows.length} pasos)
      </p>
      <p className="text-[10px] text-neutral-600 font-mono mb-2">
        Orden cronológico. Las filas enlazadas a una tarea se resaltan al
        seleccionarla en la lista de tareas.
      </p>
      <div className="space-y-1 max-h-56 overflow-auto pr-1 border border-neutral-800 rounded-md p-1.5 bg-neutral-950/40">
        {safeRows.map((row, idx) => {
          const rowTask = row.task_id ?? null;
          const highlight =
            selectedTaskId &&
            rowTask &&
            rowTask === selectedTaskId;
          const dim =
            selectedTaskId && rowTask && rowTask !== selectedTaskId;
          const key =
            row.event_id ??
            `${row.event_type}-${row.created_at ?? ""}-${idx}`;
          const tools = row.tool_trace;
          const hasTools = Array.isArray(tools) && tools.length > 0;
          const open = expanded.has(key);
          const extras = detailLine(
            row.details as Record<string, unknown> | undefined,
          );

          return (
            <div
              key={key}
              className={`text-[10px] font-mono rounded border px-2 py-1.5 transition-opacity ${
                highlight
                  ? "border-sky-500/50 bg-sky-950/30"
                  : "border-neutral-800 bg-neutral-900/30"
              } ${dim ? "opacity-45" : ""}`}
            >
              <div className="flex justify-between gap-2 items-start">
                <div className="min-w-0 flex-1">
                  <div className="text-neutral-300 truncate">
                    {labelForEventType(row.event_type)}
                  </div>
                  <div className="text-neutral-500 truncate mt-0.5">
                    {formatWhen(row.created_at ?? null)}
                    {row.producer ? ` · ${row.producer}` : ""}
                  </div>
                  {rowTask && (
                    <div className="text-neutral-600 truncate mt-0.5">
                      task {rowTask.slice(0, 8)}…
                    </div>
                  )}
                  {extras ? (
                    <div className="text-neutral-500 mt-1 break-words whitespace-pre-wrap">
                      {extras}
                    </div>
                  ) : null}
                </div>
                {hasTools && (
                  <button
                    type="button"
                    onClick={() => toggle(key)}
                    className="shrink-0 text-sky-400 hover:text-sky-300 text-[10px]"
                  >
                    {open ? "Ocultar tools" : "Ver tools"}
                  </button>
                )}
              </div>
              {hasTools && open && (
                <ul className="mt-2 space-y-1 border-t border-neutral-800 pt-2 text-neutral-400">
                  {tools!.map((step, i) => (
                    <li key={`${key}-tool-${i}`} className="break-words">
                      <span
                        className={
                          step.ok === false ? "text-red-400" : "text-emerald-400/90"
                        }
                      >
                        {step.tool ?? "?"}
                      </span>
                      {step.llm_round != null ? (
                        <span className="text-neutral-600">
                          {" "}
                          (vuelta LLM {step.llm_round})
                        </span>
                      ) : null}
                      {step.args_preview ? (
                        <pre className="mt-0.5 text-[9px] text-neutral-500 whitespace-pre-wrap max-h-24 overflow-auto">
                          args {step.args_preview}
                        </pre>
                      ) : null}
                      {step.result_preview ? (
                        <pre className="mt-0.5 text-[9px] text-neutral-500 whitespace-pre-wrap max-h-28 overflow-auto">
                          {step.result_preview}
                        </pre>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
