import type { BaseEvent } from "../types/events";
import { EVENT_COLORS } from "../types/events";

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

export function EventFeed({ events }: Props) {
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4 flex flex-col h-full">
      <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3 flex-none">
        Event Feed{" "}
        <span className="text-slate-600 normal-case">
          ({events.length} events)
        </span>
      </h2>

      <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
        {events.length === 0 && (
          <p className="text-slate-600 text-sm font-mono">
            Waiting for events...
          </p>
        )}
        {events.map((evt) => (
          <div
            key={evt.event_id}
            className="flex items-start gap-2 bg-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
          >
            <span className="text-slate-500 flex-none w-20 pt-px">
              {formatTime(evt.timestamp)}
            </span>
            <span
              className="rounded px-1.5 py-0.5 font-semibold flex-none text-white"
              style={{
                backgroundColor:
                  EVENT_COLORS[evt.event_type] ?? "#6b7280",
                opacity: 0.85,
              }}
            >
              {evt.event_type}
            </span>
            <span className="text-slate-400 truncate">
              {evt.producer}
              <span className="text-slate-600 ml-2">
                #{shortId(evt.event_id)}
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
