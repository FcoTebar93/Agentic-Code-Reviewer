import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { APP_BUTTON_TAB, cx } from "./theme";

/** Single workspace: pipeline graph + execution log share one view. */
export type MainWorkspaceSectionId = "pipeline";

export const MAIN_WORKSPACE_SECTION_IDS: MainWorkspaceSectionId[] = ["pipeline"];

/** Legacy URLs used `main=events`; normalize to the unified pipeline view. */
export function normalizeMainWorkspaceSectionFromUrl(
  raw: string | null,
): MainWorkspaceSectionId {
  if (raw === "pipeline" || raw === "events") return "pipeline";
  return "pipeline";
}

export function isMainWorkspaceSectionId(s: string): s is MainWorkspaceSectionId {
  return s === "pipeline";
}

type Props = {
  active: MainWorkspaceSectionId;
  onChange: (id: MainWorkspaceSectionId) => void;
  panels: Record<MainWorkspaceSectionId, ReactNode>;
};

export function MainWorkspaceNav({ active, onChange, panels }: Props) {
  const { t } = useTranslation();
  const sections: { id: MainWorkspaceSectionId; label: string; hint: string }[] = [
    {
      id: "pipeline",
      label: t("workspace.pipeline.label"),
      hint: t("workspace.pipeline.hint"),
    },
  ];

  if (sections.length === 1) {
    const only = sections[0].id;
    return (
      <div className="flex flex-col min-h-0 flex-1 min-w-0 basis-0">
        {panels[only]}
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-0 flex-1 gap-2 lg:gap-3 lg:flex-row">
      <nav
        className="app-divider flex shrink-0 flex-row gap-1 border-b pb-2 lg:w-[9rem] lg:flex-col lg:border-b-0 lg:border-r lg:pb-0 lg:pr-3"
        aria-label={t("workspace.ariaLabel")}
      >
        <span className="app-section-title mb-1 hidden px-1 text-[9px] lg:block">
          {t("workspace.label")}
        </span>
        <div
          className="flex flex-row lg:flex-col gap-1 flex-1 lg:flex-none"
          role="tablist"
        >
          {sections.map(({ id, label, hint }, index) => {
            const isOn = active === id;
            const k = index + 1;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={isOn}
                id={`main-tab-${id}`}
                aria-controls={`main-panel-${id}`}
                aria-keyshortcuts={`Alt+${k}`}
                title={`${hint} · Alt+${k}`}
                onClick={() => onChange(id)}
                className={cx(
                  APP_BUTTON_TAB,
                  "text-left lg:w-full lg:justify-start",
                  isOn && "app-button-tab-active",
                )}
              >
                <span className="block font-semibold">{label}</span>
                <span className="app-muted-text mt-0.5 hidden text-[9px] leading-tight lg:block">
                  {hint}
                </span>
              </button>
            );
          })}
        </div>
      </nav>

      <div className="relative flex-1 min-h-0 min-w-0 flex flex-col">
        {sections.map(({ id }) => (
          <div
            key={id}
            role="tabpanel"
            id={`main-panel-${id}`}
            aria-labelledby={`main-tab-${id}`}
            hidden={active !== id}
            className={
              active === id
                ? "flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden"
                : ""
            }
          >
            {panels[id]}
          </div>
        ))}
      </div>
    </div>
  );
}
