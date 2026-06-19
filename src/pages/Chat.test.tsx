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

describe("Chat page — medical SLM endpoint", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls /ai/medical-slm with the question + live vitals as context, and renders the answer", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({
        ok: true,
        data: {
          answer: "Rest and hydrate. See a doctor if symptoms persist.",
          model: "tinyllama-1.1b-chat-v1.0-lora-medical",
          fallback: false,
          demo_mode: false,
          latency_ms: 18000,
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Chat />);
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "what should I do for a sore throat" },
    });
    fireEvent.click(screen.getByLabelText("Send"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    // Hits the medical SLM endpoint, not /api/chat.
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/ai\/medical-slm$/);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.question).toBe("what should I do for a sore throat");
    // Live vitals shown in the dashboard are passed as context.
    expect(body.context).toContain("HR 83");
    expect(body.context).toContain("SpO2 97");

    // The generated answer is rendered, tagged with the model.
    await waitFor(() =>
      expect(
        screen.getByText(/Rest and hydrate\. See a doctor if symptoms persist\./i),
      ).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByText(/via tinyllama/i)).toBeInTheDocument(),
    );
  });
});
