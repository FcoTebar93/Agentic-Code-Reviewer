import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

vi.mock("./pages/LandingPage", () => ({
  LandingPage: () => <h1>Landing ADMADC</h1>,
}));

vi.mock("./pages/DashboardPage", () => ({
  DashboardPage: () => <h1>Dashboard ADMADC</h1>,
}));

import App from "./App";

describe("App", () => {
  it("renderiza la landing en la raiz", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("Landing ADMADC")).toBeInTheDocument();
  });

  it("renderiza el dashboard en /app", () => {
    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("Dashboard ADMADC")).toBeInTheDocument();
  });
});
