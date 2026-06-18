import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RiskHeroCard } from "./RiskHeroCard";
import type { FirebaseTelemetry } from "@/integrations/firebase/client";

function makeTelemetry(overrides: Partial<FirebaseTelemetry> = {}): FirebaseTelemetry {
  return {
    heart_rate: 75,
    spo2: 97,
    temperature_c: 36.8,
    steps: 1200,
    calories: 45,
    sleep_duration_sec: 25200,
    risk_level: "normal",
    alert_message: "Vitals are within normal range.",
    timestamp: Date.now(),
    ...overrides,
  } as FirebaseTelemetry;
}

describe("RiskHeroCard", () => {
  it("defaults to the 'All Good' state when no telemetry is provided", () => {
    render(<RiskHeroCard telemetry={null} />);
    expect(screen.getByText(/all good/i)).toBeInTheDocument();
    expect(screen.getByText(/healthy/i)).toBeInTheDocument();
  });

  it("renders the warning headline when risk_level is warning", () => {
    render(<RiskHeroCard telemetry={makeTelemetry({ risk_level: "warning" })} />);
    expect(screen.getByText(/watch/i)).toBeInTheDocument();
  });

  it("renders 'Needs Attention' when risk_level is high", () => {
    render(<RiskHeroCard telemetry={makeTelemetry({ risk_level: "high" })} />);
    expect(screen.getByText(/needs attention/i)).toBeInTheDocument();
  });

  it("uses the supplied alert_message instead of the default subtitle", () => {
    render(
      <RiskHeroCard
        telemetry={makeTelemetry({ risk_level: "high", alert_message: "Heart rate critically elevated." })}
      />
    );
    expect(screen.getByText(/heart rate critically elevated/i)).toBeInTheDocument();
  });

  it("exposes role=status for assistive tech", () => {
    render(<RiskHeroCard telemetry={makeTelemetry()} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
