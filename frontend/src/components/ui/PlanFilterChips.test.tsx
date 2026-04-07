import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PlanFilterChips } from "./PlanFilterChips";

describe("PlanFilterChips", () => {
  it("no renderiza nada si no hay planes", () => {
    const { container } = render(
      <PlanFilterChips planIds={[]} activePlanId={null} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("muestra planes truncados y dispara onChange", () => {
    const onChange = vi.fn();
    render(
      <PlanFilterChips
        planIds={["12345678-aaaa", "87654321-bbbb"]}
        activePlanId={null}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.click(screen.getByRole("button", { name: "12345678…" }));

    expect(onChange).toHaveBeenNthCalledWith(1, null);
    expect(onChange).toHaveBeenNthCalledWith(2, "12345678-aaaa");
  });
});

