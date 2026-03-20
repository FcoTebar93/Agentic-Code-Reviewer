import { useState } from "react";
import type { PlanDetail } from "../../types/planDetail";
import { buildLineDiff } from "./lineDiff";

export function CodePreview({
  task,
}: {
  task: PlanDetail["tasks"][number] | null;
}) {
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

  const [view, setView] = useState<"actual" | "original" | "diff">("actual");

  if (!hasCode) {
    return (
      <div className="mt-3 border-t border-neutral-800 pt-2">
        <p className="text-neutral-500 text-[10px] font-mono mb-1">
          Code preview
        </p>
        <p className="text-[10px] text-neutral-600 font-mono">
          No hay snapshot de código almacenado para esta tarea (puede que sea
          anterior a esta versión del gateway).
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <div className="flex items-center justify-between mb-1">
        <p className="text-neutral-500 text-[10px] font-mono">
          Code preview · {task.file_path || "(sin ruta)"}
        </p>
        <div className="flex gap-1 text-[10px] font-mono">
          <button
            type="button"
            onClick={() => setView("actual")}
            className={`px-2 py-0.5 rounded border ${
              view === "actual"
                ? "border-neutral-300 text-neutral-100"
                : "border-neutral-700 text-neutral-500 hover:border-neutral-500"
            }`}
          >
            Actual
          </button>
          {hasHistoryDiff && (
            <>
              <button
                type="button"
                onClick={() => setView("original")}
                className={`px-2 py-0.5 rounded border ${
                  view === "original"
                    ? "border-neutral-300 text-neutral-100"
                    : "border-neutral-700 text-neutral-500 hover:border-neutral-500"
                }`}
              >
                Original
              </button>
              <button
                type="button"
                onClick={() => setView("diff")}
                className={`px-2 py-0.5 rounded border ${
                  view === "diff"
                    ? "border-neutral-300 text-neutral-100"
                    : "border-neutral-700 text-neutral-500 hover:border-neutral-500"
                }`}
              >
                Diff
              </button>
            </>
          )}
        </div>
      </div>
      <div className="mb-1 flex justify-between items-center text-[10px] text-neutral-500 font-mono">
        <span>
          {task.language} · group {task.group_id || "root"}
        </span>
        <span>qa_attempt: {task.qa_attempt}</span>
      </div>
      {view === "actual" && (
        <pre className="max-h-56 overflow-auto bg-black border border-neutral-800 rounded px-2 py-2 text-[11px] font-mono text-neutral-100 whitespace-pre">
          {latestCode}
        </pre>
      )}
      {view === "original" && hasHistoryDiff && (
        <pre className="max-h-56 overflow-auto bg-black border border-neutral-800 rounded px-2 py-2 text-[11px] font-mono text-neutral-100 whitespace-pre">
          {originalCode}
        </pre>
      )}
      {view === "diff" && hasHistoryDiff && (
        <pre className="max-h-56 overflow-auto bg-black border border-neutral-800 rounded px-2 py-2 text-[11px] font-mono text-neutral-100 whitespace-pre">
          {buildLineDiff(originalCode, latestCode)}
        </pre>
      )}
    </div>
  );
}
