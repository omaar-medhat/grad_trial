import { describe, it, expect } from "vitest";
import {
  classifyHeartRate,
  classifySpO2,
  classifyTemperature,
  fahrenheitToCelsius,
  secondsToTime,
  aiClassify,
  generateHistoricalDataset,
  type HealthTelemetry,
} from "./health-data";

describe("classifyHeartRate", () => {
  it("returns normal for resting adult HR", () => {
    expect(classifyHeartRate(70)).toBe("normal");
    expect(classifyHeartRate(60)).toBe("normal");
    expect(classifyHeartRate(100)).toBe("normal");
  });
  it("returns warning for borderline tachycardia", () => {
    expect(classifyHeartRate(110)).toBe("warning");
    expect(classifyHeartRate(120)).toBe("warning");
  });
  it("returns warning for borderline bradycardia (50-59)", () => {
    expect(classifyHeartRate(55)).toBe("warning");
    expect(classifyHeartRate(50)).toBe("warning");
  });
  it("returns low when HR is below 50", () => {
    expect(classifyHeartRate(45)).toBe("low");
  });
  it("returns danger when HR is above 120", () => {
    expect(classifyHeartRate(140)).toBe("danger");
  });
});

describe("classifySpO2", () => {
  it("returns normal at or above 95%", () => {
    expect(classifySpO2(98)).toBe("normal");
    expect(classifySpO2(95)).toBe("normal");
  });
  it("returns warning between 90 and 94", () => {
    expect(classifySpO2(93)).toBe("warning");
    expect(classifySpO2(90)).toBe("warning");
  });
  it("returns danger below 90", () => {
    expect(classifySpO2(85)).toBe("danger");
  });
});

describe("classifyTemperature", () => {
  it("returns normal in the 36.1-37.2 range", () => {
    expect(classifyTemperature(36.8)).toBe("normal");
    expect(classifyTemperature(37.2)).toBe("normal");
  });
  it("returns warning for low-grade fever", () => {
    expect(classifyTemperature(37.8)).toBe("warning");
  });
  it("returns low for mild hypothermia (35.0-36.0)", () => {
    expect(classifyTemperature(35.5)).toBe("low");
  });
  it("returns danger above 38.5 (high fever)", () => {
    expect(classifyTemperature(39.0)).toBe("danger");
  });
  it("returns danger below 35.0 (severe hypothermia)", () => {
    expect(classifyTemperature(34.5)).toBe("danger");
  });
});

describe("fahrenheitToCelsius", () => {
  it("converts 98.6F to 37.0C", () => {
    expect(fahrenheitToCelsius(98.6)).toBeCloseTo(37.0, 1);
  });
  it("converts 32F to 0C", () => {
    expect(fahrenheitToCelsius(32)).toBe(0);
  });
});

describe("secondsToTime", () => {
  it("splits a sleep duration into hours and minutes", () => {
    expect(secondsToTime(3600)).toEqual({ hours: 1, minutes: 0 });
    expect(secondsToTime(3660)).toEqual({ hours: 1, minutes: 1 });
    expect(secondsToTime(0)).toEqual({ hours: 0, minutes: 0 });
  });
});

describe("aiClassify", () => {
  const base: HealthTelemetry = {
    heartRate: 72,
    temperatureF: 98.2,
    steps: 1000,
    calories: 100,
    sleepSeconds: 25200,
    spO2: 97,
    activityIndex: 20,
    timestamp: 0,
  };

  it("classifies a healthy resting reading as Normal", () => {
    const r = aiClassify(base);
    expect(r.state).toBe(0);
    expect(r.label).toBe("Normal");
  });

  it("flags critical SpO2 (<90) as High-risk", () => {
    const r = aiClassify({ ...base, spO2: 85 });
    expect(r.label).toBe("High-risk");
    expect(r.patterns.some((p) => p.toLowerCase().includes("spo"))).toBe(true);
  });

  it("flags overheating (high HR + high temp)", () => {
    const r = aiClassify({ ...base, heartRate: 115, temperatureF: 102 });
    expect(r.label).toBe("High-risk");
    expect(r.patterns.some((p) => p.toLowerCase().includes("overheating"))).toBe(true);
  });

  it("flags tachycardia (HR > 120)", () => {
    const r = aiClassify({ ...base, heartRate: 125 });
    expect(r.label).not.toBe("Normal");
    expect(r.patterns.some((p) => p.toLowerCase().includes("tachycardia"))).toBe(true);
  });

  it("flags bradycardia (HR < 55) at warning level", () => {
    const r = aiClassify({ ...base, heartRate: 50 });
    expect(["Warning", "High-risk"]).toContain(r.label);
    expect(r.patterns.some((p) => p.toLowerCase().includes("bradycardia"))).toBe(true);
  });

  it("flags stress (high HR with low movement)", () => {
    const r = aiClassify({ ...base, heartRate: 108, activityIndex: 10 });
    expect(r.label).not.toBe("Normal");
    expect(r.patterns.some((p) => p.toLowerCase().includes("stress"))).toBe(true);
  });
});

describe("generateHistoricalDataset", () => {
  it("produces the requested number of records", () => {
    const records = generateHistoricalDataset(50);
    expect(records).toHaveLength(50);
  });
  it("assigns a recognized risk label and a non-empty assessment", () => {
    const records = generateHistoricalDataset(20);
    for (const r of records) {
      expect(["Low", "Medium", "High"]).toContain(r.risk);
      expect(r.assessment.length).toBeGreaterThan(0);
    }
  });
  it("produces values within physiologically plausible ranges", () => {
    const records = generateHistoricalDataset(200);
    for (const r of records) {
      expect(r.heartRate).toBeGreaterThanOrEqual(35);
      expect(r.heartRate).toBeLessThanOrEqual(180);
      expect(r.spO2).toBeGreaterThanOrEqual(70);
      expect(r.spO2).toBeLessThanOrEqual(100);
    }
  });
});
