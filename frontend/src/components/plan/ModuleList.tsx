import type { PlanDetail } from "../../types/planDetail";

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
}
