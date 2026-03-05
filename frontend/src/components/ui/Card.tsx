import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div
      className={`bg-neutral-900 rounded-xl border border-neutral-800 p-4 ${
        className ?? ""
      }`}
    >
      {children}
    </div>
  );
}

interface SectionHeaderProps {
  children: ReactNode;
  right?: ReactNode;
  className?: string;
}

export function SectionHeader({ children, right, className }: SectionHeaderProps) {
  return (
    <div
      className={`flex items-center justify-between mb-3 ${
        className ?? ""
      }`}
    >
      <h2 className="text-neutral-400 text-xs font-mono uppercase tracking-widest">
        {children}
      </h2>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

