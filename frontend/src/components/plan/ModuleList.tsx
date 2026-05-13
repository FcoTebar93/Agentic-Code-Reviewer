import type { PlanDetail } from "../../types/planDetail";
import { useTranslation } from "react-i18next";
import { translateSeverity } from "../../i18n/formatters";
import { cx } from "../ui/theme";

type Modules = NonNullable<PlanDetail["modules"]>;

export function ModuleList({
  modules,
  selectedModuleId,
  onSelectModule,
}: {
  modules: Modules;
  selectedModuleId: string | null;
  onSelectModule: (groupId: string | null) => void;
}) {
  const { t } = useTranslation();
  if (!modules.length) return null;

  const maxQa = Math.max(...modules.map((m) => m.qa_failed_count || 0), 0);

  function severityColor(sev: string): string {
    if (sev === "critical") return "text-[var(--color-danger-red)]";
    if (sev === "high") return "text-[var(--color-warning-yellow)]";
    if (sev === "medium") return "text-[var(--color-electric-cyan)]";
    return "app-muted-text";
  }

  return (
    <div className="app-divider mt-3 border-t pt-2">
      <p className="app-section-title mb-1 text-[10px]">
        {t("moduleList.title")}
      </p>
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          onClick={() => onSelectModule(null)}
          className={cx(
            "app-chip px-2.5 py-1",
            selectedModuleId === null && "app-chip-active",
          )}
        >
          {t("moduleList.all")}
        </button>
        {modules.map((m) => {
          const active = selectedModuleId === m.group_id;
          const qaBadge =
            m.qa_failed_count > 0
              ? t("moduleList.qaFails", { count: m.qa_failed_count })
              : t("moduleList.zeroQaFails");
          const sevClass = severityColor(m.max_severity_hint || "low");

          const intensity =
            maxQa > 0 ? Math.min(1, m.qa_failed_count / maxQa) : 0;
          const bgHot =
            intensity > 0
              ? "border-[var(--color-danger-red)]/34 bg-[var(--color-danger-red)]/10"
              : "";

          return (
            <button
              key={m.group_id}
              type="button"
              onClick={() => onSelectModule(m.group_id)}
              className={cx(
                "app-chip flex items-center gap-1 px-2.5 py-1",
                bgHot,
                active && "app-chip-active",
              )}
            >
              <span className="truncate max-w-[120px]">
                {m.group_id || "root"}
              </span>
              <span className="text-[9px] text-[var(--color-silver-text)]/62">
                {m.tasks_count}t · {qaBadge}
              </span>
              <span className={`text-[9px] ${sevClass}`}>
                {translateSeverity(t, m.max_severity_hint)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
