import { useState, useRef } from "react";
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

interface PlanResult {
  plan_id: string;
  task_count: number;
  tasks: Array<{ task_id: string; description: string; file_path: string }>;
}

export function PlanForm() {
  const { t, i18n } = useTranslation();
  const localeOptions = getAgentLocaleOptions(t);
  const [prompt, setPrompt] = useState("");
  const [projectName, setProjectName] = useState("my-project");
  const [repoUrl, setRepoUrl] = useState("");
  const [mode, setMode] = useState<"normal" | "save">("normal");
  const [replannerAggressiveness, setReplannerAggressiveness] = useState<"0" | "1" | "2">("1");
  const [plannerProvider, setPlannerProvider] = useState<string>("default");
  const [userLocaleChoice, setUserLocaleChoice] = useState<string>("auto");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    if (submittingRef.current) return;
    submittingRef.current = true;
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const body: Record<string, string> = {
        prompt: prompt.trim(),
        project_name: projectName,
        user_locale: resolveAgentLocale(
          userLocaleChoice,
          i18n.resolvedLanguage || i18n.language,
        ),
      };
      if (repoUrl.trim()) {
        body.repo_url = repoUrl.trim();
      }
      body.mode = mode;
      body.replanner_aggressiveness = replannerAggressiveness;
      if (plannerProvider !== "default") {
        body.llm_provider = plannerProvider;
      }

      const data = await postJson<PlanResult>("/api/plan", body);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      submittingRef.current = false;
    }
  }

  return (
    <Card>
      <SectionHeader>{t("planForm.title")}</SectionHeader>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className={APP_LABEL}>
            {t("planForm.projectName")}
          </label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className={APP_INPUT}
            placeholder="my-project"
          />
        </div>

        <div>
          <label className={APP_LABEL}>
            {t("planForm.mode")}
          </label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "normal" | "save")}
            className={APP_SELECT}
          >
            <option value="normal">{t("planForm.modeNormal")}</option>
            <option value="save">{t("planForm.modeSave")}</option>
          </select>
        </div>

        <div>
          <label className={APP_LABEL}>
            {t("planForm.responseLanguage")}
          </label>
          <select
            value={userLocaleChoice}
            onChange={(e) => setUserLocaleChoice(e.target.value)}
            className={APP_SELECT}
          >
            {localeOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 2xl:grid-cols-2 gap-2">
          <div>
            <label className={APP_LABEL}>
              {t("planForm.replannerAggressiveness")}
            </label>
            <select
              value={replannerAggressiveness}
              onChange={(e) =>
                setReplannerAggressiveness(e.target.value as "0" | "1" | "2")
              }
              className={APP_SELECT}
            >
              <option value="0">{t("planForm.replanner0")}</option>
              <option value="1">{t("planForm.replanner1")}</option>
              <option value="2">{t("planForm.replanner2")}</option>
            </select>
          </div>

          <div>
            <label className={APP_LABEL}>
              {t("planForm.plannerProvider")}
            </label>
            <select
              value={plannerProvider}
              onChange={(e) => setPlannerProvider(e.target.value)}
              className={APP_SELECT}
            >
              <option value="default">{t("planForm.plannerAuto")}</option>
              <option value="groq">Groq (llama-3.3-70b)</option>
              <option value="gemini">Gemini</option>
              <option value="openai">OpenAI</option>
              <option value="local">{t("planForm.plannerLocal")}</option>
            </select>
          </div>
        </div>

        <div>
          <label className={APP_LABEL}>
            {t("planForm.prompt")}
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className={`${APP_TEXTAREA} min-h-[96px] resize-none`}
            placeholder={t("planForm.promptPlaceholder")}
          />
        </div>

        <div>
          <label className={APP_LABEL}>
            {t("planForm.repoUrl")}{" "}
            <span className="app-muted-text normal-case">
              ({t("planForm.repoUrlHelp")})
            </span>
          </label>
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            className={APP_INPUT}
            placeholder={t("planForm.repoPlaceholder")}
          />
          {repoUrl.trim() ? (
            <p className="mt-1 text-xs font-mono text-[var(--color-electric-cyan)]">
              {t("planForm.repoUrlPresent")}
            </p>
          ) : (
            <p className={`${APP_META_TEXT} mt-1`}>
              {t("planForm.repoUrlMissing")}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className={`${APP_BUTTON_PRIMARY} w-full text-sm`}
        >
          {loading ? t("planForm.launching") : t("planForm.launchPipeline")}
        </button>
      </form>

      {error && (
        <div className="app-surface-soft mt-3 border-red-500/30 bg-red-950/30 px-3 py-2 text-xs font-mono text-red-300">
          {error}
        </div>
      )}

      {result && (
        <div className="app-surface-soft mt-3 space-y-1 px-3 py-3">
          <p className="text-xs font-mono text-[var(--color-electric-cyan)]">
            {t("planForm.planCreated", { count: result.task_count })}
          </p>
          <p className={`${APP_META_TEXT} break-all`}>
            plan_id: {result.plan_id}
          </p>
          {result.tasks?.map((t) => (
            <p key={t.task_id} className="truncate text-xs font-mono text-[var(--color-silver-text)]/78">
              → {t.file_path}
            </p>
          ))}
        </div>
      )}
    </Card>
  );
}
