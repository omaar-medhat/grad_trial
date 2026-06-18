import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { HealthInsights } from "./HealthInsights";
import type { FirebaseTelemetry } from "@/integrations/firebase/client";

function makeTelemetry(overrides: Partial<FirebaseTelemetry> = {}): FirebaseTelemetry {
  return {
    heart_rate: 72,
    spo2: 97,
    temperature_c: 36.8,
    steps: 1000,
    calories: 100,
    sleep_duration_sec: 25200,
    risk_level: "normal",
    alert_message: "Vitals are within normal range.",
    timestamp: Date.now(),
    ...overrides,
  } as FirebaseTelemetry;
}

describe("HealthInsights", () => {
  it("renders the waiting state when there is no telemetry", () => {
    render(<HealthInsights telemetry={null} />);
    expect(screen.getByText(/waiting for the first reading/i)).toBeInTheDocument();
  });

  it("produces a healthy-range message for normal vitals", () => {
    render(<HealthInsights telemetry={makeTelemetry()} />);
    expect(screen.getByText(/heart rate is in a healthy resting range/i)).toBeInTheDocument();
    expect(screen.getByText(/blood oxygen looks healthy/i)).toBeInTheDocument();
    expect(screen.getByText(/body temperature is normal/i)).toBeInTheDocument();
  });

  it("flags critical heart rate when above 140", () => {
    render(<HealthInsights telemetry={makeTelemetry({ heart_rate: 150 })} />);
    expect(screen.getByText(/critically high/i)).toBeInTheDocument();
  });

  it("flags low blood oxygen when below 92", () => {
    render(<HealthInsights telemetry={makeTelemetry({ spo2: 88 })} />);
    expect(screen.getByText(/blood oxygen is low/i)).toBeInTheDocument();
  });

  it("flags a high fever when temperature is at or above 38.5", () => {
    render(<HealthInsights telemetry={makeTelemetry({ temperature_c: 39.0 })} />);
    expect(screen.getByText(/high fever/i)).toBeInTheDocument();
  });

  it("acknowledges step counts above the active threshold", () => {
    render(<HealthInsights telemetry={makeTelemetry({ steps: 9500 })} />);
    expect(screen.getByText(/9,500 steps today/i)).toBeInTheDocument();
  });
});
