import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { postJson } from "../api/api";
import { getAgentLocaleOptions, resolveAgentLocale } from "../i18n/locale";
import { Card, SectionHeader } from "./ui/Card";
import {
  APP_BUTTON_PRIMARY,
  APP_INPUT,
  APP_LABEL,
  APP_META_TEXT,
  APP_SELECT,
  APP_TEXTAREA,
} from "./ui/theme";

export interface AgentAskResult {
  answer: string;
  sources: Array<Record<string, unknown>>;
  prompt_tokens?: number;
  completion_tokens?: number;
  detail?: string;
  error?: string;
}

type Props = {
  /** Pre-filled from dashboard filter; user can clear to query global memory only */
  defaultPlanId: string | null;
};

export function AgentAskCard({ defaultPlanId }: Props) {
  const { t, i18n } = useTranslation();
  const localeOptions = getAgentLocaleOptions(t);
  const [question, setQuestion] = useState("");
  const [planId, setPlanId] = useState("");
  const [localeChoice, setLocaleChoice] = useState<string>("auto");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgentAskResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (defaultPlanId) setPlanId(defaultPlanId);
  }, [defaultPlanId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const body: Record<string, string> = {
        question: question.trim(),
        user_locale: resolveAgentLocale(
          localeChoice,
          i18n.resolvedLanguage || i18n.language,
        ),
      };
      const pid = planId.trim();
      if (pid) body.plan_id = pid;
      const data = await postJson<AgentAskResult>("/api/agent_ask", body);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <SectionHeader>{t("agentAsk.title")}</SectionHeader>
      <p className={`${APP_META_TEXT} mb-3 text-[11px] leading-relaxed`}>
        {t("agentAsk.description")}
      </p>
      <form onSubmit={handleSubmit} className="space-y-2">
        <div>
          <label className={APP_LABEL}>
            {t("agentAsk.question")}
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            className={`${APP_TEXTAREA} min-h-[88px] resize-none text-xs`}
            placeholder={t("agentAsk.questionPlaceholder")}
          />
        </div>
        <div>
          <label className={APP_LABEL}>
            {t("agentAsk.planId")}{" "}
            <span className="app-muted-text normal-case">
              ({t("agentAsk.planIdOptional")})
            </span>
          </label>
          <input
            type="text"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
            className={`${APP_INPUT} text-[11px]`}
            placeholder={t("agentAsk.planPlaceholder")}
          />
        </div>
        <div>
          <label className={APP_LABEL}>
            {t("agentAsk.responseLanguage")}
          </label>
          <select
            value={localeChoice}
            onChange={(e) => setLocaleChoice(e.target.value)}
            className={APP_SELECT}
          >
            {localeOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className={`${APP_BUTTON_PRIMARY} w-full text-[11px]`}
        >
          {loading ? t("agentAsk.asking") : t("agentAsk.ask")}
        </button>
      </form>
      {error && (
        <div className="app-surface-soft mt-2 border-red-500/30 bg-red-950/30 px-3 py-2 text-[10px] font-mono text-red-300">
          {error}
        </div>
      )}
      {result && (
        <div className="app-surface-soft mt-3 space-y-2 px-3 py-3 text-[10px] font-mono">
          <div className="whitespace-pre-wrap border-l border-[var(--color-electric-cyan)]/50 pl-3 leading-relaxed text-[var(--color-silver-text)]">
            {result.answer}
          </div>
          {result.sources && result.sources.length > 0 && (
            <details className={APP_META_TEXT}>
              <summary className="cursor-pointer text-[var(--color-silver-text)]/78 hover:text-[var(--color-polar-white)]">
                {t("agentAsk.sources", { count: result.sources.length })}
              </summary>
              <ul className="mt-1 space-y-1 pl-2 max-h-32 overflow-y-auto">
                {result.sources.map((s, i) => (
                  <li key={i} className="truncate" title={String(s.text_preview ?? "")}>
                    #{String(s.rank ?? i + 1)} {String(s.event_type ?? "")} score=
                    {Number(s.heuristic_score ?? 0).toFixed(2)}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {(result.prompt_tokens || result.completion_tokens) ? (
            <p className={APP_META_TEXT}>
              {t("agentAsk.tokens", {
                prompt: result.prompt_tokens ?? 0,
                completion: result.completion_tokens ?? 0,
              })}
            </p>
          ) : null}
        </div>
      )}
    </Card>
  );
}
