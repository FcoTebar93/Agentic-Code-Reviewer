import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { PlanDetail } from "../../types/planDetail";
import { buildLineDiff } from "./lineDiff";
import { translateGenericStatus } from "../../i18n/formatters";
import { CodePanel } from "../ui/CodePanel";
import { APP_META_TEXT, APP_BUTTON_TAB, cx } from "../ui/theme";

export function CodePreview({
  task,
}: {
  task: PlanDetail["tasks"][number] | null;
}) {
  const { t } = useTranslation();
  const [view, setView] = useState<"actual" | "original" | "diff">("actual");

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

  if (!hasCode) {
    return (
      <div className="app-divider mt-3 border-t pt-2">
        <p className="app-section-title mb-1 text-[10px]">
          {t("codePreview.title")}
        </p>
        <p className="app-empty-state text-[10px]">
          {t("codePreview.missing")}
        </p>
      </div>
    );
  }

  return (
    <div className="app-divider mt-3 border-t pt-2">
      <div className="flex items-center justify-between mb-1">
        <p className="app-section-title text-[10px]">
          {t("codePreview.title")} · {task.file_path || t("taskList.noPath")}
        </p>
        <div className="flex gap-1 text-[10px] font-mono">
          <button
            type="button"
            onClick={() => setView("actual")}
            className={cx(APP_BUTTON_TAB, "min-h-0 px-2 py-1 text-[10px]", view === "actual" && "app-button-tab-active")}
          >
            {t("codePreview.actual")}
          </button>
          {hasHistoryDiff && (
            <>
              <button
                type="button"
                onClick={() => setView("original")}
                className={cx(APP_BUTTON_TAB, "min-h-0 px-2 py-1 text-[10px]", view === "original" && "app-button-tab-active")}
              >
                {t("codePreview.original")}
              </button>
              <button
                type="button"
                onClick={() => setView("diff")}
                className={cx(APP_BUTTON_TAB, "min-h-0 px-2 py-1 text-[10px]", view === "diff" && "app-button-tab-active")}
              >
                {t("codePreview.diff")}
              </button>
            </>
          )}
        </div>
      </div>
      <div className={`${APP_META_TEXT} mb-1 flex items-center justify-between text-[10px]`}>
        <span>
          {task.language} · {t("codePreview.group", {
            group: translateGenericStatus(t, task.group_id || "root"),
          })}
        </span>
        <span>{t("codePreview.qaAttempt", { count: task.qa_attempt })}</span>
      </div>
      {view === "actual" && (
        <CodePanel code={latestCode} language={task.language || "text"} />
      )}
      {view === "original" && hasHistoryDiff && (
        <CodePanel code={originalCode} language={task.language || "text"} />
      )}
      {view === "diff" && hasHistoryDiff && (
        <CodePanel
          code={buildLineDiff(originalCode, latestCode)}
          language="diff"
        />
      )}
    </div>
  );
}
