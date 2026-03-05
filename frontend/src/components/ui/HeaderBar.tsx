import type { ReactNode } from "react";

interface HeaderBarProps {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}

export function HeaderBar({ title, subtitle, right }: HeaderBarProps) {
  return (
    <header className="border-b border-neutral-800 bg-black/80 backdrop-blur-sm px-6 py-3 flex items-center justify-between flex-none">
      <div className="flex items-center gap-3">
        <span className="text-white font-mono font-semibold text-lg tracking-tight">
          {title}
        </span>
        {subtitle && (
          <span className="text-neutral-500 text-sm font-mono">
            {subtitle}
          </span>
        )}
      </div>
      {right && <div className="flex items-center gap-3">{right}</div>}
    </header>
  );
}

