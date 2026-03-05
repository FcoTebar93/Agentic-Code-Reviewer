import type { ReactNode } from "react";

interface StatRowProps {
  label: ReactNode;
  value: ReactNode;
  subtle?: boolean;
}

export function StatRow({ label, value, subtle = false }: StatRowProps) {
  return (
    <div className="flex justify-between">
      <dt
        className={
          subtle
            ? "text-neutral-500 text-[10px] font-mono"
            : "text-neutral-500 text-xs font-mono"
        }
      >
        {label}
      </dt>
      <dd
        className={
          subtle
            ? "text-neutral-200 text-[10px] font-mono"
            : "text-neutral-200 text-xs font-mono"
        }
      >
        {value}
      </dd>
    </div>
  );
}

