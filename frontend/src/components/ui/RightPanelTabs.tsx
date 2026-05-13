import React, { useLayoutEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { APP_BUTTON_TAB, cx } from "./theme";

export type RightPanelTabId = "metrics" | "detail" | "approvals" | "more";

export const DEFAULT_RIGHT_PANEL_TAB: RightPanelTabId = "metrics";

export const RIGHT_PANEL_TAB_IDS: RightPanelTabId[] = [
  "metrics",
  "detail",
  "approvals",
  "more",
];

export function isRightPanelTabId(s: string): s is RightPanelTabId {
  return (RIGHT_PANEL_TAB_IDS as string[]).includes(s);
}

export function normalizeRightPanelTabFromUrl(raw: string | null): RightPanelTabId | null {
  if (raw == null || raw === "") return null;
  if (raw === "launch") return DEFAULT_RIGHT_PANEL_TAB;
  if (isRightPanelTabId(raw)) return raw;
  return null;
}

type Props = {
  active: RightPanelTabId;
  onChange: (id: RightPanelTabId) => void;
  panels: Record<RightPanelTabId, React.ReactNode>;
};

export function RightPanelTabs({ active, onChange, panels }: Props) {
  const { t } = useTranslation();
  const tabs: { id: RightPanelTabId; label: string }[] = [
    { id: "metrics", label: t("rightTabs.metrics") },
    { id: "detail", label: t("rightTabs.detail") },
    { id: "approvals", label: t("rightTabs.approvals") },
    { id: "more", label: t("rightTabs.more") },
  ];
  const [visited, setVisited] = useState<Set<RightPanelTabId>>(
    () => new Set([active]),
  );

  useLayoutEffect(() => {
    setVisited((prev) => new Set(prev).add(active));
  }, [active]);

  return (
    <div className="flex flex-col min-h-0 flex-1 gap-2 overflow-hidden">
      <div
        className="app-divider -mb-px flex flex-wrap gap-1 border-b pb-2"
        role="tablist"
        aria-label={t("rightTabs.ariaLabel")}
      >
        {tabs.map(({ id, label }, index) => {
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
              className={cx(APP_BUTTON_TAB, isActive && "app-button-tab-active")}
            >
              {label}
            </button>
          );
        })}
      </div>
      <div className="flex-1 min-h-0 min-w-0 relative">
        {tabs.map(({ id }) => {
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
