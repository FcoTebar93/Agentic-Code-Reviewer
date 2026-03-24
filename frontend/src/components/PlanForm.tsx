import { useState, useRef } from "react";
import { postJson } from "../api/api";
import { Card, SectionHeader } from "./ui/Card";

interface PlanResult {
  plan_id: string;
  task_count: number;
  tasks: Array<{ task_id: string; description: string; file_path: string }>;
}

const LOCALE_OPTIONS = [
  { value: "auto", label: "Auto (browser language)" },
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
  { value: "pt", label: "Português" },
  { value: "it", label: "Italiano" },
] as const;

const SUPPORTED_PRIMARY = new Set([
  "en",
  "es",
  "fr",
  "de",
  "pt",
  "it",
  "ja",
  "zh",
  "ko",
]);

function effectiveUserLocale(choice: string): string {
  if (choice !== "auto") return choice;
  if (typeof navigator === "undefined") return "en";
  const primary = (navigator.language || "en").split("-")[0].toLowerCase();
  return SUPPORTED_PRIMARY.has(primary) ? primary : "en";
}

export function PlanForm() {
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
        user_locale: effectiveUserLocale(userLocaleChoice),
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
      <SectionHeader>Launch Plan</SectionHeader>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            Project name
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
            Mode
          </label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "normal" | "save")}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
          >
            <option value="normal">normal (more context, more tokens)</option>
            <option value="save">save (reduced context, fewer tokens)</option>
          </select>
        </div>

        <div>
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            Agent response language
          </label>
          <select
            value={userLocaleChoice}
            onChange={(e) => setUserLocaleChoice(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
          >
            {LOCALE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-neutral-500 text-xs font-mono mb-1">
              Replanner aggressiveness
            </label>
            <select
              value={replannerAggressiveness}
              onChange={(e) =>
                setReplannerAggressiveness(e.target.value as "0" | "1" | "2")
              }
              className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
            >
              <option value="0">0 — off (no auto-replan)</option>
              <option value="1">1 — normal (current behaviour)</option>
              <option value="2">2 — more aggressive (prioritise replans)</option>
            </select>
          </div>

          <div>
            <label className="block text-neutral-500 text-xs font-mono mb-1">
              Planner LLM provider
            </label>
            <select
              value={plannerProvider}
              onChange={(e) => setPlannerProvider(e.target.value)}
              className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-xs font-mono focus:outline-none focus:border-neutral-500 transition-colors"
            >
              <option value="default">auto (from backend)</option>
              <option value="groq">Groq (llama-3.3-70b)</option>
              <option value="gemini">Gemini</option>
              <option value="openai">OpenAI</option>
              <option value="local">Local (Ollama / LM Studio)</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            Prompt
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-sm font-mono placeholder:text-neutral-600 focus:outline-none focus:border-neutral-500 resize-none transition-colors"
            placeholder="Create a Python REST API with FastAPI..."
          />
        </div>

        <div>
          <label className="block text-neutral-500 text-xs font-mono mb-1">
            GitHub repo URL{" "}
            <span className="text-neutral-600">(optional — required for real PR)</span>
          </label>
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            className="w-full bg-black border border-neutral-700 rounded-lg px-3 py-2 text-neutral-100 text-sm font-mono placeholder:text-neutral-600 focus:outline-none focus:border-neutral-500 transition-colors"
            placeholder="https://github.com/your-org/your-repo"
          />
          {repoUrl.trim() ? (
            <p className="text-emerald-400 text-xs font-mono mt-1">
              ✓ PR will be created on GitHub after human approval
            </p>
          ) : (
            <p className="text-neutral-600 text-xs font-mono mt-1">
              Without a repo URL, files are written locally in the container
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="w-full bg-white hover:bg-neutral-200 disabled:bg-neutral-800 disabled:text-neutral-500 text-black font-mono text-sm font-medium rounded-lg px-4 py-2.5 transition-colors"
        >
          {loading ? "Launching..." : "Launch Pipeline"}
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
            Plan created — {result.task_count} task
            {result.task_count !== 1 ? "s" : ""}
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
