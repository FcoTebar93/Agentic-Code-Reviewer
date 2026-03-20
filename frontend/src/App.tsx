import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useDashboardKeyboardShortcuts } from "./hooks/useDashboardKeyboardShortcuts";
import { useIsNarrowDrawerViewport } from "./hooks/useMediaQuery";
import { useDrawerFocusManagement } from "./hooks/useDrawerFocusManagement";
import { useDeepLinkDrawer } from "./hooks/useDeepLinkDrawer";
import { getDashboardHref, useDashboardUrlSync } from "./hooks/useDashboardUrlSync";
import { PipelineGraph } from "./components/PipelineGraph";
import { EventFeed } from "./components/EventFeed";
import { ActivePlanBar } from "./components/ActivePlanBar";
import { HeaderBar } from "./components/ui/HeaderBar";
import { PlanFilterChips } from "./components/ui/PlanFilterChips";
import { PanelTabFallback } from "./components/ui/PanelTabFallback";
import { MainWorkspaceNav, type MainWorkspaceSectionId } from "./components/ui/MainWorkspaceNav";
import { RightPanelTabs, type RightPanelTabId } from "./components/ui/RightPanelTabs";
import type { BaseEvent } from "./types/events";
import { postWithoutBody } from "./api/gatewayClient";
import { getGatewayWsUrl } from "./lib/gatewayConfig";

const LazyPlanForm = lazy(() =>
  import("./components/PlanForm").then((m) => ({ default: m.PlanForm })),
);
const LazyPlanMetrics = lazy(() =>
  import("./components/PlanMetrics").then((m) => ({ default: m.PlanMetrics })),
);
const LazyPlanDetailCard = lazy(() =>
  import("./components/PlanDetailCard").then((m) => ({
    default: m.PlanDetailCard,
  })),
);
const LazyApprovalQueue = lazy(() =>
  import("./components/ApprovalQueue").then((m) => ({
    default: m.ApprovalQueue,
  })),
);
const LazyRightPanelMoreTab = lazy(() =>
  import("./components/RightPanelMoreTab").then((m) => ({
    default: m.RightPanelMoreTab,
  })),
);

const WS_URL = getGatewayWsUrl();

const STATUS_DOT: Record<string, string> = {
  connected: "bg-emerald-500",
  connecting: "bg-amber-400 animate-pulse",
  disconnected: "bg-red-500 animate-pulse",
};

function extractPlanId(evt: BaseEvent): string | null {
  const p =
    (evt.payload?.plan_id as string | undefined) ??
    (evt.payload?.original_plan_id as string | undefined);
  if (typeof p === "string" && p.trim()) return p.trim();
  return null;
}

function sortByTimestampDesc(events: BaseEvent[]): BaseEvent[] {
  return [...events].sort((a, b) => {
    const ta = Date.parse(a.timestamp);
    const tb = Date.parse(b.timestamp);
    if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
    return tb - ta;
  });
}

async function callApprovalEndpoint(
  approvalId: string,
  action: "approve" | "reject",
) {
  await postWithoutBody(`/api/approvals/${approvalId}/${action}`);
}

