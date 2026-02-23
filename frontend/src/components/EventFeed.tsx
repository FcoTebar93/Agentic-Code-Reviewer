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

function extractPrUrl(eventType: string, payload: Record<string, unknown>): string {
  if (eventType !== "pr.created") return "";
  const url = payload["pr_url"];
  if (typeof url === "string" && url.startsWith("http")) return url;
  return "";
}

function EventRow({ evt }: { evt: BaseEvent }) {
  const [open, setOpen] = useState(false);
  const reasoning = extractReasoning(evt.payload);
  const prUrl = extractPrUrl(evt.event_type, evt.payload);
  const expandable = reasoning || prUrl;
  const color = EVENT_COLORS[evt.event_type] ?? "#6b7280";
  const label = EVENT_LABELS[evt.event_type] ?? evt.event_type;

  return (
    <div className="bg-slate-800 rounded-lg overflow-hidden text-xs font-mono">
      {/* Main row */}
      <div
        className={`flex items-start gap-2 px-3 py-2 ${expandable ? "cursor-pointer hover:bg-slate-750" : ""}`}
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
          <span className="text-slate-600 ml-2">#{shortId(evt.event_id)}</span>
        </span>
        {prUrl && !open && (
          <span className="text-green-500 flex-none ml-1">↗</span>
        )}
        {expandable && (
          <span className="text-slate-600 flex-none ml-1 select-none">
            {open ? "▾" : "▸"}
          </span>
        )}
      </div>

      {/* Expanded panel */}
      {expandable && open && (
        <div className="px-3 pb-3 pt-1 border-t border-slate-700/60 space-y-2">
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
          {reasoning && (
            <div>
              <p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1.5">
                Agent reasoning
              </p>
              <p className="text-slate-300 leading-relaxed">{reasoning}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function EventFeed({ events }: Props) {
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4 flex flex-col h-full">
      <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3 flex-none">
        Event Feed{" "}
        <span className="text-slate-600 normal-case">({events.length} events)</span>
        <span className="text-slate-700 normal-case ml-2 text-[10px]">
          — click rows with ▸ to expand reasoning
        </span>
      </h2>

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
