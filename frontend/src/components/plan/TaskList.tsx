import type { PlanDetail } from "../../types/planDetail";
import { useTranslation } from "react-i18next";
import {
  translateGenericStatus,
  translateSeverity,
} from "../../i18n/formatters";
import { APP_META_TEXT, cx } from "../ui/theme";

export function TaskList({
  tasks,
  qaOutcomes,
  selectedTaskId,
  onSelectTask,
}: {
  tasks: PlanDetail["tasks"];
  qaOutcomes: PlanDetail["qa_outcomes"];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
}) {
  const { t: translate } = useTranslation();
  if (!tasks.length) return null;

  const qaByTask = new Map(
    qaOutcomes.map((o) => [o.task_id, o] as const),
  );

  return (
    <div className="app-divider mt-3 border-t pt-2">
      <p className="app-section-title mb-1 text-[10px]">
        {translate("taskList.title")}
      </p>
      <div className="space-y-1 max-h-40 overflow-auto pr-1">
        {tasks.map((task) => {
          const qa = qaByTask.get(task.task_id);
          const severity =
            qa?.severity_hint && qa.severity_hint !== "medium"
              ? qa.severity_hint
              : null;
          const isActive = selectedTaskId === task.task_id;
          return (
            <div
              key={task.task_id}
              onClick={() => onSelectTask(task.task_id)}
              className={`app-surface-soft flex cursor-pointer flex-col gap-0.5 px-3 py-2 text-xs transition-colors ${
                isActive
                  ? "border-[var(--color-electric-cyan)]/34 bg-[rgba(34,211,238,0.08)]"
                  : "hover:border-[var(--color-neon-violet)]/28"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="max-w-[160px] truncate text-[var(--color-polar-white)]">
                  {task.file_path || translate("taskList.noPath")}
                </span>
                <span className={cx(APP_META_TEXT, "text-[10px]")}>
                  {translateGenericStatus(translate, task.status || "unknown")}
                </span>
              </div>
              <div className={`${APP_META_TEXT} flex justify-between gap-2 text-[10px]`}>
                <span className="max-w-[130px] truncate">
                  {task.language} ·{" "}
                  {translateGenericStatus(translate, task.group_id || "root")}
                </span>
                <span>
                  {translate("taskList.qaAttempt", { count: task.qa_attempt })}
                </span>
              </div>
              {severity && (
                <div className="text-[10px] text-[var(--color-danger-red)]">
                  {translate("taskList.qaSeverity", {
                    severity: translateSeverity(translate, severity),
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
