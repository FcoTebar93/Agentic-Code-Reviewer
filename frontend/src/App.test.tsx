import { render, screen } from "@testing-library/react";
import App from "./App";

class MockWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close() {}
}

describe("App", () => {
  beforeEach(() => {
    Object.defineProperty(window, "WebSocket", {
      writable: true,
      configurable: true,
      value: MockWebSocket,
    });
  });

  it("renderiza el dashboard principal", () => {
    render(<App />);
    expect(screen.getByText("ADMADC")).toBeInTheDocument();
  });
});
