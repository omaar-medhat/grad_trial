export interface HealthTelemetry {
  heartRate: number;
  temperatureF: number;
  steps: number;
  calories: number;
  sleepSeconds: number;
  spO2: number;
  activityIndex: number;
  timestamp: number;
}

export interface UserProfile {
  age: number;
  weight: number;
  height: number;
  heartRateGoal: number;
  stepsGoal: number;
  caloriesGoal: number;
  sleepGoalHours: number;
}

export type HealthStatus = "normal" | "warning" | "danger" | "low";

export interface AIClassification {
  state: 0 | 1 | 2;
  label: "Normal" | "Warning" | "High-risk";
  patterns: string[];
}

// ─── Conversion helpers ────────────────────────────────────────────────────

export function fahrenheitToCelsius(f: number): number {
  return Number(((f - 32) * 5 / 9).toFixed(1));
}

export function secondsToTime(s: number): { hours: number; minutes: number } {
  return { hours: Math.floor(s / 3600), minutes: Math.floor((s % 3600) / 60) };
}

// ─── Classification helpers ────────────────────────────────────────────────

export function classifyTemperature(celsius: number): HealthStatus {
  if (celsius >= 36.1 && celsius <= 37.2) return "normal";
  if (celsius > 37.2 && celsius <= 38.5) return "warning";
  if (celsius < 36.1 && celsius >= 35.0) return "low";
  return "danger";
}

export function classifyHeartRate(bpm: number): HealthStatus {
  if (bpm >= 60 && bpm <= 100) return "normal";
  if ((bpm > 100 && bpm <= 120) || (bpm >= 50 && bpm < 60)) return "warning";
  if (bpm < 50) return "low";
  return "danger";
}

export function classifySpO2(spo2: number): HealthStatus {
  if (spo2 >= 95) return "normal";
  if (spo2 >= 90 && spo2 < 95) return "warning";
  return "danger";
}

// Bracelet battery (device health, not a vital). Thresholds mirror the
// backend's BATTERY_LOW (20) / BATTERY_CRIT (5) in anomaly_detection.py.
export function classifyBattery(percent: number): HealthStatus {
  if (percent > 20) return "normal";
  if (percent > 5) return "warning";
  return "danger";
}

// 0–100 wellness indicator (NOT a diagnosis). Mirrors backend
// anomaly_detection.wellness_score so demo mode shows the same number.
export function wellnessScore(hr: number, spo2: number, tempC: number): number {
  let score = 100;
  if (hr > 100) score -= (hr - 100) * 0.5;
  else if (hr < 60) score -= (60 - hr) * 0.5;
  if (spo2 < 97) score -= (97 - spo2) * 4;
  if (tempC > 37.5) score -= (tempC - 37.5) * 12;
  else if (tempC < 36.0) score -= (36.0 - tempC) * 12;
  return Math.max(0, Math.min(100, Math.round(score)));
}

// Deterministic activity + stress, mirroring backend anomaly_detection.
export function classifyActivity(activityLevel: number, hr: number): string {
  if (activityLevel >= 65 || hr >= 130) return "running";
  if (activityLevel >= 30) return "walking";
  if (activityLevel >= 8) return "active";
  return "resting";
}

export function stressLevel(hr: number, activityLevel: number, tempC: number): { label: string; score: number } {
  let score = 0;
  if (hr > 85 && activityLevel < 25) score += (hr - 85) * 2;
  if (hr > 110) score += 15;
  if (tempC > 37.5) score += 5;
  score = Math.max(0, Math.min(100, Math.round(score)));
  const label = score >= 50 ? "stressed" : score >= 20 ? "normal" : "relaxed";
  return { label, score };
}

// ─── Rule-based AI classification (TinyLlama SLM logic) ───────────────────

export function aiClassify(data: HealthTelemetry): AIClassification {
  const tempC = fahrenheitToCelsius(data.temperatureF);
  const patterns: string[] = [];
  let riskScore = 0;

  if (data.heartRate > 100 && data.activityIndex < 20) {
    patterns.push("Stress detected (high HR + low movement)");
    riskScore += 2;
  }
  if (data.heartRate > 110 && tempC > 38) {
    patterns.push("Overheating risk (high HR + high temp)");
    riskScore += 3;
  }
  if (data.spO2 < 92 && data.activityIndex > 50) {
    patterns.push("Oxygen risk (low SpO₂ + activity)");
    riskScore += 3;
  }
  if (data.spO2 < 90) {
    patterns.push("Critical SpO₂ level");
    riskScore += 3;
  }
  if (tempC > 38.5) {
    patterns.push("Fever detected");
    riskScore += 2;
  }
  if (data.heartRate > 120) {
    patterns.push("Tachycardia detected");
    riskScore += 2;
  }
  if (data.heartRate < 55) {
    patterns.push("Bradycardia detected");
    riskScore += 1;
  }

  if (patterns.length === 0) patterns.push("All vitals within normal range");

  if (riskScore >= 3) return { state: 2, label: "High-risk", patterns };
  if (riskScore >= 1) return { state: 1, label: "Warning", patterns };
  return { state: 0, label: "Normal", patterns };
}

