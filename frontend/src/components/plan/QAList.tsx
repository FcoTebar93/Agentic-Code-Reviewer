import type { PlanDetail } from "../../types/planDetail";
import { useTranslation } from "react-i18next";
import { translateSeverity } from "../../i18n/formatters";
import { APP_BUTTON_SECONDARY, APP_META_TEXT, cx } from "../ui/theme";

export function QAList({
  qaOutcomes,
  onSuggestReplan,
}: {
  qaOutcomes: PlanDetail["qa_outcomes"];
  onSuggestReplan: (
    module: string,
    severity: string,
    issues: string[],
    qaAttempt: number,
  ) => void;
}) {
  const { t } = useTranslation();
  if (!qaOutcomes.length) return null;
  return (
    <div className="app-divider mt-3 border-t pt-2">
      <p className="app-section-title mb-1 text-[10px]">
        {t("qaList.title")}
      </p>
      <div className="space-y-1 max-h-40 overflow-auto pr-1">
        {qaOutcomes.map((o) => (
          <div
            key={o.task_id}
            className="app-surface-soft px-3 py-2 text-xs"
          >
            <div className={`${APP_META_TEXT} mb-0.5 flex justify-between text-[10px]`}>
              <span>
                {t("qaList.taskModule", {
                  taskId: o.task_id.slice(0, 8),
                  module: o.module || t("values.unknown"),
                })}
              </span>
              <span>{t("qaList.attempt", { count: o.qa_attempt })}</span>
            </div>
            <div className="mb-0.5 text-[10px] text-[var(--color-silver-text)]">
              {t("qaList.severity")}:{" "}
              <span className="font-medium text-[var(--color-danger-red)]">
                {translateSeverity(t, o.severity_hint)}
              </span>
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
                  className={cx(
                    APP_BUTTON_SECONDARY,
                    "min-h-0 border-amber-500/40 px-2.5 py-1 text-[10px] text-amber-300 hover:bg-amber-500/10",
                  )}
                >
                  {t("qaList.replanModule")}
                </button>
              )}
            </div>
            <ul className="ml-4 list-disc space-y-0.5 text-[10px] text-[var(--color-silver-text)]/78">
              {o.issues.slice(0, 3).map((iss, idx) => (
                <li key={idx}>{iss}</li>
              ))}
              {o.issues.length > 3 && (
                <li>{t("qaList.moreIssues", { count: o.issues.length - 3 })}</li>
              )}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
