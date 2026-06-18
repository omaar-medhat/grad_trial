import { useState, useEffect } from "react";
import { HealthTelemetry, UserProfile, generateTelemetry } from "@/lib/health-data";

/**
 * useHealthData
 * -------------
 * In-browser simulator used as the last-resort data source on the dashboard
 * (when neither Firebase nor the backend is reachable). Keeps a rolling
 * 120-sample history so the chart and analytics page have something to draw.
 *
 * NOTE: the technical anomaly ensemble (z-score / IQR / moving avg) used to
 * live here. It was removed for the consumer-facing UI — the production
 * surfaces now show plain-language insights derived from the rule engine.
 * The ensemble code is still available in src/lib/anomaly-detection.ts for
 * the academic write-up and for future opt-in features.
 */

const DEFAULT_PROFILE: UserProfile = {
  age: 28,
  weight: 70,
  height: 175,
  heartRateGoal: 80,
  stepsGoal: 10000,
  caloriesGoal: 2000,
  sleepGoalHours: 8,
};

export interface HealthAlert {
  id: string;
  message: string;
  severity: "warning" | "danger";
  timestamp: number;
}

export function useHealthData() {
  const [telemetry, setTelemetry] = useState<HealthTelemetry>(generateTelemetry());
  const [history, setHistory] = useState<HealthTelemetry[]>([]);
  const [profile] = useState<UserProfile>(DEFAULT_PROFILE);
  const [isConnected] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      const next = generateTelemetry();
      setTelemetry(next);
      setHistory(prev => [...prev.slice(-119), next]);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return { telemetry, history, profile, isConnected };
}
