import { useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { postJson } from "../api/api";
import { getAgentLocaleOptions, resolveAgentLocale } from "../i18n/locale";
import { Card, SectionHeader } from "./ui/Card";

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
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            {t("planForm.projectName")}
          </label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-sm font-mono placeholder:text-neutral-600 focus:outline-none focus:border-neutral-500 transition-colors"
            placeholder="my-project"
          />
        </div>

        <div>
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            {t("planForm.mode")}
          </label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "normal" | "save")}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
          >
            <option value="normal">{t("planForm.modeNormal")}</option>
            <option value="save">{t("planForm.modeSave")}</option>
          </select>
        </div>

        <div>
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            {t("planForm.responseLanguage")}
          </label>
          <select
            value={userLocaleChoice}
            onChange={(e) => setUserLocaleChoice(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
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
            <label className="block text-neutral-500 text-xs font-mono mb-1">
              {t("planForm.replannerAggressiveness")}
            </label>
            <select
              value={replannerAggressiveness}
              onChange={(e) =>
                setReplannerAggressiveness(e.target.value as "0" | "1" | "2")
              }
              className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
            >
              <option value="0">{t("planForm.replanner0")}</option>
              <option value="1">{t("planForm.replanner1")}</option>
              <option value="2">{t("planForm.replanner2")}</option>
            </select>
          </div>

          <div>
            <label className="block text-neutral-500 text-xs font-mono mb-1">
              {t("planForm.plannerProvider")}
            </label>
            <select
              value={plannerProvider}
              onChange={(e) => setPlannerProvider(e.target.value)}
              className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
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
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            {t("planForm.prompt")}
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-sm font-mono placeholder:text-neutral-600 focus:outline-none focus:border-neutral-500 resize-none transition-colors"
            placeholder={t("planForm.promptPlaceholder")}
          />
        </div>

        <div>
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            {t("planForm.repoUrl")}{" "}
            <span className="text-neutral-600">
              ({t("planForm.repoUrlHelp")})
            </span>
          </label>
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-sm font-mono placeholder:text-neutral-600 focus:outline-none focus:border-neutral-500 transition-colors"
            placeholder={t("planForm.repoPlaceholder")}
          />
          {repoUrl.trim() ? (
            <p className="text-emerald-400 text-xs font-mono mt-1">
              {t("planForm.repoUrlPresent")}
            </p>
          ) : (
            <p className="text-neutral-600 text-xs font-mono mt-1">
              {t("planForm.repoUrlMissing")}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="w-full bg-white hover:bg-neutral-200 disabled:bg-neutral-800 disabled:text-neutral-500 text-black font-mono text-sm font-medium rounded-lg px-4 py-2.5 transition-colors"
        >
          {loading ? t("planForm.launching") : t("planForm.launchPipeline")}
        </button>
      </form>

      {error && (
        <div className="mt-3 bg-red-950/50 border border-red-900 rounded-lg px-3 py-2 text-red-300 text-xs font-mono">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-3 bg-black border border-neutral-800 rounded-lg px-3 py-2 space-y-1">
          <p className="text-emerald-400 text-xs font-mono">
            {t("planForm.planCreated", { count: result.task_count })}
          </p>
          <p className="text-neutral-500 text-xs font-mono break-all">
            plan_id: {result.plan_id}
          </p>
          {result.tasks?.map((t) => (
            <p key={t.task_id} className="text-neutral-400 text-xs font-mono truncate">
              → {t.file_path}
            </p>
          ))}
        </div>
      )}
    </Card>
  );
}
