import { useEffect, useRef, useState } from "react";
import {
  normalizeMainWorkspaceSectionFromUrl,
  type MainWorkspaceSectionId,
} from "../components/ui/MainWorkspaceNav";
import { DEFAULT_RIGHT_PANEL_TAB, normalizeRightPanelTabFromUrl, type RightPanelTabId } from "../components/ui/RightPanelTabs";

const PLAN_QUERY = "plan";
const TAB_QUERY = "tab";
const MAIN_QUERY = "main";

export function getDashboardHref( planId: string | null, tab: RightPanelTabId, mainSection: MainWorkspaceSectionId = "pipeline"): string {
  if (typeof window === "undefined") return "";
  const url = new URL(window.location.href);
  if (planId) {
    url.searchParams.set(PLAN_QUERY, planId);
  } else {
    url.searchParams.delete(PLAN_QUERY);
  }
  if (tab === DEFAULT_RIGHT_PANEL_TAB) {
    url.searchParams.delete(TAB_QUERY);
  } else {
    url.searchParams.set(TAB_QUERY, tab);
  }
  if (mainSection === "pipeline") {
    url.searchParams.delete(MAIN_QUERY);
  } else {
    url.searchParams.set(MAIN_QUERY, mainSection);
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function useDashboardUrlSync(
  activePlanId: string | null,
  setActivePlanId: (id: string | null) => void,
  knownPlanIds: string[],
  rightTab: RightPanelTabId,
  setRightTab: (t: RightPanelTabId) => void,
  mainSection: MainWorkspaceSectionId,
  setMainSection: (s: MainWorkspaceSectionId) => void,
): void {
  const planInitialized = useRef(false);
  const [tabHydrated, setTabHydrated] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const normalized = normalizeRightPanelTabFromUrl(params.get(TAB_QUERY));
    if (normalized) {
      setRightTab(normalized);
    }
    setMainSection(normalizeMainWorkspaceSectionFromUrl(params.get(MAIN_QUERY)));
    setTabHydrated(true);
  }, [setRightTab, setMainSection]);

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

      const normalizedTab = normalizeRightPanelTabFromUrl(params.get(TAB_QUERY));
      if (normalizedTab) {
        setRightTab(normalizedTab);
      } else {
        setRightTab(DEFAULT_RIGHT_PANEL_TAB);
      }

      setMainSection(normalizeMainWorkspaceSectionFromUrl(params.get(MAIN_QUERY)));

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
  }, [setActivePlanId, setRightTab, setMainSection]);

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

    if (rightTab === DEFAULT_RIGHT_PANEL_TAB) {
      url.searchParams.delete(TAB_QUERY);
    } else {
      url.searchParams.set(TAB_QUERY, rightTab);
    }

    if (mainSection === "pipeline") {
      url.searchParams.delete(MAIN_QUERY);
    } else {
      url.searchParams.set(MAIN_QUERY, mainSection);
    }

    const next = `${url.pathname}${url.search}${url.hash}`;
    const cur = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (next !== cur) {
      window.history.replaceState(null, "", next);
    }
  }, [activePlanId, rightTab, mainSection, tabHydrated, knownPlanIds.length]);
}
