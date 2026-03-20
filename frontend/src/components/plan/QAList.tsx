import type { PlanDetail } from "../../types/planDetail";

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
}
