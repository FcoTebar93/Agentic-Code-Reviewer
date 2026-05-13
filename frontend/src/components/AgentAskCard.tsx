import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { postJson } from "../api/api";
import { getAgentLocaleOptions, resolveAgentLocale } from "../i18n/locale";
import { Card, SectionHeader } from "./ui/Card";

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
      <p className="text-[10px] font-mono text-neutral-500 mb-3 leading-relaxed">
        {t("agentAsk.description")}
      </p>
      <form onSubmit={handleSubmit} className="space-y-2">
        <div>
          <label className="block text-neutral-500 text-[10px] font-mono mb-1">
            {t("agentAsk.question")}
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            className="w-full bg-black border border-neutral-700 rounded-lg px-2 py-1.5 text-neutral-100 text-xs font-mono placeholder:text-neutral-600 focus:outline-none focus:border-neutral-500 resize-none"
            placeholder={t("agentAsk.questionPlaceholder")}
          />
        </div>
        <div>
          <label className="block text-neutral-500 text-[10px] font-mono mb-1">
            {t("agentAsk.planId")}{" "}
            <span className="text-neutral-600">
              ({t("agentAsk.planIdOptional")})
            </span>
          </label>
          <input
            type="text"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded-lg px-2 py-1.5 text-neutral-100 text-[10px] font-mono focus:outline-none focus:border-neutral-500"
            placeholder={t("agentAsk.planPlaceholder")}
          />
        </div>
        <div>
          <label className="block text-neutral-500 text-[10px] font-mono mb-1">
            {t("agentAsk.responseLanguage")}
          </label>
          <select
            value={localeChoice}
            onChange={(e) => setLocaleChoice(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded-lg px-2 py-1.5 text-neutral-100 text-[10px] font-mono focus:outline-none focus:border-neutral-500"
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
          className="w-full bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-900 disabled:text-neutral-600 text-neutral-100 font-mono text-[11px] rounded-lg px-3 py-2 transition-colors border border-neutral-600"
        >
          {loading ? t("agentAsk.asking") : t("agentAsk.ask")}
        </button>
      </form>
      {error && (
        <div className="mt-2 text-red-300 text-[10px] font-mono border border-red-900/50 rounded-lg px-2 py-1.5 bg-red-950/30">
          {error}
        </div>
      )}
      {result && (
        <div className="mt-3 space-y-2 text-[10px] font-mono">
          <div className="text-neutral-300 whitespace-pre-wrap leading-relaxed border-l border-emerald-800/60 pl-2">
            {result.answer}
          </div>
          {result.sources && result.sources.length > 0 && (
            <details className="text-neutral-500">
              <summary className="cursor-pointer text-neutral-400 hover:text-neutral-300">
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
            <p className="text-neutral-600">
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
