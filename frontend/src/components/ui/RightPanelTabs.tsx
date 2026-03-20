import React, { useLayoutEffect, useState } from "react";

export type RightPanelTabId =
  | "launch"
  | "metrics"
  | "detail"
  | "approvals"
  | "more";

export const RIGHT_PANEL_TAB_IDS: RightPanelTabId[] = [
  "launch",
  "metrics",
  "detail",
  "approvals",
  "more",
];

export function isRightPanelTabId(s: string): s is RightPanelTabId {
  return (RIGHT_PANEL_TAB_IDS as string[]).includes(s);
}

const TABS: { id: RightPanelTabId; label: string }[] = [
  { id: "launch", label: "Lanzar" },
  { id: "metrics", label: "Métricas" },
  { id: "detail", label: "Detalle" },
  { id: "approvals", label: "Aprobaciones" },
  { id: "more", label: "Más" },
];

type Props = {
  active: RightPanelTabId;
  onChange: (id: RightPanelTabId) => void;
  panels: Record<RightPanelTabId, React.ReactNode>;
};

export function RightPanelTabs({ active, onChange, panels }: Props) {
  const [visited, setVisited] = useState<Set<RightPanelTabId>>(
    () => new Set([active]),
  );

  useLayoutEffect(() => {
    setVisited((prev) => new Set(prev).add(active));
  }, [active]);

  return (
    <div className="flex flex-col min-h-0 flex-1 gap-2 overflow-hidden">
      <div
        className="flex flex-wrap gap-1 border-b border-neutral-800 pb-2 -mb-px"
        role="tablist"
        aria-label="Panel lateral"
      >
        {TABS.map(({ id, label }, index) => {
          const isActive = active === id;
          const k = index + 3;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={isActive}
              id={`tab-${id}`}
              aria-controls={`panel-${id}`}
              aria-keyshortcuts={`Alt+${k}`}
              title={`${label} · Alt+${k}`}
              onClick={() => onChange(id)}
              className={`text-[11px] font-mono px-2.5 py-1.5 rounded-t border-b-2 transition-colors ${
                isActive
                  ? "border-neutral-100 text-neutral-100 bg-neutral-900/80"
                  : "border-transparent text-neutral-500 hover:text-neutral-300 hover:bg-neutral-900/40"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>
      <div className="flex-1 min-h-0 min-w-0 relative">
        {TABS.map(({ id }) => {
          const mounted = visited.has(id) || id === active;
          return (
            <div
              key={id}
              role="tabpanel"
              id={`panel-${id}`}
              aria-labelledby={`tab-${id}`}
              hidden={active !== id}
              className={
                active === id
                  ? "absolute inset-0 overflow-y-auto pr-1 space-y-4"
                  : ""
              }
            >
              {mounted ? panels[id] : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
