import type { PlanDetail } from "../../types/planDetail";

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
}
