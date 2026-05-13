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
import { APP_BUTTON_SECONDARY, cx } from "../ui/theme";

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
    <div className="app-shell flex min-h-dvh flex-col text-neutral-50">
      <div className="app-shell-glow" aria-hidden />
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
              className={cx(APP_BUTTON_SECONDARY, "shrink-0 px-3 py-2 text-[11px]")}
              aria-expanded={rightDrawerOpen}
              aria-controls="right-panel-drawer"
              onClick={() => setRightDrawerOpen((o) => !o)}
            >
              {rightDrawerOpen
                ? t("dashboard.closeInsights")
                : t("dashboard.openInsights")}
            </button>
            {pendingApprovals.length > 0 && (
              <span className="app-badge animate-pulse border-amber-500/40 bg-amber-500/16 text-amber-300">
                {t("dashboard.pendingApprovals", {
                  count: pendingApprovals.length,
                })}
              </span>
            )}
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${STATUS_DOT[status]}`} />
              <span className="app-meta-text text-xs">
                {translateConnectionStatus(t, status)}
              </span>
            </div>
          </>
        }
      />

      <main className="relative z-10 mx-auto flex min-h-0 w-full max-w-[1680px] flex-1 flex-col gap-4 overflow-y-auto px-4 py-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)] lg:overflow-hidden 2xl:grid-cols-[minmax(560px,1.15fr)_minmax(420px,1fr)] xl:px-6">
        {rightDrawerOpen && (
          <div
            role="presentation"
            className="fixed inset-0 z-40 bg-[rgba(13,14,17,0.72)] backdrop-blur-sm"
            aria-hidden
            onClick={closeRightDrawer}
          />
        )}

        <div className="flex flex-col min-h-0 order-1 lg:order-1 min-w-0 flex-1">
          <div className="flex flex-1 min-h-0 min-w-0 flex-col gap-4 xl:gap-5">
            <div className="shrink-0 overflow-x-auto pr-1">
              <PipelineGraph latestEvent={latestEvent} />
            </div>
            <div className="app-divider mt-1 flex min-h-0 min-w-0 flex-1 border-t pt-4">
              <MainWorkspaceNav
                active={mainSection}
                onChange={setMainSectionWithHistory}
                panels={{
                  pipeline: (
                    <div className="flex flex-col flex-1 min-h-0 min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-2 shrink-0 mb-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="app-section-title text-[10px]">
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
                            className="app-button app-button-subtle"
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
          className={`fixed right-0 top-0 bottom-0 z-50 w-[min(100vw,520px)] max-w-full border-l border-[rgba(58,58,63,0.92)] bg-[linear-gradient(180deg,rgba(244,114,182,0.06),rgba(20,21,26,0.98)),rgba(13,14,17,0.96)] p-4 shadow-2xl transition-transform duration-200 ease-out motion-reduce:transition-none ${
            rightDrawerOpen
              ? "translate-x-0 pointer-events-auto"
              : "translate-x-full pointer-events-none"
          }`}
        >
          <div className="flex items-center justify-between gap-2 shrink-0 mb-3">
            <span
              id="right-drawer-title"
              className="app-section-title text-[10px]"
            >
              {t("dashboard.insights")}
            </span>
            <button
              type="button"
              className={cx(APP_BUTTON_SECONDARY, "min-h-0 px-2.5 py-1 text-[10px]")}
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
