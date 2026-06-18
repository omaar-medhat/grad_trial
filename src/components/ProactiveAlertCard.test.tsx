import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ProactiveAlertCard } from "./ProactiveAlertCard";
import type { LiveAlert } from "@/hooks/useLiveTelemetry";

const ALERT: LiveAlert = {
  id: "a1", type: "high_heart_rate", severity: "warning",
  title: "Elevated heart rate", message: "Heart rate is elevated (120 bpm).",
  risk_level: "high", timestamp: 1, metric: "heart_rate",
};

function wrap(alerts: LiveAlert[]) {
  return render(
    <MemoryRouter>
      <ProactiveAlertCard alerts={alerts} />
    </MemoryRouter>,
  );
}

describe("ProactiveAlertCard", () => {
  it("surfaces a proactive card for a current alert", () => {
    wrap([ALERT]);
    expect(screen.getByText(/i noticed a current alert/i)).toBeInTheDocument();
    expect(screen.getByText(/elevated heart rate/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /explain it/i })).toBeInTheDocument();
  });

  it("renders nothing when there are no actionable alerts", () => {
    const { container } = wrap([]);
    expect(container.textContent).toBe("");
  });

  it("can be dismissed", () => {
    wrap([ALERT]);
    fireEvent.click(screen.getByLabelText(/dismiss/i));
    expect(screen.queryByText(/i noticed a current alert/i)).toBeNull();
  });

  it("does not respawn for the same condition (no spam across polls)", () => {
    const { rerender } = wrap([ALERT]);
    fireEvent.click(screen.getByLabelText(/dismiss/i));
    // Next poll: same condition, new per-reading id/timestamp.
    rerender(
      <MemoryRouter>
        <ProactiveAlertCard alerts={[{ ...ALERT, id: "a2", timestamp: 2 }]} />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/i noticed a current alert/i)).toBeNull();
  });
});
