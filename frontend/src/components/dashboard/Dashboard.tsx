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
import { LanguageSwitcher } from "../ui/LanguageSwitcher";
import { useTranslation } from "react-i18next";
import { translateConnectionStatus } from "../../i18n/formatters";

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
  const { t } = useTranslation();
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
    <div className="min-h-dvh bg-black text-neutral-50 flex flex-col">
      <HeaderBar
        title="ADMADC"
        subtitle={t("dashboard.subtitle")}
        shortcutsHint={t("dashboard.shortcutsHint")}
        right={
          <>
            <LanguageSwitcher />
            <button
              ref={panelToggleRef}
              type="button"
              className="shrink-0 rounded-lg border border-neutral-600 bg-neutral-900 px-2.5 py-1.5 text-[11px] font-mono text-neutral-200 hover:bg-neutral-800"
              aria-expanded={rightDrawerOpen}
              aria-controls="right-panel-drawer"
              onClick={() => setRightDrawerOpen((o) => !o)}
            >
              {rightDrawerOpen
                ? t("dashboard.closeInsights")
                : t("dashboard.openInsights")}
            </button>
            {pendingApprovals.length > 0 && (
              <span className="bg-amber-500/20 text-amber-400 border border-amber-500/40 text-xs font-mono rounded-full px-2.5 py-0.5 animate-pulse">
                {t("dashboard.pendingApprovals", {
                  count: pendingApprovals.length,
                })}
              </span>
            )}
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${STATUS_DOT[status]}`} />
              <span className="text-xs font-mono text-neutral-500">
                {translateConnectionStatus(t, status)}
              </span>
            </div>
          </>
        }
      />

      <main className="relative flex-1 flex flex-col lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)] 2xl:grid-cols-[minmax(560px,1.15fr)_minmax(420px,1fr)] gap-4 px-4 py-4 xl:px-6 min-h-0 overflow-y-auto lg:overflow-hidden">
        {rightDrawerOpen && (
          <div
            role="presentation"
            className="fixed inset-0 z-40 bg-black/65"
            aria-hidden
            onClick={closeRightDrawer}
          />
        )}

        <div className="flex flex-col min-h-0 order-1 lg:order-1 min-w-0 flex-1">
          <div className="flex flex-1 min-h-0 min-w-0 flex-col gap-4 xl:gap-5">
            <div className="shrink-0 overflow-x-auto pr-1">
              <PipelineGraph latestEvent={latestEvent} />
            </div>
            <div className="flex flex-1 min-h-0 min-w-0 mt-1 border-t border-neutral-800 pt-4">
              <MainWorkspaceNav
                active={mainSection}
                onChange={setMainSectionWithHistory}
                panels={{
                  pipeline: (
                    <div className="flex flex-col flex-1 min-h-0 min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-2 shrink-0 mb-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider">
                            {t("dashboard.executionLog")}
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
                            {t("dashboard.clearLogs")}
                          </button>
                        )}
                      </div>
                      <div className="flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden">
                        <EventFeed events={filteredEvents} />
                      </div>
                    </div>
                  ),
                }}
              />
            </div>
          </div>
        </div>

        <aside className="flex flex-col gap-3 min-h-0 order-2 lg:order-2 min-w-0 flex-1 lg:flex-none lg:max-h-full overflow-hidden">
          <div className="flex-1 min-h-0 flex flex-col min-w-0 overflow-y-auto">
            <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider shrink-0 mb-2">
              {t("dashboard.launch")}
            </span>
            <div className="min-h-0 flex-1 flex flex-col gap-4 pr-1">
              <Suspense fallback={<PanelTabFallback />}>
                <LazyPlanForm />
              </Suspense>
              <div className="shrink-0 border-t border-neutral-800 pt-3">
                <Suspense fallback={<PanelTabFallback />}>
                  <LazyAgentAskCard defaultPlanId={activePlanId} />
                </Suspense>
              </div>
            </div>
          </div>
        </aside>

        <aside
          id="right-panel-drawer"
          ref={rightPanelDrawerRef}
          tabIndex={-1}
          {...rightPanelAriaProps}
          className={`fixed top-0 right-0 bottom-0 z-50 w-[min(100vw,520px)] max-w-full border-l border-neutral-800 bg-neutral-950 p-4 shadow-2xl transition-transform duration-200 ease-out motion-reduce:transition-none ${
            rightDrawerOpen
              ? "translate-x-0 pointer-events-auto"
              : "translate-x-full pointer-events-none"
          }`}
        >
          <div className="flex items-center justify-between gap-2 shrink-0 mb-3">
            <span
              id="right-drawer-title"
              className="text-[10px] font-mono uppercase tracking-wider text-neutral-500"
            >
              {t("dashboard.insights")}
            </span>
            <button
              type="button"
              className="text-[10px] font-mono text-neutral-400 hover:text-white px-2 py-1 rounded border border-neutral-700"
              onClick={closeRightDrawer}
            >
              {t("dashboard.close")}
            </button>
          </div>
          <div className="flex flex-col min-h-0 h-[calc(100dvh-3.75rem)]">
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
        </aside>
      </main>
    </div>
  );
}
