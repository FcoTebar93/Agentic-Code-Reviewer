import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { PipelineTraceRow } from "../../types/planDetail";
import {
  formatLocalizedDateTime,
  translateEventType,
  translateGenericStatus,
  translateSeverity,
} from "../../i18n/formatters";

function detailLine(
  details: Record<string, unknown> | undefined,
  t: TFunction<"common">,
): string | null {
  if (!details || typeof details !== "object") return null;
  const parts: string[] = [];
  if (typeof details.file_path === "string" && details.file_path)
    parts.push(details.file_path);
  if (details.task_count !== undefined)
    parts.push(t("pipelineTrace.steps", { count: details.task_count }));
  if (details.qa_retry) parts.push(t("planMetrics.qaRetries"));
  if (typeof details.qa_attempt === "number")
    parts.push(t("qaList.attempt", { count: details.qa_attempt }));
  if (typeof details.tool_steps_count === "number" && details.tool_steps_count > 0)
    parts.push(`${details.tool_steps_count} tools (Dev)`);
  if (typeof details.branch_name === "string" && details.branch_name)
    parts.push(`${t("approvalQueue.branch")} ${details.branch_name}`);
  if (details.approved === false) parts.push(t("values.no"));
  if (details.approved === true) parts.push(t("values.yes"));
  if (typeof details.issue_count === "number")
    parts.push(`${details.issue_count} issues`);
  if (typeof details.violation_count === "number")
    parts.push(`${details.violation_count} violations`);
  if (typeof details.files_changed_count === "number")
    parts.push(`${details.files_changed_count} files changed`);
  if (typeof details.severity_hint === "string" && details.severity_hint) {
    parts.push(
      `${t("qaList.severity")} ${translateSeverity(t, details.severity_hint)}`,
    );
  }
  if (typeof details.severity === "string" && details.severity) {
    parts.push(
      `${t("manualReplan.severity")} ${translateSeverity(t, details.severity)}`,
    );
  }
  if (typeof details.mode === "string" && details.mode) {
    parts.push(
      t("activePlan.mode", {
        mode: translateGenericStatus(t, details.mode),
      }),
    );
  }
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
  const { t, i18n } = useTranslation();
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
          {t("pipelineTrace.title")}
        </p>
        <p className="text-[10px] text-neutral-600 font-mono">
          {t("pipelineTrace.empty")}
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        {t("pipelineTrace.title")} ({t("pipelineTrace.steps", { count: safeRows.length })})
      </p>
      <p className="text-[10px] text-neutral-600 font-mono mb-2">
        {t("pipelineTrace.helper")}
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
            t,
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
                    {translateEventType(t, row.event_type)}
                  </div>
                  <div className="text-neutral-500 truncate mt-0.5">
                    {row.created_at
                      ? formatLocalizedDateTime(
                          row.created_at,
                          i18n.resolvedLanguage || i18n.language || "es",
                          {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          },
                        )
                      : "—"}
                    {row.producer ? ` · ${row.producer}` : ""}
                  </div>
                  {rowTask && (
                    <div className="text-neutral-600 truncate mt-0.5">
                      {t("pipelineTrace.taskLabel", {
                        taskId: rowTask.slice(0, 8),
                      })}
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
                    {open ? t("pipelineTrace.hideTools") : t("pipelineTrace.showTools")}
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
                          ({t("pipelineTrace.llmRound", {
                            count: step.llm_round,
                          })})
                        </span>
                      ) : null}
                      {step.args_preview ? (
                        <pre className="mt-0.5 text-[9px] text-neutral-500 whitespace-pre-wrap max-h-24 overflow-auto">
                          {t("pipelineTrace.args", { value: step.args_preview })}
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
