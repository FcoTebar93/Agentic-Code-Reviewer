import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LandingNav } from "./LandingNav";

describe("LandingNav i18n", () => {
  it("cambia la navegación y persiste el idioma seleccionado", () => {
    render(
      <MemoryRouter>
        <LandingNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Capacidades" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "EN" }));

    expect(screen.getByRole("link", { name: "Capabilities" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Enter system" })).toBeInTheDocument();
    expect(localStorage.getItem("admadc.ui-language")).toBe("en");
  });
});
