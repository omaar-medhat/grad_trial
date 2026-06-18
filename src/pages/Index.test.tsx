import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const FB = {
  available: true, heart_rate: 72, spo2: 98, temperature_c: 37.0, steps: 1200,
  calories: 300, sleep_duration_sec: 25200, battery_level: 82, systolic: 120,
  diastolic: 80, fall_alert: false, risk_level: "normal",
  device_risk_level: "moderate", stress_label: "normal", source: "firebase",
  is_simulated: false, device_status: "connected", last_seen_seconds: 3,
  activity: "resting", timestamp: 1,
};

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "u", email: "a@b.com" } }),
}));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

let liveState: Record<string, unknown>;
vi.mock("@/hooks/useLiveTelemetry", () => ({
  useLiveTelemetry: () => liveState,
}));

import Index from "./Index";

function renderIndex() {
  return render(
    <MemoryRouter>
      <Index />
    </MemoryRouter>,
  );
}

describe("Dashboard — Firebase-backed single source of truth", () => {
  it("renders cards (incl. blood pressure) from the vitals contract", () => {
    liveState = {
      data: FB, history: [{ heart_rate: 72, timestamp: 1 }], alerts: [],
      historicalAlerts: [], source: "firebase", isSimulated: false,
      simulatorEnabled: false, deviceStatus: "connected", lastSeenSeconds: 3,
      stale: false, available: true, lastUpdate: Date.now(),
    };
    renderIndex();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText("120/80")).toBeInTheDocument();
    expect(screen.getByText("Firebase live")).toBeInTheDocument();  // badge
  });

  it("hides simulator controls in Firebase mode, shows them in simulator mode", () => {
    liveState = {
      data: FB, history: [], alerts: [], historicalAlerts: [],
      source: "firebase", isSimulated: false, simulatorEnabled: false,
      deviceStatus: "connected", lastSeenSeconds: 3, stale: false,
      available: true, lastUpdate: Date.now(),
    };
    const { unmount } = renderIndex();
    expect(screen.queryByRole("button", { name: /new reading/i })).toBeNull();
    expect(screen.getByText(/simulator disabled/i)).toBeInTheDocument();
    unmount();

    liveState = { ...liveState, source: "simulator", isSimulated: true, simulatorEnabled: true };
    renderIndex();
    expect(screen.getByRole("button", { name: /new reading/i })).toBeInTheDocument();
  });

  it("shows a stale banner with the last known reading (no simulator)", () => {
    liveState = {
      data: FB, history: [], alerts: [], historicalAlerts: [],
      source: "firebase", isSimulated: false, deviceStatus: "stale",
      lastSeenSeconds: 30, stale: true, available: true, lastUpdate: Date.now(),
    };
    renderIndex();
    expect(screen.getByText("Bracelet data is stale")).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/last known reading/i);
  });

  it("shows a fall banner when fall_alert is true", () => {
    liveState = {
      data: { ...FB, fall_alert: true }, history: [], alerts: [],
      historicalAlerts: [], source: "firebase", isSimulated: false,
      deviceStatus: "connected", lastSeenSeconds: 3, stale: false,
      available: true, lastUpdate: Date.now(),
    };
    renderIndex();
    expect(screen.getByText(/fall detected/i)).toBeInTheDocument();
  });
});
