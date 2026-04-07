import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("./hooks/useDashboard", () => ({
  useDashboard: () => ({
    status: "connected",
    pendingApprovals: [],
    panelToggleRef: { current: null },
    rightDrawerOpen: false,
    setRightDrawerOpen: vi.fn(),
    closeRightDrawer: vi.fn(),
    rightPanelDrawerRef: { current: null },
    isNarrowDrawer: false,
    rightPanelAriaProps: { role: "complementary", "aria-label": "tools" },
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
    onApprove: vi.fn(),
    onReject: vi.fn(),
  }),
}));

vi.mock("./components/dashboard/Dashboard", () => ({
  Dashboard: () => <h1>ADMADC</h1>,
}));

import App from "./App";

describe("App", () => {
  it("renderiza el dashboard principal", () => {
    render(<App />);
    expect(screen.getByText("ADMADC")).toBeInTheDocument();
  });
});
