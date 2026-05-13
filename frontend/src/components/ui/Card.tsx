import type { ReactNode } from "react";
import { cx } from "./theme";

interface CardProps {
  children: ReactNode;
  className?: string;
  compact?: boolean;
}

export function Card({ children, className, compact = false }: CardProps) {
  return (
    <div
      className={cx(
        "app-surface",
        compact ? "p-4" : "p-5 xl:p-6",
        className,
      )}
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
    <div className={cx("app-section-header", className)}>
      <h2 className="app-section-title">
        {children}
      </h2>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

