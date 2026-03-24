import type { ReactNode } from "react";

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

const SECTIONS: { id: MainWorkspaceSectionId; label: string; hint: string }[] = [
  {
    id: "pipeline",
    label: "Plan y ejecución",
    hint: "Agentes activos arriba, registro del plan abajo",
  },
];

type Props = {
  active: MainWorkspaceSectionId;
  onChange: (id: MainWorkspaceSectionId) => void;
  panels: Record<MainWorkspaceSectionId, ReactNode>;
};

export function MainWorkspaceNav({ active, onChange, panels }: Props) {
  if (SECTIONS.length === 1) {
    const only = SECTIONS[0].id;
    return (
      <div className="flex flex-col min-h-0 flex-1 min-w-0 basis-0">
        {panels[only]}
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-0 flex-1 gap-2 lg:gap-3 lg:flex-row">
      <nav
        className="flex flex-row lg:flex-col gap-1 shrink-0 border-b border-neutral-800 pb-2 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-3 lg:w-[8.5rem]"
        aria-label="Vista principal"
      >
        <span className="hidden lg:block text-[9px] font-mono text-neutral-600 uppercase tracking-widest mb-1 px-1">
          Vista
        </span>
        <div
          className="flex flex-row lg:flex-col gap-1 flex-1 lg:flex-none"
          role="tablist"
        >
          {SECTIONS.map(({ id, label, hint }, index) => {
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
                className={`text-left text-[11px] font-mono px-2.5 py-2 rounded-lg border transition-colors lg:w-full ${
                  isOn
                    ? "border-neutral-500 bg-neutral-800/80 text-neutral-100"
                    : "border-transparent text-neutral-500 hover:text-neutral-300 hover:bg-neutral-900/60"
                }`}
              >
                <span className="block font-semibold">{label}</span>
                <span className="hidden lg:block text-[9px] text-neutral-600 mt-0.5 leading-tight">
                  {hint}
                </span>
              </button>
            );
          })}
        </div>
      </nav>

      <div className="relative flex-1 min-h-0 min-w-0 flex flex-col">
        {SECTIONS.map(({ id }) => (
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
