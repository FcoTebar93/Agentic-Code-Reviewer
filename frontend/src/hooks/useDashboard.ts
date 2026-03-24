import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { useWebSocket } from "./useWebSocket";
import { useDashboardKeyboardShortcuts } from "./useDashboardKeyboardShortcuts";
import { useIsNarrowDrawerViewport } from "./useMediaQuery";
import { useDrawerFocusManagement } from "./useDrawerFocusManagement";
import { useDeepLinkDrawer } from "./useDeepLinkDrawer";
import { getDashboardHref, useDashboardUrlSync } from "./useDashboardUrlSync";
import type { MainWorkspaceSectionId } from "../components/ui/MainWorkspaceNav";
import type { RightPanelTabId } from "../components/ui/RightPanelTabs";
import type { BaseEvent, PrApproval } from "../types/events";
import { postWithoutBody } from "../api/api";
import { extractPlanId, sortByTimestampDesc } from "../lib/dashboardUtils";

export interface DashboardProps {
  status: ReturnType<typeof useWebSocket>["status"];
  pendingApprovals: PrApproval[];
  panelToggleRef: RefObject<HTMLButtonElement>;
  rightDrawerOpen: boolean;
  setRightDrawerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  closeRightDrawer: () => void;
  rightPanelDrawerRef: RefObject<HTMLDivElement>;
  isNarrowDrawer: boolean;
  rightPanelAriaProps:
    | { role: "complementary"; "aria-label": string }
    | { role: "dialog"; "aria-modal": true; "aria-labelledby": string }
    | { "aria-hidden": true };
  mainSection: MainWorkspaceSectionId;
  setMainSectionWithHistory: (section: MainWorkspaceSectionId) => void;
  latestEvent: BaseEvent | null;
  knownPlanIds: string[];
  activePlanId: string | null;
  setActivePlanIdWithHistory: (planId: string | null) => void;
  visibleEvents: BaseEvent[];
  setVisibleEvents: React.Dispatch<React.SetStateAction<BaseEvent[]>>;
  setKnownPlanIds: React.Dispatch<React.SetStateAction<string[]>>;
  setActivePlanId: React.Dispatch<React.SetStateAction<string | null>>;
  pushUrlIfChanged: (overrides?: {
    planId?: string | null;
    rightTab?: RightPanelTabId;
    mainSection?: MainWorkspaceSectionId;
  }) => void;
  filteredEvents: BaseEvent[];
  activePlanMode: string | null;
  rightTab: RightPanelTabId;
  setRightTabFromPanel: (tab: RightPanelTabId) => void;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
}

