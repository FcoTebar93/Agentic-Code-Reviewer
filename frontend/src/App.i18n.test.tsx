import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "./components/ui/LanguageSwitcher";

vi.mock("./pages/LandingPage", () => ({
  LandingPage: () => {
    const { t } = useTranslation();
    return (
      <div>
        <LanguageSwitcher />
        <span>{t("landing.nav.enterSystem")}</span>
      </div>
    );
  },
}));

vi.mock("./pages/DashboardPage", () => ({
  DashboardPage: () => {
    const { t } = useTranslation();
    return <span>{t("dashboard.launch")}</span>;
  },
}));

import App from "./App";

describe("App i18n persistence", () => {
  it("mantiene el idioma al navegar entre la landing y /app", async () => {
    const landing = render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(await screen.findByText("Enter system")).toBeInTheDocument();

    landing.unmount();

    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("Launch")).toBeInTheDocument();
    expect(localStorage.getItem("admadc.ui-language")).toBe("en");
  });
});
