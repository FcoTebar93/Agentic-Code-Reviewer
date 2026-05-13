import type { ReactNode } from "react";

interface HeaderBarProps {
  title: string;
  subtitle?: string;
  shortcutsHint?: string;
  right?: ReactNode;
}

export function HeaderBar({
  title,
  subtitle,
  shortcutsHint,
  right,
}: HeaderBarProps) {
  return (
    <header className="app-header flex items-center justify-between gap-4 px-4 py-4 md:px-6">
      <div className="min-w-0 flex flex-col gap-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="app-header-title">
            {title}
          </span>
          {subtitle && (
            <span className="app-header-subtitle">
              {subtitle}
            </span>
          )}
        </div>
        {shortcutsHint && (
          <p className="app-shortcut-hint hidden truncate sm:block">
            {shortcutsHint}
          </p>
        )}
      </div>
      {right && <div className="flex shrink-0 items-center gap-3">{right}</div>}
    </header>
  );
}

