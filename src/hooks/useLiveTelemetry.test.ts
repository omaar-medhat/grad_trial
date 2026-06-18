import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

// Active user comes from auth → the hook must scope all calls to this uid.
vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "u123", email: "a@b.com", isDemo: false } }),
}));

import { useLiveTelemetry } from "./useLiveTelemetry";

const CONNECTED = {
  available: true, heart_rate: 72, spo2: 98, temperature_c: 37.0, steps: 12,
  calories: 0.48, sleep_duration_sec: 28, battery_level: 82, systolic: 120,
  diastolic: 80, fall_alert: false, source: "firebase", is_simulated: false,
  device_status: "connected", last_seen_seconds: 2, risk_level: "moderate",
  derived_risk_level: "normal", timestamp: 123,
};

function fetchReturning(latest: Record<string, unknown>) {
  return vi.fn((url: string) => {
    if (url.includes("/vitals/latest"))
      return Promise.resolve({ json: async () => ({ ok: true, data: latest }) });
    if (url.includes("/vitals/history"))
      return Promise.resolve({ json: async () => ({ ok: true, data: {
        source: "firebase", count: 2,
        readings: [{ heart_rate: 70, timestamp: 1 }, { heart_rate: 75, timestamp: 2 }],
      } }) });
    if (url.includes("/goals"))
      return Promise.resolve({ json: async () => ({ ok: true, data: {
        uid: "u123", goals: { steps: 12000, calories: 600, sleep: 7 },
      } }) });
    if (url.includes("/alerts"))
      return Promise.resolve({ json: async () => ({ ok: true, data: {
        source: "firebase",
        current: [{ type: "fall", severity: "high", message: "Fall detected", timestamp: 1 }],
        history: [{ type: "fever", severity: "warning", message: "fever earlier", timestamp: 1 }],
      } }) });
    return Promise.resolve({ json: async () => ({}) });
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("useLiveTelemetry — Firebase-backed", () => {
  it("maps the contract, labels firebase, and sends no-store fetches", async () => {
    const fetchMock = fetchReturning(CONNECTED);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useLiveTelemetry());
    await waitFor(() => expect(result.current.data).not.toBeNull());
    await waitFor(() => expect(result.current.history).toHaveLength(2));

    expect(result.current.source).toBe("firebase");
    expect(result.current.isSimulated).toBe(false);
    expect(result.current.simulatorEnabled).toBe(false);
    expect(result.current.deviceStatus).toBe("connected");
    expect(result.current.data!.heart_rate).toBe(72);
    expect(result.current.data!.risk_level).toBe("normal");      // derived
    expect(result.current.data!.device_risk_level).toBe("moderate");
    expect(result.current.alerts[0].risk_level).toBe("high");
    expect(result.current.historicalAlerts).toHaveLength(1);
    expect(result.current.stale).toBe(false);

    // Every request must be cache-busted + no-store.
    const url = fetchMock.mock.calls[0][0] as string;
    const opts = fetchMock.mock.calls[0][1] as RequestInit;
    expect(url).toMatch(/_=\d+/);
    expect(opts.cache).toBe("no-store");
  });

  it("flips from disconnected to connected when the API says so", async () => {
    const fetchMock = fetchReturning({ ...CONNECTED, device_status: "disconnected" });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useLiveTelemetry());
    await waitFor(() => expect(result.current.deviceStatus).toBe("disconnected"));

    // Sensor comes back: API now reports connected → state must update.
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/vitals/latest"))
        return Promise.resolve({ json: async () => ({ ok: true, data: CONNECTED }) });
      return Promise.resolve({ json: async () => ({ ok: true, data: { current: [], history: [] } }) });
    });
    await waitFor(() => expect(result.current.deviceStatus).toBe("connected"), { timeout: 4000 });
    expect(result.current.stale).toBe(false);
  });

  it("keeps the last known reading and marks offline when the backend fails", async () => {
    const fetchMock = fetchReturning(CONNECTED);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useLiveTelemetry());
    await waitFor(() => expect(result.current.data).not.toBeNull());

    fetchMock.mockImplementation(() => Promise.reject(new Error("down")));
    await waitFor(() => expect(result.current.source).toBe("offline"), { timeout: 5000 });
    expect(result.current.data!.heart_rate).toBe(72); // last known retained
    expect(result.current.stale).toBe(true);
  });

  it("scopes all calls to the active uid and exposes goals", async () => {
    const fetchMock = fetchReturning(CONNECTED);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useLiveTelemetry());
    await waitFor(() => expect(result.current.goals).not.toBeNull());

    // Every request carries the active uid.
    const urls = fetchMock.mock.calls.map((c) => c[0] as string);
    expect(urls.every((u) => u.includes("uid=u123"))).toBe(true);
    expect(result.current.goals!.steps).toBe(12000);
  });

  it("enables simulator controls only when the source is simulator", async () => {
    vi.stubGlobal("fetch", fetchReturning({
      ...CONNECTED, source: "simulator", is_simulated: true,
    }));
    const { result } = renderHook(() => useLiveTelemetry());
    await waitFor(() => expect(result.current.simulatorEnabled).toBe(true));
    expect(result.current.source).toBe("simulator");
  });
});
