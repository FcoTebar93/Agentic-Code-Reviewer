import { useState } from "react";
import type { BaseEvent } from "../types/events";
import { EVENT_COLORS, EVENT_LABELS } from "../types/events";

interface Props {
  events: BaseEvent[];
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

function extractReasoning(payload: Record<string, unknown>): string {
  const r = payload["reasoning"];
  if (typeof r === "string" && r.trim().length > 0) return r.trim();
  const sr = payload["security_reasoning"];
  if (typeof sr === "string" && sr.trim().length > 0) return sr.trim();
  return "";
}

function extractCode(
  eventType: string,
  payload: Record<string, unknown>
): { code: string; filePath: string; language: string } | null {
  if (eventType !== "code.generated") return null;
  const code = payload["code"];
  if (typeof code !== "string" || !code.trim()) return null;
  return {
    code: code.trim(),
    filePath: typeof payload["file_path"] === "string" ? payload["file_path"] : "",
    language: typeof payload["language"] === "string" ? payload["language"] : "python",
  };
}

function extractFiles(
  eventType: string,
  payload: Record<string, unknown>
): string[] {
  if (eventType !== "pr.requested" && eventType !== "security.approved") return [];
  const files = payload["files"];
  if (!Array.isArray(files)) return [];
  return files
    .map((f) => (typeof f === "object" && f !== null ? (f as Record<string, unknown>)["file_path"] : null))
    .filter((fp): fp is string => typeof fp === "string");
}

function extractPrUrl(eventType: string, payload: Record<string, unknown>): string {
  if (eventType !== "pr.created") return "";
  const url = payload["pr_url"];
  if (typeof url === "string" && url.startsWith("http")) return url;
  return "";
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="relative">
      <div className="flex items-center justify-between bg-slate-950 rounded-t px-3 py-1 border border-slate-700/60">
        <span className="text-slate-500 text-[10px] uppercase tracking-widest">
          {language}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); copy(); }}
          className="text-slate-600 hover:text-slate-400 text-[10px] transition-colors"
        >
          {copied ? "copied ✓" : "copy"}
        </button>
      </div>
      <pre className="bg-slate-950 border border-t-0 border-slate-700/60 rounded-b px-3 py-2 overflow-x-auto max-h-64 text-[11px] leading-relaxed text-slate-300 whitespace-pre">
        {code}
      </pre>
    </div>
  );
}

function EventRow({ evt }: { evt: BaseEvent }) {
  // All events start expanded so information is immediately visible
  const [open, setOpen] = useState(true);

  const reasoning = extractReasoning(evt.payload);
  const prUrl = extractPrUrl(evt.event_type, evt.payload);
  const codeInfo = extractCode(evt.event_type, evt.payload);
  const fileList = extractFiles(evt.event_type, evt.payload);
  const expandable = !!(reasoning || prUrl || codeInfo || fileList.length);

  const color = EVENT_COLORS[evt.event_type] ?? "#6b7280";
  const label = EVENT_LABELS[evt.event_type] ?? evt.event_type;

  // File path shown inline on the header for code events
  const inlineFilePath =
    evt.event_type === "code.generated" &&
    typeof evt.payload["file_path"] === "string"
      ? (evt.payload["file_path"] as string)
      : null;

  return (
    <div className="bg-slate-800 rounded-lg overflow-hidden text-xs font-mono border border-slate-700/40">
      {/* Header row */}
      <div
        className={`flex items-start gap-2 px-3 py-2 ${expandable ? "cursor-pointer select-none" : ""}`}
        onClick={() => expandable && setOpen((v) => !v)}
      >
        <span className="text-slate-500 flex-none w-20 pt-px">
          {formatTime(evt.timestamp)}
        </span>
        <span
          className="rounded px-1.5 py-0.5 font-semibold flex-none text-white whitespace-nowrap"
          style={{ backgroundColor: color, opacity: 0.9 }}
        >
          {label}
        </span>
        <span className="text-slate-400 truncate flex-1">
          {evt.producer}
          {inlineFilePath && (
            <span className="text-indigo-400 ml-2">{inlineFilePath}</span>
          )}
          <span className="text-slate-600 ml-2">#{shortId(evt.event_id)}</span>
        </span>
        {prUrl && !open && (
          <span className="text-green-500 flex-none ml-1">↗</span>
        )}
        {expandable && (
          <span className="text-slate-600 flex-none ml-1">
            {open ? "▾" : "▸"}
          </span>
        )}
      </div>

      {/* Expanded panel */}
      {expandable && open && (
        <div className="border-t border-slate-700/60 space-y-3 px-3 pt-2 pb-3">

          {/* PR link */}
          {prUrl && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1">
                Pull Request
              </p>
              <a
                href={prUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-400 hover:text-indigo-300 underline break-all"
                onClick={(e) => e.stopPropagation()}
              >
                {prUrl}
              </a>
            </div>
          )}

          {/* Files list (pr.requested / security.approved) */}
          {fileList.length > 0 && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                Files in PR ({fileList.length})
              </p>
              <div className="space-y-0.5">
                {fileList.map((fp) => (
                  <div key={fp} className="text-indigo-400 flex items-center gap-1">
                    <span className="text-slate-600">+</span> {fp}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Generated code */}
          {codeInfo && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                Generated code — {codeInfo.filePath}
              </p>
              <CodeBlock code={codeInfo.code} language={codeInfo.language} />
            </div>
          )}

          {/* Agent reasoning */}
          {reasoning && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                Agent reasoning
              </p>
              <p className="text-slate-300 leading-relaxed whitespace-pre-wrap">
                {reasoning}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function EventFeed({ events }: Props) {
  const [allCollapsed, setAllCollapsed] = useState(false);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 flex-none">
        <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest">
          Event Feed{" "}
          <span className="text-slate-600 normal-case">({events.length} events)</span>
        </h2>
        {events.length > 0 && (
          <button
            onClick={() => setAllCollapsed((v) => !v)}
            className="text-slate-600 hover:text-slate-400 text-[10px] font-mono transition-colors"
          >
            {allCollapsed ? "expand all" : "collapse all"}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
        {events.length === 0 && (
          <p className="text-slate-600 text-sm font-mono">Waiting for events...</p>
        )}
        {events.map((evt) => (
          <EventRow key={evt.event_id} evt={evt} />
        ))}
      </div>
    </div>
  );
}
