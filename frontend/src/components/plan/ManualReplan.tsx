import { useEffect, useState } from "react";
import { postJson } from "../../api/api";
import type { PlanDetail } from "../../types/planDetail";
import type { ReplanPrefill } from "./replanPrefill";

export function ManualReplan({
  plan,
  prefill,
}: {
  plan: PlanDetail;
  prefill?: ReplanPrefill;
}) {
  const [severity, setSeverity] = useState<string>("medium");
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [reason, setReason] = useState<string>("");
  const [suggestions, setSuggestions] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!prefill) return;
    setSeverity(prefill.severity || "medium");
    setSelectedGroups(
      Array.isArray(prefill.targetGroupIds) ? prefill.targetGroupIds : [],
    );
    setReason(prefill.reason || "");
    setSuggestions(prefill.suggestions || "");
    setMessage(
      "Formulario de replan pre-rellenado desde QA (revisa y confirma si tiene sentido).",
    );
  }, [
    prefill?.severity,
    prefill?.reason,
    prefill?.suggestions,
    prefill?.targetGroupIds,
  ]);

  const uniqueGroups = Array.from(
    new Set(
      plan.tasks
        .map((t) => t.group_id)
        .filter((g) => typeof g === "string" && g.trim().length > 0),
    ),
  ).slice(0, 10);

  if (!plan.plan_id || uniqueGroups.length === 0) {
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setMessage(null);

    try {
      const body = {
        original_plan_id: plan.plan_id,
        severity,
        reason:
          reason.trim() ||
          "Manual replan triggered from UI based on QA/Security outcomes.",
        summary: `Manual replanning requested for plan ${plan.plan_id.slice(
          0,
          8,
        )}`,
        suggestions: suggestions
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        target_group_ids: selectedGroups.length ? selectedGroups : uniqueGroups,
      };
      await postJson("/api/replan", body);
      setMessage("Replan solicitado correctamente (esperando nuevo plan).");
      setReason("");
      setSuggestions("");
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Error al solicitar replan.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function toggleGroup(groupId: string) {
    setSelectedGroups((prev) =>
      prev.includes(groupId)
        ? prev.filter((g) => g !== groupId)
        : [...prev, groupId],
    );
  }

  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        Manual replan
      </p>
      <form onSubmit={handleSubmit} className="space-y-2 text-xs">
        <div className="flex gap-2 items-center">
          <label className="text-[10px] text-neutral-500 font-mono">
            Severidad
          </label>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="bg-black border border-neutral-700 rounded px-2 py-1 text-[11px] font-mono text-neutral-100 flex-1"
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
        </div>
        <div>
          <p className="text-[10px] text-neutral-500 font-mono mb-1">
            Grupos objetivo (módulos)
          </p>
          <div className="flex flex-wrap gap-1">
            {uniqueGroups.map((g) => {
              const active = selectedGroups.includes(g);
              return (
                <button
                  key={g}
                  type="button"
                  onClick={() => toggleGroup(g)}
                  className={`text-[10px] px-2 py-0.5 rounded-full border font-mono ${
                    active
                      ? "bg-neutral-100 text-black border-neutral-100"
                      : "bg-black text-neutral-300 border-neutral-700 hover:border-neutral-500"
                  }`}
                >
                  {g}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <label className="block text-[10px] text-neutral-500 font-mono mb-1">
            Motivo (opcional)
          </label>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-100 placeholder:text-neutral-600 resize-none"
            placeholder="Ej: Fallos repetidos de QA en estos módulos, necesito reforzar tests y validación..."
          />
        </div>
        <div>
          <label className="block text-[10px] text-neutral-500 font-mono mb-1">
            Sugerencias (una por línea, opcional)
          </label>
          <textarea
            rows={2}
            value={suggestions}
            onChange={(e) => setSuggestions(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-100 placeholder:text-neutral-600 resize-none"
            placeholder="- Añadir tests de validación de formularios&#10;- Endurecer controles de acceso en endpoints sensibles"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-neutral-100 hover:bg-neutral-300 disabled:bg-neutral-800 disabled:text-neutral-500 text-black font-mono text-[11px] font-medium rounded px-3 py-1.5 transition-colors"
        >
          {submitting ? "Solicitando replan..." : "Solicitar replan para este plan"}
        </button>
        {message && (
          <p className="text-[10px] font-mono mt-1 text-neutral-400">
            {message}
          </p>
        )}
      </form>
    </div>
  );
}
