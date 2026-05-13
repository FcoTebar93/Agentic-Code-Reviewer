import { useTranslation } from "react-i18next";
import { cx } from "./theme";

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
  const { t } = useTranslation();

  if (planIds.length === 0) return null;

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => onChange(null)}
        className={cx(
          "app-chip px-2.5 py-1",
          activePlanId === null && "app-chip-active",
        )}
      >
        {t("planFilter.all")}
      </button>
      {planIds.map((pid) => (
        <button
          key={pid}
          type="button"
          onClick={() => onChange(pid)}
          className={cx(
            "app-chip max-w-[88px] truncate px-2.5 py-1",
            activePlanId === pid && "app-chip-active",
          )}
          title={pid}
        >
          {pid.slice(0, 8)}…
        </button>
      ))}
    </div>
  );
}