export function useDashboard(wsUrl: string): DashboardProps {
  const { events, pendingApprovals, status } = useWebSocket(wsUrl);
  const [visibleEvents, setVisibleEvents] = useState<BaseEvent[]>(events);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [knownPlanIds, setKnownPlanIds] = useState<string[]>([]);
  const [rightTab, setRightTab] = useState<RightPanelTabId>("metrics");
  const [mainSection, setMainSection] =
    useState<MainWorkspaceSectionId>("pipeline");
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const isNarrowDrawer = useIsNarrowDrawerViewport();
  const rightPanelDrawerRef = useRef<HTMLDivElement>(null);
  const panelToggleRef = useRef<HTMLButtonElement>(null);

  const closeRightDrawer = useCallback(() => setRightDrawerOpen(false), []);

  useDrawerFocusManagement({
    open: rightDrawerOpen,
    isNarrowViewport: isNarrowDrawer,
    containerRef: rightPanelDrawerRef,
    returnFocusRef: panelToggleRef,
    onRequestClose: closeRightDrawer,
  });

  useDeepLinkDrawer(isNarrowDrawer, setRightDrawerOpen);

  type NavSnapshot = {
    planId: string | null;
    rightTab: RightPanelTabId;
    mainSection: MainWorkspaceSectionId;
  };

  const navRef = useRef<NavSnapshot>({
    planId: activePlanId,
    rightTab,
    mainSection,
  });
  navRef.current = { planId: activePlanId, rightTab, mainSection };

  const pushUrlIfChanged = useCallback((overrides?: Partial<NavSnapshot>) => {
    if (typeof window === "undefined") return;
    const s = { ...navRef.current, ...overrides };
    const next = getDashboardHref(s.planId, s.rightTab, s.mainSection);
    const cur = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (next !== cur) {
      window.history.pushState(null, "", next);
    }
  }, []);

  const setRightTabWithHistory = useCallback(
    (tab: RightPanelTabId) => {
      pushUrlIfChanged({ rightTab: tab });
      setRightTab(tab);
    },
    [pushUrlIfChanged],
  );

  const setRightTabFromPanel = useCallback(
    (tab: RightPanelTabId) => {
      setRightTabWithHistory(tab);
      if (isNarrowDrawer) setRightDrawerOpen(false);
    },
    [setRightTabWithHistory, isNarrowDrawer],
  );

  const setRightTabFromShortcut = useCallback(
    (tab: RightPanelTabId) => {
      setRightTabWithHistory(tab);
      if (isNarrowDrawer) setRightDrawerOpen(true);
    },
    [setRightTabWithHistory, isNarrowDrawer],
  );

  const setActivePlanIdWithHistory = useCallback(
    (planId: string | null) => {
      pushUrlIfChanged({ planId });
      setActivePlanId(planId);
    },
    [pushUrlIfChanged],
  );

  const setMainSectionWithHistory = useCallback(
    (section: MainWorkspaceSectionId) => {
      pushUrlIfChanged({ mainSection: section });
      setMainSection(section);
    },
    [pushUrlIfChanged],
  );

  useDashboardUrlSync(
    activePlanId,
    setActivePlanId,
    knownPlanIds,
    rightTab,
    setRightTab,
    mainSection,
    setMainSection,
  );

  useDashboardKeyboardShortcuts(
    setMainSectionWithHistory,
    setRightTabFromShortcut,
  );

  const prevPendingCount = useRef<number | null>(null);
  useEffect(() => {
    const n = pendingApprovals.length;
    const prev = prevPendingCount.current;
    prevPendingCount.current = n;
    if (prev !== null && n > prev && n > 0) {
      setRightTab("approvals");
      if (isNarrowDrawer) setRightDrawerOpen(true);
    }
  }, [pendingApprovals.length, isNarrowDrawer]);

  const prevEventsCount = useRef<number | null>(null);
  useEffect(() => {
    const n = events.length;
    const prev = prevEventsCount.current;
    prevEventsCount.current = n;
    if (prev !== null && n > prev && n > 0) {
      setMainSection("pipeline");
    }
  }, [events.length]);

  const filteredEvents = sortByTimestampDesc(
    activePlanId === null
      ? visibleEvents
      : visibleEvents.filter((e) => extractPlanId(e) === activePlanId),
  );
  const latestEvent = filteredEvents[0] ?? null;

  const activePlanMode =
    activePlanId === null
      ? null
      : (() => {
          const planCreated = filteredEvents.find(
            (e) =>
              e.event_type === "plan.created" &&
              extractPlanId(e) === activePlanId,
          );
          const mode = planCreated?.payload?.mode as string | undefined;
          return typeof mode === "string" && mode.trim() ? mode : null;
        })();

  useEffect(() => {
    setVisibleEvents(events);

    const ids: string[] = [];
    for (const ev of events) {
      const pid = extractPlanId(ev);
      if (pid && !ids.includes(pid)) {
        ids.push(pid);
      }
    }
    setKnownPlanIds(ids);
    setActivePlanId((prev) => {
      if (prev && ids.includes(prev)) return prev;
      if (prev === null && ids.length > 0) return ids[0];
      if (!prev && ids.length > 0) return ids[0];
      return prev;
    });
  }, [events]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => {
      if (mq.matches) setRightDrawerOpen(false);
    };
    mq.addEventListener("change", onChange);
    onChange();
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const rightPanelAriaProps =
    !isNarrowDrawer
      ? ({
          role: "complementary" as const,
          "aria-label": "Plan, métricas y herramientas",
        } as const)
      : rightDrawerOpen
        ? ({
            role: "dialog" as const,
            "aria-modal": true as const,
            "aria-labelledby": "right-drawer-title",
          } as const)
        : ({ "aria-hidden": true as const } as const);

  const onApprove = useCallback(
    (id: string) => postWithoutBody(`/api/approvals/${id}/approve`),
    [],
  );
  const onReject = useCallback(
    (id: string) => postWithoutBody(`/api/approvals/${id}/reject`),
    [],
  );

  return {
    status,
    pendingApprovals,
    panelToggleRef,
    rightDrawerOpen,
    setRightDrawerOpen,
    closeRightDrawer,
    rightPanelDrawerRef,
    isNarrowDrawer,
    rightPanelAriaProps,
    mainSection,
    setMainSectionWithHistory,
    latestEvent,
    knownPlanIds,
    activePlanId,
    setActivePlanIdWithHistory,
    visibleEvents,
    setVisibleEvents,
    setKnownPlanIds,
    setActivePlanId,
    pushUrlIfChanged,
    filteredEvents,
    activePlanMode,
    rightTab,
    setRightTabFromPanel,
    onApprove,
    onReject,
  };
}
