import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// The live telemetry the dashboard/header is showing.
const LIVE = {
  heart_rate: 83, spo2: 97, temperature_c: 36.8, steps: 4200,
  battery_level: 91, wellness_score: 85, activity: "running",
  stress_label: "non_stress", risk_level: "high",
  source: "simulator", timestamp: 1779716107821,
};

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "demo-user-001", isDemo: true } }),
}));
vi.mock("@/hooks/useLiveTelemetry", () => ({
  useLiveTelemetry: () => ({
    data: LIVE, history: [], alerts: [],
    source: "simulator", stale: false, lastUpdate: Date.now(),
  }),
}));

import Chat from "./Chat";

describe("Chat page — single source of truth", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the exact live telemetry shown in the dashboard to /api/chat", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({
        ok: true,
        data: {
          response: "Your current heart rate is 83 bpm.",
          source: "pulseguard_ai",
          telemetry_origin: "client_live",
          telemetry_source: "simulator",
          latency_ms: 3,
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Chat />);
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "what is my heart rate right now" },
    });
    fireEvent.click(screen.getByLabelText("Send"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    // The chat must send the SAME object the dashboard is displaying.
    expect(body.telemetry).toEqual(LIVE);
    expect(body.telemetry.heart_rate).toBe(83);

    // And it surfaces where the answer's data came from.
    await waitFor(() =>
      expect(screen.getByText(/data: client_live/i)).toBeInTheDocument(),
    );
  });
});