export default function App() {
  const { events, pendingApprovals, status } = useWebSocket(WS_URL);
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
    setMainSection
  );

  useDashboardKeyboardShortcuts(
    setMainSectionWithHistory,
    setRightTabFromShortcut
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
      setMainSection("events");
    }
  }, [events.length]);

  const filteredEvents = sortByTimestampDesc(
    activePlanId === null
      ? visibleEvents
      : visibleEvents.filter((e) => extractPlanId(e) === activePlanId)
  );
  const latestEvent = filteredEvents[0] ?? null;

  const activePlanMode =
    activePlanId === null
      ? null
      : (() => {
          const planCreated = filteredEvents.find(
            (e) => e.event_type === "plan.created" && extractPlanId(e) === activePlanId
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

  return (
    <div className="h-dvh max-h-dvh overflow-hidden bg-black text-neutral-50 flex flex-col">
      <HeaderBar
        title="ADMADC"
        subtitle="Autonomous Deterministic Multi-Agent Dev Company"
        shortcutsHint="Atajos: Alt+1 Pipeline · Alt+2 Eventos · Alt+3–6 panel (Métricas…Más)"
        right={
          <>
            <button
              ref={panelToggleRef}
              type="button"
              className="lg:hidden shrink-0 rounded-lg border border-neutral-600 bg-neutral-900 px-2.5 py-1.5 text-[11px] font-mono text-neutral-200 hover:bg-neutral-800"
              aria-expanded={rightDrawerOpen}
              aria-controls="right-panel-drawer"
              onClick={() => setRightDrawerOpen((o) => !o)}
            >
              {rightDrawerOpen ? "Cerrar panel" : "Panel"}
            </button>
            {pendingApprovals.length > 0 && (
              <span className="bg-amber-500/20 text-amber-400 border border-amber-500/40 text-xs font-mono rounded-full px-2.5 py-0.5 animate-pulse">
                {pendingApprovals.length} approval{pendingApprovals.length !== 1 ? "s" : ""} pending
              </span>
            )}
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${STATUS_DOT[status]}`} />
              <span className="text-xs font-mono text-neutral-500">{status}</span>
            </div>
          </>
        }
      />

      <main className="relative flex-1 flex flex-col lg:grid lg:grid-cols-[1fr_minmax(280px,380px)] gap-4 p-4 min-h-0 overflow-hidden">
        {rightDrawerOpen && (
          <div
            role="presentation"
            className="lg:hidden fixed inset-0 z-40 bg-black/70"
            aria-hidden
            onClick={closeRightDrawer}
          />
        )}

        <div className="flex flex-col min-h-0 order-1 min-w-0 flex-1">
          <MainWorkspaceNav
            active={mainSection}
            onChange={setMainSectionWithHistory}
            panels={{
              pipeline: (
                <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                  <PipelineGraph latestEvent={latestEvent} />
                </div>
              ),
              events: (
                <div className="flex flex-1 min-h-0 min-w-0 flex-row gap-3">
                  <div className="flex flex-col flex-1 min-h-0 min-w-0 basis-0">
                    <div className="flex flex-wrap items-center justify-between gap-2 shrink-0 mb-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider">
                          Event Feed
                        </span>
                        <PlanFilterChips
                          planIds={knownPlanIds}
                          activePlanId={activePlanId}
                          onChange={setActivePlanIdWithHistory}
                        />
                      </div>
                      {visibleEvents.length > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            pushUrlIfChanged({ planId: null });
                            setVisibleEvents([]);
                            setActivePlanId(null);
                            setKnownPlanIds([]);
                          }}
                          className="text-[10px] font-mono text-neutral-500 hover:text-neutral-300 transition-colors"
                        >
                          clear logs
                        </button>
                      )}
                    </div>
                    <div className="flex-1 min-h-0 min-w-0 flex flex-col">
                      <EventFeed events={filteredEvents} />
                    </div>
                  </div>
                  <aside
                    className="flex flex-col shrink-0 min-h-0 w-[min(200px,36vw)] min-w-[132px] sm:w-[min(220px,34vw)] lg:w-[min(300px,32%)] border-l border-neutral-800 pl-3 overflow-y-auto"
                    aria-label="Lanzar plan"
                  >
                    <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider shrink-0 mb-2">
                      Lanzar
                    </span>
                    <div className="min-h-0 flex-1">
                      <Suspense fallback={<PanelTabFallback />}>
                        <LazyPlanForm />
                      </Suspense>
                    </div>
                  </aside>
                </div>
              ),
            }}
          />
        </div>

        <div
          id="right-panel-drawer"
          ref={rightPanelDrawerRef}
          tabIndex={-1}
          {...rightPanelAriaProps}
          className={`flex flex-col gap-3 min-h-0 order-2 lg:order-none min-w-0 flex-1 lg:flex-none lg:max-h-full overflow-hidden max-lg:fixed max-lg:top-0 max-lg:bottom-0 max-lg:right-0 max-lg:z-50 max-lg:w-[min(100vw,420px)] max-lg:max-w-full max-lg:border-l max-lg:border-neutral-800 max-lg:bg-neutral-950 max-lg:p-4 max-lg:shadow-2xl max-lg:transition-transform max-lg:duration-200 max-lg:ease-out max-lg:motion-reduce:transition-none lg:relative lg:inset-auto lg:z-auto lg:w-full lg:border-l-0 lg:bg-transparent lg:p-0 lg:shadow-none lg:translate-x-0 lg:pointer-events-auto ${
            rightDrawerOpen
              ? "max-lg:translate-x-0 max-lg:pointer-events-auto"
              : "max-lg:translate-x-full max-lg:pointer-events-none"
          }`}
        >
          <div className="flex items-center justify-between gap-2 lg:hidden shrink-0">
            <span
              id="right-drawer-title"
              className="text-[10px] font-mono uppercase tracking-wider text-neutral-500"
            >
              Herramientas
            </span>
            <button
              type="button"
              className="text-[10px] font-mono text-neutral-400 hover:text-white px-2 py-1 rounded border border-neutral-700"
              onClick={closeRightDrawer}
            >
              Cerrar
            </button>
          </div>
          <ActivePlanBar
            planId={activePlanId}
            mode={activePlanMode}
            rightTab={rightTab}
            mainSection={mainSection}
            onClear={() => setActivePlanIdWithHistory(null)}
          />
          <div className="flex-1 min-h-0 flex flex-col min-w-0 overflow-hidden">
            <RightPanelTabs
              active={rightTab}
              onChange={setRightTabFromPanel}
              panels={{
                metrics: (
                  <Suspense fallback={<PanelTabFallback />}>
                    <LazyPlanMetrics planId={activePlanId} />
                  </Suspense>
                ),
                detail: (
                  <Suspense fallback={<PanelTabFallback />}>
                    <LazyPlanDetailCard planId={activePlanId} />
                  </Suspense>
                ),
                approvals: (
                  <Suspense fallback={<PanelTabFallback />}>
                    <LazyApprovalQueue
                      approvals={pendingApprovals}
                      onApprove={(id) => callApprovalEndpoint(id, "approve")}
                      onReject={(id) => callApprovalEndpoint(id, "reject")}
                    />
                  </Suspense>
                ),
                more: (
                  <Suspense fallback={<PanelTabFallback />}>
                    <LazyRightPanelMoreTab
                      visibleEventsCount={visibleEvents.length}
                      pendingApprovalsCount={pendingApprovals.length}
                      activePlanMode={activePlanMode}
                      latestEvent={latestEvent}
                    />
                  </Suspense>
                ),
              }}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
