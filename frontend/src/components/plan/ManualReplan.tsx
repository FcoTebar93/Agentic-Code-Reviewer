import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { postJson } from "../../api/api";
import type { PlanDetail } from "../../types/planDetail";
import type { ReplanPrefill } from "./replanPrefill";
import { translateSeverity } from "../../i18n/formatters";
import {
  APP_BUTTON_PRIMARY,
  APP_LABEL,
  APP_SELECT,
  APP_TEXTAREA,
  cx,
} from "../ui/theme";

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
    <div className="app-divider mt-3 border-t pt-2">
      <p className="app-section-title mb-1 text-[10px]">
        {t("manualReplan.title")}
      </p>
      <form onSubmit={handleSubmit} className="space-y-2 text-xs">
        <div className="flex gap-2 items-center">
          <label className={cx(APP_LABEL, "mb-0 min-w-[78px]")}>
            {t("manualReplan.severity")}
          </label>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className={cx(APP_SELECT, "flex-1")}
          >
            <option value="low">{translateSeverity(t, "low")}</option>
            <option value="medium">{translateSeverity(t, "medium")}</option>
            <option value="high">{translateSeverity(t, "high")}</option>
            <option value="critical">{translateSeverity(t, "critical")}</option>
          </select>
        </div>
        <div>
          <p className="app-section-title mb-1 text-[10px]">
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
                  className={cx(
                    "app-chip px-2.5 py-1",
                    active && "app-chip-active",
                  )}
                >
                  {g}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <label className={APP_LABEL}>
            {t("manualReplan.reason")} ({t("values.optional")})
          </label>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className={`${APP_TEXTAREA} resize-none text-xs`}
            placeholder={t("manualReplan.reasonPlaceholder")}
          />
        </div>
        <div>
          <label className={APP_LABEL}>
            {t("manualReplan.suggestions")} ({t("values.optional")})
          </label>
          <textarea
            rows={2}
            value={suggestions}
            onChange={(e) => setSuggestions(e.target.value)}
            className={`${APP_TEXTAREA} resize-none text-xs`}
            placeholder={t("manualReplan.suggestionsPlaceholder")}
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className={`${APP_BUTTON_PRIMARY} w-full text-[11px]`}
        >
          {submitting ? t("manualReplan.requesting") : t("manualReplan.request")}
        </button>
        {message && (
          <p className="app-meta-text mt-1 text-[10px]">
            {message}
          </p>
        )}
      </form>
    </div>
  );
}
