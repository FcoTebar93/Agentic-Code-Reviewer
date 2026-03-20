import type { ReactNode } from "react";

interface HeaderBarProps {
  title: string;
  subtitle?: string;
  shortcutsHint?: string;
  right?: ReactNode;
}

export function HeaderBar({title,subtitle,shortcutsHint,right}: HeaderBarProps) {
  return (
    <header className="border-b border-neutral-800 bg-black/80 backdrop-blur-sm px-6 py-3 flex items-center justify-between flex-none gap-4">
      <div className="flex flex-col gap-0.5 min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-white font-mono font-semibold text-lg tracking-tight">
            {title}
          </span>
          {subtitle && (
            <span className="text-neutral-500 text-sm font-mono">
              {subtitle}
            </span>
          )}
        </div>
        {shortcutsHint && (
          <p className="hidden sm:block text-[10px] font-mono text-neutral-600 truncate">
            {shortcutsHint}
          </p>
        )}
      </div>
      {right && <div className="flex items-center gap-3 shrink-0">{right}</div>}
    </header>
  );
}

