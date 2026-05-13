import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { Dashboard } from "./Dashboard";
import type { DashboardProps } from "../../hooks/useDashboard";

function buildProps(): DashboardProps {
  return {
    status: "connected",
    pendingApprovals: [],
    panelToggleRef: createRef<HTMLButtonElement>(),
    rightDrawerOpen: false,
    setRightDrawerOpen: vi.fn(),
    closeRightDrawer: vi.fn(),
    rightPanelDrawerRef: createRef<HTMLDivElement>(),
    isNarrowDrawer: false,
    rightPanelAriaProps: {
      role: "complementary",
      "aria-label": "Plan, métricas y herramientas",
    },
    mainSection: "pipeline",
    setMainSectionWithHistory: vi.fn(),
    latestEvent: null,
    knownPlanIds: [],
    activePlanId: null,
    setActivePlanIdWithHistory: vi.fn(),
    visibleEvents: [],
    setVisibleEvents: vi.fn(),
    setKnownPlanIds: vi.fn(),
    setActivePlanId: vi.fn(),
    pushUrlIfChanged: vi.fn(),
    filteredEvents: [],
    activePlanMode: null,
    rightTab: "metrics",
    setRightTabFromPanel: vi.fn(),
    onApprove: vi.fn(async () => {}),
    onReject: vi.fn(async () => {}),
  };
}

describe("Dashboard i18n", () => {
  it("traduce el shell del dashboard al cambiar el idioma", async () => {
    render(<Dashboard {...buildProps()} />);

    expect(screen.getByRole("button", { name: "Abrir insights" })).toBeInTheDocument();
    expect(screen.getByText("Lanzar")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "EN" }));

    expect(
      await screen.findByRole("button", { name: "Open insights" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Launch")).toBeInTheDocument();
  });
});
