import { lazy, Suspense } from "react";
import type { DashboardProps } from "../../hooks/useDashboard";
import { PipelineGraph } from "../PipelineGraph";
import { EventFeed } from "../EventFeed";
import { ActivePlanBar } from "../ActivePlanBar";
import { HeaderBar } from "../ui/HeaderBar";
import { PlanFilterChips } from "../ui/PlanFilterChips";
import { PanelTabFallback } from "../ui/PanelTabFallback";
import { MainWorkspaceNav } from "../ui/MainWorkspaceNav";
import { RightPanelTabs } from "../ui/RightPanelTabs";
import { STATUS_DOT } from "../../lib/dashboardUtils";

const LazyPlanForm = lazy(() =>
  import("../PlanForm").then((m) => ({ default: m.PlanForm })),
);
const LazyAgentAskCard = lazy(() =>
  import("../AgentAskCard").then((m) => ({ default: m.AgentAskCard })),
);
const LazyPlanMetrics = lazy(() =>
  import("../PlanMetrics").then((m) => ({ default: m.PlanMetrics })),
);
const LazyPlanDetailCard = lazy(() =>
  import("../PlanDetailCard").then((m) => ({
    default: m.PlanDetailCard,
  })),
);
const LazyApprovalQueue = lazy(() =>
  import("../ApprovalQueue").then((m) => ({
    default: m.ApprovalQueue,
  })),
);
const LazyRightPanelMoreTab = lazy(() =>
  import("../RightPanelMoreTab").then((m) => ({
    default: m.RightPanelMoreTab,
  })),
);

export function Dashboard(props: DashboardProps) {
  const {
    status,
    pendingApprovals,
    panelToggleRef,
    rightDrawerOpen,
    setRightDrawerOpen,
    closeRightDrawer,
    rightPanelDrawerRef,
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
  } = props;

  return (
    <div className="h-dvh max-h-dvh overflow-hidden bg-black text-neutral-50 flex flex-col">
      <HeaderBar
        title="ADMADC"
        subtitle="Autonomous Deterministic Multi-Agent Dev Company"
        shortcutsHint="Atajos: Alt+1–2 vista plan · Alt+3–6 panel (Métricas…Más)"
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
                {pendingApprovals.length} approval
                {pendingApprovals.length !== 1 ? "s" : ""} pending
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
          <div className="flex flex-1 min-h-0 min-w-0 flex-row gap-3">
            <MainWorkspaceNav
              active={mainSection}
              onChange={setMainSectionWithHistory}
              panels={{
                pipeline: (
                  <div className="flex flex-col flex-1 min-h-0 min-w-0 gap-3 overflow-hidden">
                    <div className="shrink-0 overflow-x-auto pr-1">
                      <PipelineGraph latestEvent={latestEvent} />
                    </div>
                    <div className="flex flex-col flex-1 min-h-0 min-w-0 border-t border-neutral-800 pt-3">
                      <div className="flex flex-wrap items-center justify-between gap-2 shrink-0 mb-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider">
                            Registro de ejecución
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
                      <div className="flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden">
                        <EventFeed events={filteredEvents} />
                      </div>
                    </div>
                  </div>
                ),
              }}
            />
            <aside
              className="flex flex-col shrink-0 min-h-0 w-[min(200px,36vw)] min-w-[132px] sm:w-[min(220px,34vw)] lg:w-[min(300px,32%)] border-l border-neutral-800 pl-3 overflow-y-auto"
              aria-label="Lanzar plan y preguntas"
            >
              <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider shrink-0 mb-2">
                Lanzar
              </span>
              <div className="min-h-0 flex-1 flex flex-col gap-4">
                <Suspense fallback={<PanelTabFallback />}>
                  <LazyPlanForm />
                </Suspense>
                <div className="shrink-0 border-t border-neutral-800 pt-3">
                  <Suspense fallback={<PanelTabFallback />}>
                    <LazyAgentAskCard defaultPlanId={activePlanId} />
                  </Suspense>
                </div>
              </div>
            </aside>
          </div>
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
                      onApprove={onApprove}
                      onReject={onReject}
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
