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
import { APP_BUTTON_SECONDARY, APP_EMPTY_STATE, APP_META_TEXT, cx } from "../ui/theme";

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
      <div className="app-divider mt-3 border-t pt-2">
        <p className="app-section-title mb-1 text-[10px]">
          {t("pipelineTrace.title")}
        </p>
        <p className={`${APP_EMPTY_STATE} text-[10px]`}>
          {t("pipelineTrace.empty")}
        </p>
      </div>
    );
  }

  return (
    <div className="app-divider mt-3 border-t pt-2">
      <p className="app-section-title mb-1 text-[10px]">
        {t("pipelineTrace.title")} ({t("pipelineTrace.steps", { count: safeRows.length })})
      </p>
      <p className={`${APP_META_TEXT} mb-2 text-[10px]`}>
        {t("pipelineTrace.helper")}
      </p>
      <div className="app-surface-soft max-h-56 space-y-1 overflow-auto p-1.5 pr-1">
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
              className={`rounded px-3 py-2 text-[10px] font-mono transition-opacity ${
                highlight
                  ? "border border-[var(--color-electric-cyan)]/34 bg-[rgba(34,211,238,0.08)]"
                  : "app-surface-soft"
              } ${dim ? "opacity-45" : ""}`}
            >
              <div className="flex justify-between gap-2 items-start">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[var(--color-polar-white)]">
                    {translateEventType(t, row.event_type)}
                  </div>
                  <div className={`${APP_META_TEXT} mt-0.5 truncate`}>
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
                    <div className="app-muted-text mt-0.5 truncate">
                      {t("pipelineTrace.taskLabel", {
                        taskId: rowTask.slice(0, 8),
                      })}
                    </div>
                  )}
                  {extras ? (
                    <div className={`${APP_META_TEXT} mt-1 break-words whitespace-pre-wrap`}>
                      {extras}
                    </div>
                  ) : null}
                </div>
                {hasTools && (
                  <button
                    type="button"
                    onClick={() => toggle(key)}
                    className={cx(
                      APP_BUTTON_SECONDARY,
                      "min-h-0 shrink-0 px-2.5 py-1 text-[10px] text-[var(--color-electric-cyan)]",
                    )}
                  >
                    {open ? t("pipelineTrace.hideTools") : t("pipelineTrace.showTools")}
                  </button>
                )}
              </div>
              {hasTools && open && (
                <ul className="app-divider mt-2 space-y-1 border-t pt-2 text-[var(--color-silver-text)]/78">
                  {tools!.map((step, i) => (
                    <li key={`${key}-tool-${i}`} className="break-words">
                      <span
                        className={
                          step.ok === false
                            ? "text-[var(--color-danger-red)]"
                            : "text-[var(--color-electric-cyan)]"
                        }
                      >
                        {step.tool ?? "?"}
                      </span>
                      {step.llm_round != null ? (
                        <span className="app-muted-text">
                          {" "}
                          ({t("pipelineTrace.llmRound", {
                            count: step.llm_round,
                          })})
                        </span>
                      ) : null}
                      {step.args_preview ? (
                        <pre className="app-surface-soft mt-1 max-h-24 overflow-auto whitespace-pre-wrap px-2 py-1 text-[9px] text-[var(--color-silver-text)]/78">
                          {t("pipelineTrace.args", { value: step.args_preview })}
                        </pre>
                      ) : null}
                      {step.result_preview ? (
                        <pre className="app-surface-soft mt-1 max-h-28 overflow-auto whitespace-pre-wrap px-2 py-1 text-[9px] text-[var(--color-silver-text)]/78">
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
