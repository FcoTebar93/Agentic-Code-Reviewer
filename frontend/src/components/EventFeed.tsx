import { useState, useEffect, useCallback } from "react";
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

function extractReasoning(payload: Record<string, unknown>, eventType?: string): string {
  if (eventType === "pipeline.conclusion") {
    const c = payload["conclusion_text"];
    if (typeof c === "string" && c.trim().length > 0) return c.trim();
  }
  const r = payload["reasoning"];
  if (typeof r === "string" && r.trim().length > 0) return r.trim();
  const sr = payload["security_reasoning"];
  if (typeof sr === "string" && sr.trim().length > 0) return sr.trim();
  return "";
}

/** Code from code.generated or qa.passed */
function extractCode(
  eventType: string,
  payload: Record<string, unknown>
): { code: string; filePath: string; language: string } | null {
  if (eventType !== "code.generated" && eventType !== "qa.passed") return null;
  const code = payload["code"];
  if (typeof code !== "string" || !code.trim()) return null;
  return {
    code: code.trim(),
    filePath: typeof payload["file_path"] === "string" ? payload["file_path"] : "",
    language: typeof payload["language"] === "string" ? payload["language"] : "python",
  };
}

/** File list for pr.requested / security.approved / pipeline.conclusion */
function extractFiles(
  eventType: string,
  payload: Record<string, unknown>
): string[] {
  if (eventType === "pipeline.conclusion") {
    const f = payload["files_changed"];
    if (Array.isArray(f)) {
      return f.filter((x): x is string => typeof x === "string");
    }
    return [];
  }
  if (eventType !== "pr.requested" && eventType !== "security.approved") return [];
  const files = payload["files"];
  if (!Array.isArray(files)) return [];
  return files
    .map((f) => (typeof f === "object" && f !== null ? (f as Record<string, unknown>)["file_path"] : null))
    .filter((fp): fp is string => typeof fp === "string");
}

/** Planned file paths from plan.created */
function extractPlannedFiles(payload: Record<string, unknown>): string[] {
  const tasks = payload["tasks"];
  if (!Array.isArray(tasks)) return [];
  return tasks
    .map((t) => (typeof t === "object" && t !== null ? (t as Record<string, unknown>)["file_path"] : null))
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

interface EventRowProps {
  evt: BaseEvent;
  isExpanded: boolean;
  onToggle: () => void;
}

function EventRow({ evt, isExpanded, onToggle }: EventRowProps) {
  const reasoning = extractReasoning(evt.payload, evt.event_type);
  const prUrl = extractPrUrl(evt.event_type, evt.payload);
  const codeInfo = extractCode(evt.event_type, evt.payload);
  const fileList = extractFiles(evt.event_type, evt.payload);
  const plannedFiles = evt.event_type === "plan.created" ? extractPlannedFiles(evt.payload) : [];
  const isConclusion = evt.event_type === "pipeline.conclusion";
  const expandable = !!(reasoning || prUrl || codeInfo || fileList.length || plannedFiles.length || isConclusion);

  const color = EVENT_COLORS[evt.event_type] ?? "#6b7280";
  const label = EVENT_LABELS[evt.event_type] ?? evt.event_type;

  const inlineFilePath =
    (evt.event_type === "code.generated" || evt.event_type === "qa.passed") &&
    typeof evt.payload["file_path"] === "string"
      ? (evt.payload["file_path"] as string)
      : null;

  const open = expandable ? isExpanded : true;

  return (
    <div className="bg-slate-800 rounded-lg overflow-hidden text-xs font-mono border border-slate-700/40">
      <div
        className={`flex items-start gap-2 px-3 py-2 ${expandable ? "cursor-pointer select-none hover:bg-slate-750/50" : ""}`}
        onClick={() => expandable && onToggle()}
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

      {expandable && open && (
        <div className="border-t border-slate-700/60 space-y-3 px-3 pt-2 pb-3">
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

          {plannedFiles.length > 0 && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                Planned files ({plannedFiles.length})
              </p>
              <div className="space-y-0.5">
                {plannedFiles.map((fp) => (
                  <div key={fp} className="text-indigo-400 flex items-center gap-1">
                    <span className="text-slate-600">→</span> {fp}
                  </div>
                ))}
              </div>
            </div>
          )}

          {fileList.length > 0 && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                {isConclusion ? "Files changed" : "Files in PR"} ({fileList.length})
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

          {codeInfo && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                {evt.event_type === "qa.passed" ? "Reviewed code" : "Generated code"} — {codeInfo.filePath}
              </p>
              <CodeBlock code={codeInfo.code} language={codeInfo.language} />
            </div>
          )}

          {reasoning && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                {isConclusion ? "Conclusion" : "Agent reasoning"}
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
  const [collapseAll, setCollapseAll] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

  // New events appear expanded by default
  useEffect(() => {
    if (events.length === 0) return;
    setExpandedIds((prev) => {
      const next = new Set(prev);
      events.forEach((e) => next.add(e.event_id));
      return next;
    });
  }, [events]);

  const handleToggle = useCallback((eventId: string) => {
    setCollapseAll(false);
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) next.delete(eventId);
      else next.add(eventId);
      return next;
    });
  }, []);

  const handleCollapseExpandAll = useCallback(() => {
    if (collapseAll) {
      setCollapseAll(false);
      setExpandedIds(new Set(events.map((e) => e.event_id)));
    } else {
      setCollapseAll(true);
    }
  }, [collapseAll, events]);

  const isExpanded = (eventId: string) => !collapseAll && expandedIds.has(eventId);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 flex-none">
        <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest">
          Event Feed{" "}
          <span className="text-slate-600 normal-case">({events.length} events)</span>
        </h2>
        {events.length > 0 && (
          <button
            onClick={handleCollapseExpandAll}
            className="text-slate-600 hover:text-slate-400 text-[10px] font-mono transition-colors"
          >
            {collapseAll ? "expand all" : "collapse all"}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
        {events.length === 0 && (
          <p className="text-slate-600 text-sm font-mono">Waiting for events...</p>
        )}
        {events.map((evt) => (
          <EventRow
            key={evt.event_id}
            evt={evt}
            isExpanded={isExpanded(evt.event_id)}
            onToggle={() => handleToggle(evt.event_id)}
          />
        ))}
      </div>
    </div>
  );
}
