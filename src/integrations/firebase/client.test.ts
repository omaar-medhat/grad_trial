import { describe, it, expect } from "vitest";
import { normalizeTemperatureC, normalizeTelemetry } from "./client";

describe("normalizeTemperatureC", () => {
  it("keeps plausible Celsius", () => {
    expect(normalizeTemperatureC(36.6)).toBe(36.6);
  });
  it("converts Fahrenheit to Celsius", () => {
    expect(normalizeTemperatureC(98.6)).toBe(37.0);
  });
  it("divides accidentally x10 values", () => {
    expect(normalizeTemperatureC(365)).toBe(36.5);
  });
  it("returns undefined for garbage", () => {
    expect(normalizeTemperatureC(23.57)).toBeUndefined();
    expect(normalizeTemperatureC(256)).toBeUndefined();
    expect(normalizeTemperatureC("x")).toBeUndefined();
    expect(normalizeTemperatureC(null)).toBeUndefined();
  });
});

describe("normalizeTelemetry (legacy Firebase schema)", () => {
  it("maps temperature_f and drops impossible heart_rate", () => {
    const out = normalizeTelemetry({
      heart_rate: 1.3,          // normalized garbage -> dropped
      temperature_f: 98.6,      // legacy field -> Celsius
      steps: 1200, timestamp: 1779716107821,
    });
    expect(out?.heart_rate).toBeUndefined();
    expect(out?.temperature_c).toBe(37.0);
    expect(out?.steps).toBe(1200);
  });

  it("keeps a valid canonical reading intact", () => {
    const out = normalizeTelemetry({
      heart_rate: 72, spo2: 97, temperature_c: 36.8,
      battery_level: 88, timestamp: 1,
    });
    expect(out?.heart_rate).toBe(72);
    expect(out?.spo2).toBe(97);
    expect(out?.temperature_c).toBe(36.8);
  });

  it("returns null for empty input", () => {
    expect(normalizeTelemetry(null)).toBeNull();
  });
});
