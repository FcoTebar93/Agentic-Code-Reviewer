interface PlanFilterChipsProps {
  planIds: string[];
  activePlanId: string | null;
  onChange: (planId: string | null) => void;
}

export function PlanFilterChips({
  planIds,
  activePlanId,
  onChange,
}: PlanFilterChipsProps) {
  if (planIds.length === 0) return null;

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => onChange(null)}
        className={`px-2 py-0.5 rounded-md text-[10px] font-mono border transition-colors ${
          activePlanId === null
            ? "bg-white text-black border-neutral-600"
            : "bg-neutral-900 text-neutral-400 border-neutral-700 hover:bg-neutral-800 hover:text-neutral-200"
        }`}
      >
        All
      </button>
      {planIds.map((pid) => (
        <button
          key={pid}
          type="button"
          onClick={() => onChange(pid)}
          className={`px-2 py-0.5 rounded-md text-[10px] font-mono border truncate max-w-[80px] transition-colors ${
            activePlanId === pid
              ? "bg-white text-black border-neutral-600"
              : "bg-neutral-900 text-neutral-400 border-neutral-700 hover:bg-neutral-800 hover:text-neutral-200"
          }`}
          title={pid}
        >
          {pid.slice(0, 8)}…
        </button>
      ))}
    </div>
  );
}

