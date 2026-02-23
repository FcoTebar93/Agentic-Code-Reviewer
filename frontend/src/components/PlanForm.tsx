import { useState } from "react";

const HTTP_URL = import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";

interface PlanResult {
  plan_id: string;
  task_count: number;
  tasks: Array<{ task_id: string; description: string; file_path: string }>;
}

export function PlanForm() {
  const [prompt, setPrompt] = useState("");
  const [projectName, setProjectName] = useState("my-project");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;

    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const resp = await fetch(`${HTTP_URL}/api/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt.trim(), project_name: projectName }),
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
      }

      const data = await resp.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
      <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3">
        Launch Plan
      </h2>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-slate-500 text-xs font-mono mb-1">
            Project name
          </label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm font-mono focus:outline-none focus:border-indigo-500"
            placeholder="my-project"
          />
        </div>

        <div>
          <label className="block text-slate-500 text-xs font-mono mb-1">
            Prompt
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm font-mono focus:outline-none focus:border-indigo-500 resize-none"
            placeholder="Create a Python REST API with FastAPI..."
          />
        </div>

        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-mono text-sm rounded-lg px-4 py-2.5 transition-colors"
        >
          {loading ? "Launching..." : "Launch Pipeline"}
        </button>
      </form>

      {error && (
        <div className="mt-3 bg-red-900/40 border border-red-700 rounded-lg px-3 py-2 text-red-300 text-xs font-mono">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-3 bg-slate-800 rounded-lg px-3 py-2 space-y-1">
          <p className="text-green-400 text-xs font-mono">
            Plan created — {result.task_count} task
            {result.task_count !== 1 ? "s" : ""}
          </p>
          <p className="text-slate-500 text-xs font-mono break-all">
            plan_id: {result.plan_id}
          </p>
          {result.tasks?.map((t) => (
            <p key={t.task_id} className="text-slate-400 text-xs font-mono truncate">
              → {t.file_path}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
