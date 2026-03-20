import { useEffect, useRef } from "react";

const PLAN_QUERY = "plan";

export function usePlanUrlSync(
  activePlanId: string | null,
  setActivePlanId: (id: string | null) => void,
  knownPlanIds: string[],
): void {
  const initialized = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get(PLAN_QUERY)?.trim();
    if (!fromUrl) {
      initialized.current = true;
      return;
    }
    if (knownPlanIds.length === 0) {
      return;
    }
    if (knownPlanIds.includes(fromUrl)) {
      setActivePlanId(fromUrl);
    }
    initialized.current = true;
  }, [knownPlanIds, setActivePlanId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!initialized.current) return;

    const url = new URL(window.location.href);
    if (activePlanId) {
      url.searchParams.set(PLAN_QUERY, activePlanId);
    } else {
      url.searchParams.delete(PLAN_QUERY);
    }
    const next = `${url.pathname}${url.search}${url.hash}`;
    const cur = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (next !== cur) {
      window.history.replaceState(null, "", next);
    }
  }, [activePlanId]);
}
