import type { ReactNode } from "react";

interface StatRowProps {
  label: ReactNode;
  value: ReactNode;
  subtle?: boolean;
}

export function StatRow({ label, value, subtle = false }: StatRowProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt
        className={
          subtle
            ? "app-meta-text text-[10px]"
            : "app-meta-text text-xs"
        }
      >
        {label}
      </dt>
      <dd
        className={
          subtle
            ? "text-[var(--color-polar-white)] text-[10px] font-mono text-right"
            : "text-[var(--color-polar-white)] text-xs font-mono text-right"
        }
      >
        {value}
      </dd>
    </div>
  );
}

