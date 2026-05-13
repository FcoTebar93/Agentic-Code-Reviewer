import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { BaseEvent } from "../types/events";
import { EVENT_COLORS } from "../types/events";
import { postJson } from "../api/api";
import { Card, SectionHeader } from "./ui/Card";
import { CodePanel } from "./ui/CodePanel";
import {
  APP_BUTTON_SECONDARY,
  APP_BUTTON_SUBTLE,
  APP_EMPTY_STATE,
  cx,
} from "./ui/theme";
import {
  formatLocalizedTime,
  translateEventType,
} from "../i18n/formatters";

interface Props {
  events: BaseEvent[];
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

function extractReasoning(
  payload: Record<string, unknown>,
  eventType: string | undefined,
  labels: {
    suggestedChanges: string;
    spec: string;
    tests: string;
  },
): string {
  if (eventType === "pipeline.conclusion") {
    const c = payload["conclusion_text"];
    if (typeof c === "string" && c.trim().length > 0) return c.trim();
  }

  if (eventType === "plan.revision_suggested") {
    const summary = payload["summary"];
    const suggestions = payload["suggestions"];
    let text = "";
    if (typeof summary === "string" && summary.trim().length > 0) {
      text += summary.trim();
    }
    if (Array.isArray(suggestions) && suggestions.length > 0) {
      const suggLines = suggestions
        .filter((s): s is string => typeof s === "string" && s.trim().length > 0)
        .map((s) => `- ${s.trim()}`)
        .join("\n");
      if (suggLines) {
        text = text
          ? `${text}\n\n${labels.suggestedChanges}:\n${suggLines}`
          : suggLines;
      }
    }
    if (text) return text;
  }

  if (eventType === "spec.generated") {
    const spec = payload["spec_text"];
    const tests = payload["test_suggestions"];
    let text = "";
    if (typeof spec === "string" && spec.trim().length > 0) {
      text += `${labels.spec}:\n${spec.trim()}`;
    }
    if (typeof tests === "string" && tests.trim().length > 0) {
      text += (text ? "\n\n" : "") + `${labels.tests}:\n${tests.trim()}`;
    }
    if (text) return text;
  }

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
  if (eventType !== "code.generated" && eventType !== "qa.passed") return null;
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

interface EventRowProps {
  evt: BaseEvent;
  isExpanded: boolean;
  onToggle: () => void;
  language: string;
}

function EventRow({ evt, isExpanded, onToggle, language }: EventRowProps) {
  const { t } = useTranslation();
  const reasoning = extractReasoning(evt.payload, evt.event_type, {
    suggestedChanges: t("eventFeed.suggestedChanges"),
    spec: t("eventFeed.spec"),
    tests: t("eventFeed.tests"),
  });
  const prUrl = extractPrUrl(evt.event_type, evt.payload);
  const codeInfo = extractCode(evt.event_type, evt.payload);
  const fileList = extractFiles(evt.event_type, evt.payload);
  const plannedFiles = evt.event_type === "plan.created" ? extractPlannedFiles(evt.payload) : [];
  const isConclusion = evt.event_type === "pipeline.conclusion";
  const isPlanRevision = evt.event_type === "plan.revision_suggested";
  const expandable = !!(reasoning || prUrl || codeInfo || fileList.length || plannedFiles.length || isConclusion || isPlanRevision);

  const color = EVENT_COLORS[evt.event_type] ?? "#6b7280";
  const label = translateEventType(t, evt.event_type);

  const inlineFilePath =
    (evt.event_type === "code.generated" || evt.event_type === "qa.passed") &&
    typeof evt.payload["file_path"] === "string"
      ? (evt.payload["file_path"] as string)
      : null;

  const open = expandable ? isExpanded : true;

  const [replanLoading, setReplanLoading] = useState(false);

  async function handleReplanClick(e: React.MouseEvent<HTMLButtonElement>) {
    e.stopPropagation();
    if (replanLoading) return;
    setReplanLoading(true);
    try {
      await postJson("/api/replan", evt.payload);
    } catch (err) {
      console.error("Replan request error", err);
    } finally {
      setReplanLoading(false);
    }
  }

  return (
    <div className="app-surface-soft overflow-hidden text-xs font-mono">
      <div
        className={cx(
          "flex items-start gap-2 px-3 py-2.5 transition-colors",
          expandable && "cursor-pointer select-none hover:bg-[rgba(40,42,54,0.52)]",
        )}
        onClick={() => expandable && onToggle()}
      >
        <span className="app-meta-text flex-none w-20 pt-px">
          {formatLocalizedTime(evt.timestamp, language)}
        </span>
        <span
          className="app-badge flex-none whitespace-nowrap border-transparent text-white"
          style={{
            backgroundColor: `${color}2a`,
            boxShadow: `inset 0 0 0 1px ${color}66`,
          }}
        >
          {label}
        </span>
        <span className="truncate flex-1 text-[var(--color-silver-text)]">
          {evt.producer}
          {inlineFilePath && (
            <span className="ml-2 text-[var(--color-electric-cyan)]">{inlineFilePath}</span>
          )}
          <span className="app-muted-text ml-2">#{shortId(evt.event_id)}</span>
        </span>
        {prUrl && !open && (
          <span className="ml-1 flex-none text-[var(--color-electric-cyan)]">↗</span>
        )}
        {expandable && (
          <span className="app-muted-text ml-1 flex-none">
            {open ? "▾" : "▸"}
          </span>
        )}
      </div>

      {expandable && open && (
        <div className="app-divider space-y-3 border-t px-3 pb-3 pt-2">
          {isPlanRevision && (
            <div className="flex items-center justify-between gap-2">
              <p className="app-section-title text-[10px]">
                {t("eventFeed.replannerSuggestion")}
              </p>
              <button
                onClick={handleReplanClick}
                disabled={replanLoading}
                className={cx(
                  APP_BUTTON_SECONDARY,
                  "min-h-0 border-amber-500/50 px-2.5 py-1 text-[10px] text-amber-300",
                  !replanLoading && "hover:bg-amber-500/10",
                )}
              >
                {replanLoading
                  ? t("eventFeed.confirming")
                  : t("eventFeed.confirmReplan")}
              </button>
            </div>
          )}
          {prUrl && (
            <div>
              <p className="app-section-title mb-1 text-[10px]">
                {t("eventFeed.pullRequest")}
              </p>
              <a
                href={prUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="break-all text-[var(--color-electric-cyan)] underline transition-colors hover:text-[var(--color-polar-white)]"
                onClick={(e) => e.stopPropagation()}
              >
                {prUrl}
              </a>
            </div>
          )}

          {plannedFiles.length > 0 && (
            <div>
              <p className="app-section-title mb-1.5 text-[10px]">
                {t("eventFeed.plannedFiles")} ({plannedFiles.length})
              </p>
              <div className="space-y-0.5">
                {plannedFiles.map((fp) => (
                  <div key={fp} className="flex items-center gap-1 text-[var(--color-electric-cyan)]">
                    <span className="app-muted-text">→</span> {fp}
                  </div>
                ))}
              </div>
            </div>
          )}

          {fileList.length > 0 && (
            <div>
              <p className="app-section-title mb-1.5 text-[10px]">
                {isConclusion
                  ? t("eventFeed.filesChanged")
                  : t("eventFeed.filesInPr")}{" "}
                ({fileList.length})
              </p>
              <div className="space-y-0.5">
                {fileList.map((fp) => (
                  <div key={fp} className="flex items-center gap-1 text-[var(--color-electric-cyan)]">
                    <span className="app-muted-text">+</span> {fp}
                  </div>
                ))}
              </div>
            </div>
          )}

          {codeInfo && (
            <div>
              <p className="app-section-title mb-1.5 text-[10px]">
                {evt.event_type === "qa.passed"
                  ? t("eventFeed.reviewedCode")
                  : t("eventFeed.generatedCode")}{" "}
                — {codeInfo.filePath}
              </p>
              <CodePanel code={codeInfo.code} language={codeInfo.language} />
            </div>
          )}

          {reasoning && (
            <div>
              <p className="app-section-title mb-1.5 text-[10px]">
                {isConclusion
                  ? t("eventFeed.conclusion")
                  : t("eventFeed.agentReasoning")}
              </p>
              <p className="leading-relaxed whitespace-pre-wrap text-[var(--color-silver-text)]">
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
  const { t, i18n } = useTranslation();
  const [collapseAll, setCollapseAll] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

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
    <Card className="flex flex-col h-full">
      <SectionHeader
        right={
          events.length > 0 && (
            <button
              onClick={handleCollapseExpandAll}
              className={cx(APP_BUTTON_SUBTLE, "min-h-0 px-0 py-0 text-[10px]")}
            >
              {collapseAll ? t("eventFeed.expandAll") : t("eventFeed.collapseAll")}
            </button>
          )
        }
      >
        {t("eventFeed.title")}{" "}
        <span className="app-muted-text normal-case">({events.length})</span>
      </SectionHeader>

      <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
        {events.length === 0 && (
          <p className={`${APP_EMPTY_STATE} text-sm`}>
            {t("eventFeed.waiting")}
          </p>
        )}
        {events.map((evt) => (
          <EventRow
            key={evt.event_id}
            evt={evt}
            isExpanded={isExpanded(evt.event_id)}
            onToggle={() => handleToggle(evt.event_id)}
            language={i18n.resolvedLanguage || i18n.language || "es"}
          />
        ))}
      </div>
    </Card>
  );
}
