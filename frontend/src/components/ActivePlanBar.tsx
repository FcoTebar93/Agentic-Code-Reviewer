import React from "react";

type Props = {
  planId: string | null;
  mode: string | null;
  onClear?: () => void;
};

export function ActivePlanBar({ planId, mode, onClear }: Props) {
  const [copied, setCopied] = React.useState<"id" | "link" | null>(null);

  if (!planId) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-950/80 px-3 py-2 text-[11px] text-neutral-500 font-mono">
        Ningún plan seleccionado. Lanza un plan o elige uno en el feed.
      </div>
    );
  }

  const id = planId;
  const short = `${id.slice(0, 8)}…`;
  const displayMode =
    mode === "ahorro" ? "save" : mode ?? "—";

  async function copyId() {
    try {
      await navigator.clipboard.writeText(id);
      setCopied("id");
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  async function copyLink() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("plan", id);
      await navigator.clipboard.writeText(url.toString());
      setCopied("link");
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-700 bg-neutral-900/60 px-3 py-2 flex flex-wrap items-center gap-2 text-[11px]">
      <span className="text-neutral-500 font-mono uppercase tracking-wider">
        Plan activo
      </span>
      <span
        className="font-mono text-neutral-100 truncate max-w-[200px]"
        title={id}
      >
        {short}
      </span>
      <span className="text-neutral-600">·</span>
      <span className="text-neutral-400 font-mono">modo {displayMode}</span>
      <div className="flex flex-wrap gap-1.5 ml-auto">
        <button
          type="button"
          onClick={copyId}
          className="px-2 py-0.5 rounded border border-neutral-600 text-neutral-300 hover:bg-neutral-800 font-mono text-[10px]"
        >
          {copied === "id" ? "Copiado" : "Copiar ID"}
        </button>
        <button
          type="button"
          onClick={copyLink}
          className="px-2 py-0.5 rounded border border-neutral-600 text-neutral-300 hover:bg-neutral-800 font-mono text-[10px]"
        >
          {copied === "link" ? "Enlace copiado" : "Copiar enlace"}
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="px-2 py-0.5 rounded border border-neutral-700 text-neutral-500 hover:text-neutral-300 font-mono text-[10px]"
          >
            Quitar filtro
          </button>
        )}
      </div>
    </div>
  );
}