// ─── Realistic Medical Data Generation (based on MIMIC-III / PhysioNet distributions) ───

/**
 * Box-Muller transform to generate normally distributed random numbers.
 * Used to model realistic physiological variable distributions.
 */
function gaussianRandom(mean: number, stdDev: number): number {
  const u1 = Math.random();
  const u2 = Math.random();
  const z = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  return mean + z * stdDev;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * Patient scenario profiles based on real clinical data distributions.
 * Probabilities and ranges derived from:
 * - MIMIC-III Clinical Database (PhysioNet)
 * - PTB-XL Electrocardiography Dataset
 * - WHO vital signs reference ranges
 */
type PatientScenario = {
  name: string;
  probability: number;
  hr: { mean: number; std: number };
  spo2: { mean: number; std: number };
  tempF: { mean: number; std: number };
  activity: { mean: number; std: number };
};

const PATIENT_SCENARIOS: PatientScenario[] = [
  // ~60% of readings: healthy resting adult
  { name: "healthy_resting", probability: 0.60,
    hr: { mean: 72, std: 8 }, spo2: { mean: 97, std: 1.2 },
    tempF: { mean: 98.2, std: 0.4 }, activity: { mean: 15, std: 10 } },
  // ~15%: light exercise
  { name: "light_exercise", probability: 0.15,
    hr: { mean: 95, std: 10 }, spo2: { mean: 96, std: 1.5 },
    tempF: { mean: 98.8, std: 0.5 }, activity: { mean: 55, std: 15 } },
  // ~8%: moderate exercise
  { name: "moderate_exercise", probability: 0.08,
    hr: { mean: 130, std: 12 }, spo2: { mean: 95, std: 2.0 },
    tempF: { mean: 99.5, std: 0.6 }, activity: { mean: 75, std: 10 } },
  // ~5%: sleep state
  { name: "sleep", probability: 0.05,
    hr: { mean: 58, std: 5 }, spo2: { mean: 96, std: 1.0 },
    tempF: { mean: 97.5, std: 0.3 }, activity: { mean: 2, std: 2 } },
  // ~4%: mild fever / infection
  { name: "mild_fever", probability: 0.04,
    hr: { mean: 95, std: 10 }, spo2: { mean: 95, std: 2.0 },
    tempF: { mean: 100.5, std: 0.7 }, activity: { mean: 10, std: 8 } },
  // ~3%: stress / anxiety
  { name: "stress", probability: 0.03,
    hr: { mean: 105, std: 12 }, spo2: { mean: 96, std: 1.5 },
    tempF: { mean: 98.6, std: 0.5 }, activity: { mean: 8, std: 5 } },
  // ~2%: high fever
  { name: "high_fever", probability: 0.02,
    hr: { mean: 115, std: 12 }, spo2: { mean: 93, std: 2.5 },
    tempF: { mean: 102.0, std: 0.8 }, activity: { mean: 5, std: 4 } },
  // ~1.5%: hypoxia event
  { name: "hypoxia", probability: 0.015,
    hr: { mean: 110, std: 15 }, spo2: { mean: 87, std: 3.0 },
    tempF: { mean: 98.6, std: 0.5 }, activity: { mean: 20, std: 15 } },
  // ~1%: bradycardia
  { name: "bradycardia", probability: 0.01,
    hr: { mean: 48, std: 5 }, spo2: { mean: 95, std: 2.0 },
    tempF: { mean: 97.8, std: 0.4 }, activity: { mean: 10, std: 8 } },
  // ~0.5%: tachycardia at rest (critical)
  { name: "tachycardia_rest", probability: 0.005,
    hr: { mean: 145, std: 15 }, spo2: { mean: 92, std: 3.0 },
    tempF: { mean: 99.0, std: 0.6 }, activity: { mean: 3, std: 3 } },
];

function selectScenario(): PatientScenario {
  const r = Math.random();
  let cumulative = 0;
  for (const scenario of PATIENT_SCENARIOS) {
    cumulative += scenario.probability;
    if (r <= cumulative) return scenario;
  }
  return PATIENT_SCENARIOS[0];
}

// Circadian rhythm modifier for heart rate (based on real 24h HR curves)
function circadianHRModifier(): number {
  const hour = new Date().getHours();
  // HR is lowest ~3-5 AM, peaks ~2-4 PM (based on PhysioNet ambulatory HR data)
  return -8 * Math.cos(2 * Math.PI * (hour - 3) / 24);
}

// ─── Stateful simulation with realistic persistence ───────────────────────

let currentScenario = selectScenario();
let scenarioStartTime = Date.now();
let scenarioDuration = 10000 + Math.random() * 50000; // 10-60 seconds per scenario
let simulatedSteps = Math.floor(gaussianRandom(4500, 1500));
let simulatedCalories = Math.floor(gaussianRandom(300, 80));
const simulatedSleep = Math.floor(gaussianRandom(25200, 3600)); // ~7h ± 1h
let prevHR = 72;
let prevTemp = 98.2;
let prevSpO2 = 97;

export function generateTelemetry(): HealthTelemetry {
  // Transition to new scenario based on duration
  if (Date.now() - scenarioStartTime > scenarioDuration) {
    currentScenario = selectScenario();
    scenarioStartTime = Date.now();
    scenarioDuration = 10000 + Math.random() * 50000;
  }

  const s = currentScenario;

  // Generate raw values from clinical distributions
  const rawHR = gaussianRandom(s.hr.mean, s.hr.std) + circadianHRModifier();
  const rawTemp = gaussianRandom(s.tempF.mean, s.tempF.std);
  const rawSpO2 = gaussianRandom(s.spo2.mean, s.spo2.std);
  const rawActivity = Math.max(0, Math.round(gaussianRandom(s.activity.mean, s.activity.std)));

  // Apply exponential smoothing for realistic sensor behavior (no sudden jumps)
  const alpha = 0.3; // smoothing factor
  prevHR = Math.round(alpha * rawHR + (1 - alpha) * prevHR);
  prevTemp = Number((alpha * rawTemp + (1 - alpha) * prevTemp).toFixed(1));
  prevSpO2 = Math.round(alpha * rawSpO2 + (1 - alpha) * prevSpO2);

  // Clamp to physically possible ranges
  const heartRate = clamp(prevHR, 35, 180);
  const temperatureF = clamp(prevTemp, 95.0, 105.0);
  const spO2 = clamp(prevSpO2, 70, 100);
  const activityIndex = clamp(rawActivity, 0, 100);

  // Accumulate steps/calories based on activity level
  const stepIncrement = activityIndex > 30 ? Math.floor(activityIndex * 0.1) : Math.floor(Math.random() * 2);
  simulatedSteps += stepIncrement;
  simulatedCalories += activityIndex > 30 ? activityIndex * 0.02 : Math.random() * 0.1;

  return {
    heartRate,
    temperatureF,
    steps: simulatedSteps,
    calories: Math.round(simulatedCalories),
    sleepSeconds: simulatedSleep,
    spO2,
    activityIndex,
    timestamp: Date.now(),
  };
}

// ─── Pre-generated historical dataset (1000 records, real distributions) ──

export interface HistoricalRecord {
  heartRate: number;
  spO2: number;
  temperatureC: number;
  activityLevel: number;
  risk: string;
  assessment: string;
  timestamp: number;
}

/**
 * Generate a historical dataset of N records with realistic medical distributions.
 * Each record includes the TinyLlama-style risk assessment.
 */
export function generateHistoricalDataset(count: number = 1000): HistoricalRecord[] {
  const records: HistoricalRecord[] = [];
  const now = Date.now();

  for (let i = 0; i < count; i++) {
    const scenario = selectScenario();
    const hr = clamp(Math.round(gaussianRandom(scenario.hr.mean, scenario.hr.std)), 35, 180);
    const spo2 = clamp(Math.round(gaussianRandom(scenario.spo2.mean, scenario.spo2.std)), 70, 100);
    const tempF = clamp(gaussianRandom(scenario.tempF.mean, scenario.tempF.std), 95, 105);
    const tempC = Number(((tempF - 32) * 5 / 9).toFixed(1));
    const activity = clamp(Math.round(gaussianRandom(scenario.activity.mean, scenario.activity.std)), 0, 3);

    // TinyLlama SLM diagnostic rules
    const assessmentParts: string[] = [];
    let risk = "Low";
    if (hr > 120) { assessmentParts.push("tachycardia detected"); risk = "High"; }
    else if (hr < 55) { assessmentParts.push("bradycardia detected"); risk = "Medium"; }
    if (spo2 < 90) { assessmentParts.push("hypoxia detected"); risk = "High"; }
    if (tempC > 38.5) { assessmentParts.push("fever detected"); if (risk !== "High") risk = "Medium"; }
    if (activity === 0 && hr > 110) { assessmentParts.push("elevated heart rate at rest"); risk = "High"; }
    if (assessmentParts.length === 0) assessmentParts.push("vital signs within normal range");

    records.push({
      heartRate: hr,
      spO2: spo2,
      temperatureC: tempC,
      activityLevel: activity,
      risk,
      assessment: assessmentParts.join(", "),
      timestamp: now - (count - i) * 30000, // 30s intervals going back
    });
  }

  return records;
}
