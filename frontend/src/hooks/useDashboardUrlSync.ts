import { useEffect, useRef, useState } from "react";
import { isRightPanelTabId, type RightPanelTabId } from "../components/ui/RightPanelTabs";

const PLAN_QUERY = "plan";
const TAB_QUERY = "tab";

export function useDashboardUrlSync(
  activePlanId: string | null,
  setActivePlanId: (id: string | null) => void,
  knownPlanIds: string[],
  rightTab: RightPanelTabId,
  setRightTab: (t: RightPanelTabId) => void,
): void {
  const planInitialized = useRef(false);
  const [tabHydrated, setTabHydrated] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const raw = params.get(TAB_QUERY);
    if (raw && isRightPanelTabId(raw)) {
      setRightTab(raw);
    }
    setTabHydrated(true);
  }, [setRightTab]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get(PLAN_QUERY)?.trim();
    if (!fromUrl) {
      planInitialized.current = true;
      return;
    }
    if (knownPlanIds.length === 0) {
      return;
    }
    if (knownPlanIds.includes(fromUrl)) {
      setActivePlanId(fromUrl);
    }
    planInitialized.current = true;
  }, [knownPlanIds, setActivePlanId]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const applySearchToState = () => {
      const params = new URLSearchParams(window.location.search);

      const rawTab = params.get(TAB_QUERY);
      if (rawTab && isRightPanelTabId(rawTab)) {
        setRightTab(rawTab);
      } else {
        setRightTab("launch");
      }

      const fromPlan = params.get(PLAN_QUERY)?.trim() ?? "";
      if (!fromPlan) {
        setActivePlanId(null);
      } else {
        setActivePlanId(fromPlan);
      }

      planInitialized.current = true;
    };

    const onPopState = () => {
      applySearchToState();
    };

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [setActivePlanId, setRightTab]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!tabHydrated) return;

    const url = new URL(window.location.href);

    if (planInitialized.current) {
      if (activePlanId) {
        url.searchParams.set(PLAN_QUERY, activePlanId);
      } else {
        url.searchParams.delete(PLAN_QUERY);
      }
    }

    if (rightTab === "launch") {
      url.searchParams.delete(TAB_QUERY);
    } else {
      url.searchParams.set(TAB_QUERY, rightTab);
    }

    const next = `${url.pathname}${url.search}${url.hash}`;
    const cur = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (next !== cur) {
      window.history.replaceState(null, "", next);
    }
  }, [activePlanId, rightTab, tabHydrated, knownPlanIds.length]);
}
