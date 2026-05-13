import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { postJson } from "../../api/api";
import type { PlanDetail } from "../../types/planDetail";
import type { ReplanPrefill } from "./replanPrefill";
import { translateSeverity } from "../../i18n/formatters";

export function ManualReplan({
  plan,
  prefill,
}: {
  plan: PlanDetail;
  prefill?: ReplanPrefill;
}) {
  const { t, i18n } = useTranslation();
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
      t("manualReplan.prefilled"),
    );
  }, [
    prefill?.severity,
    prefill?.reason,
    prefill?.suggestions,
    prefill?.targetGroupIds,
    t,
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
        user_locale: i18n.resolvedLanguage || i18n.language || "es",
        reason:
          reason.trim() ||
          t("manualReplan.defaultReason"),
        summary: t("manualReplan.defaultSummary", {
          planId: plan.plan_id.slice(0, 8),
        }),
        suggestions: suggestions
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        target_group_ids: selectedGroups.length ? selectedGroups : uniqueGroups,
      };
      await postJson("/api/replan", body);
      setMessage(t("manualReplan.requestSuccess"));
      setReason("");
      setSuggestions("");
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : t("manualReplan.requestError"),
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
        {t("manualReplan.title")}
      </p>
      <form onSubmit={handleSubmit} className="space-y-2 text-xs">
        <div className="flex gap-2 items-center">
          <label className="text-[10px] text-neutral-500 font-mono">
            {t("manualReplan.severity")}
          </label>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="bg-black border border-neutral-700 rounded px-2 py-1 text-[11px] font-mono text-neutral-100 flex-1"
          >
            <option value="low">{translateSeverity(t, "low")}</option>
            <option value="medium">{translateSeverity(t, "medium")}</option>
            <option value="high">{translateSeverity(t, "high")}</option>
            <option value="critical">{translateSeverity(t, "critical")}</option>
          </select>
        </div>
        <div>
          <p className="text-[10px] text-neutral-500 font-mono mb-1">
            {t("manualReplan.targetGroups")}
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
            {t("manualReplan.reason")} ({t("values.optional")})
          </label>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-100 placeholder:text-neutral-600 resize-none"
            placeholder={t("manualReplan.reasonPlaceholder")}
          />
        </div>
        <div>
          <label className="block text-[10px] text-neutral-500 font-mono mb-1">
            {t("manualReplan.suggestions")} ({t("values.optional")})
          </label>
          <textarea
            rows={2}
            value={suggestions}
            onChange={(e) => setSuggestions(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-100 placeholder:text-neutral-600 resize-none"
            placeholder={t("manualReplan.suggestionsPlaceholder")}
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-neutral-100 hover:bg-neutral-300 disabled:bg-neutral-800 disabled:text-neutral-500 text-black font-mono text-[11px] font-medium rounded px-3 py-1.5 transition-colors"
        >
          {submitting ? t("manualReplan.requesting") : t("manualReplan.request")}
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
