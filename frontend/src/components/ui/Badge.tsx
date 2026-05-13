import type { ReactNode } from "react";
import { cx } from "./theme";

interface BadgeProps {
  children: ReactNode;
  className?: string;
}

export function Badge({ children, className }: BadgeProps) {
  return (
    <span
      className={cx("app-badge", className)}
    >
      {children}
    </span>
  );
}

