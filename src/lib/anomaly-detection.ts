import { HealthTelemetry, fahrenheitToCelsius } from "./health-data";

/**
 * Anomaly Detection Module
 * 
 * Implements multiple ML-inspired anomaly detection techniques:
 * 1. Z-Score based statistical anomaly detection
 * 2. Interquartile Range (IQR) outlier detection
 * 3. Moving average deviation detector
 * 4. Multi-variate anomaly scoring (simplified Isolation Forest logic)
 */

export interface AnomalyResult {
  isAnomaly: boolean;
  score: number;       // 0-1, higher = more anomalous
  metric: string;
  method: string;
  details: string;
}

export interface AnomalyReport {
  overall: {
    isAnomaly: boolean;
    score: number;
    riskLevel: "Normal" | "Suspicious" | "Anomalous" | "Critical";
  };
  anomalies: AnomalyResult[];
  modelInfo: {
    method: string;
    windowSize: number;
    samplesAnalyzed: number;
  };
}

// ─── Statistical helpers ───────────────────────────────────────────────────

function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function stdDev(values: number[]): number {
  const m = mean(values);
  const squareDiffs = values.map(v => (v - m) ** 2);
  return Math.sqrt(squareDiffs.reduce((a, b) => a + b, 0) / values.length);
}

function percentile(sorted: number[], p: number): number {
  const idx = (p / 100) * (sorted.length - 1);
  const lower = Math.floor(idx);
  const upper = Math.ceil(idx);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (idx - lower) * (sorted[upper] - sorted[lower]);
}

// ─── Z-Score Anomaly Detection ─────────────────────────────────────────────

function zScoreDetect(value: number, history: number[], metric: string, threshold = 2.5): AnomalyResult {
  if (history.length < 5) {
    return { isAnomaly: false, score: 0, metric, method: "Z-Score", details: "Insufficient data" };
  }
  const m = mean(history);
  const sd = stdDev(history);
  if (sd === 0) return { isAnomaly: false, score: 0, metric, method: "Z-Score", details: "Zero variance" };

  const zScore = Math.abs((value - m) / sd);
  const normalizedScore = Math.min(1, zScore / 5); // normalize to 0-1

  return {
    isAnomaly: zScore > threshold,
    score: normalizedScore,
    metric,
    method: "Z-Score",
    details: `z=${zScore.toFixed(2)}, μ=${m.toFixed(1)}, σ=${sd.toFixed(1)}`,
  };
}

// ─── IQR Outlier Detection ─────────────────────────────────────────────────

function iqrDetect(value: number, history: number[], metric: string, k = 1.5): AnomalyResult {
  if (history.length < 10) {
    return { isAnomaly: false, score: 0, metric, method: "IQR", details: "Insufficient data" };
  }
  const sorted = [...history].sort((a, b) => a - b);
  const q1 = percentile(sorted, 25);
  const q3 = percentile(sorted, 75);
  const iqr = q3 - q1;
  const lowerBound = q1 - k * iqr;
  const upperBound = q3 + k * iqr;

  const isAnomaly = value < lowerBound || value > upperBound;
  const deviation = value < lowerBound
    ? (lowerBound - value) / (iqr || 1)
    : value > upperBound
      ? (value - upperBound) / (iqr || 1)
      : 0;

  return {
    isAnomaly,
    score: Math.min(1, deviation / 3),
    metric,
    method: "IQR",
    details: `bounds=[${lowerBound.toFixed(1)}, ${upperBound.toFixed(1)}], IQR=${iqr.toFixed(1)}`,
  };
}

// ─── Moving Average Deviation ──────────────────────────────────────────────

function movingAvgDetect(value: number, history: number[], metric: string, windowSize = 10, threshold = 2.0): AnomalyResult {
  if (history.length < windowSize) {
    return { isAnomaly: false, score: 0, metric, method: "Moving Avg", details: "Insufficient data" };
  }
  const window = history.slice(-windowSize);
  const movAvg = mean(window);
  const movStd = stdDev(window);
  if (movStd === 0) return { isAnomaly: false, score: 0, metric, method: "Moving Avg", details: "Zero variance" };

  const deviation = Math.abs(value - movAvg) / movStd;
  return {
    isAnomaly: deviation > threshold,
    score: Math.min(1, deviation / 4),
    metric,
    method: "Moving Avg",
    details: `MA=${movAvg.toFixed(1)}, dev=${deviation.toFixed(2)}σ`,
  };
}

// ─── Multi-variate Anomaly Score (Simplified Isolation Forest) ─────────────

function isolationScore(telemetry: HealthTelemetry, historyArr: HealthTelemetry[]): number {
  if (historyArr.length < 10) return 0;

  // Normalize each metric to 0-1 range based on observed data
  const features = [
    { current: telemetry.heartRate, history: historyArr.map(h => h.heartRate) },
    { current: telemetry.spO2, history: historyArr.map(h => h.spO2) },
    { current: fahrenheitToCelsius(telemetry.temperatureF), history: historyArr.map(h => fahrenheitToCelsius(h.temperatureF)) },
    { current: telemetry.activityIndex, history: historyArr.map(h => h.activityIndex) },
  ];

  let totalScore = 0;
  for (const f of features) {
    const m = mean(f.history);
    const sd = stdDev(f.history);
    if (sd === 0) continue;
    const z = Math.abs((f.current - m) / sd);
    totalScore += Math.min(1, z / 3);
  }

  return totalScore / features.length;
}

// ─── Main anomaly detection pipeline ───────────────────────────────────────

export function detectAnomalies(
  current: HealthTelemetry,
  history: HealthTelemetry[]
): AnomalyReport {
  const hrHistory = history.map(h => h.heartRate);
  const spo2History = history.map(h => h.spO2);
  const tempHistory = history.map(h => fahrenheitToCelsius(h.temperatureF));
  const actHistory = history.map(h => h.activityIndex);

  const currentTempC = fahrenheitToCelsius(current.temperatureF);

  const anomalies: AnomalyResult[] = [
    // Z-Score detection
    zScoreDetect(current.heartRate, hrHistory, "Heart Rate", 2.5),
    zScoreDetect(current.spO2, spo2History, "SpO₂", 2.0),
    zScoreDetect(currentTempC, tempHistory, "Temperature", 2.5),

    // IQR detection
    iqrDetect(current.heartRate, hrHistory, "Heart Rate"),
    iqrDetect(current.spO2, spo2History, "SpO₂"),

    // Moving average detection
    movingAvgDetect(current.heartRate, hrHistory, "Heart Rate"),
    movingAvgDetect(current.spO2, spo2History, "SpO₂"),
    movingAvgDetect(currentTempC, tempHistory, "Temperature"),
  ].filter(a => a.score > 0);

  // Multi-variate isolation score
  const isoScore = isolationScore(current, history);

  // Aggregate anomaly score
  const detectedAnomalies = anomalies.filter(a => a.isAnomaly);
  const maxScore = Math.max(isoScore, ...anomalies.map(a => a.score), 0);
  const avgScore = anomalies.length > 0
    ? anomalies.reduce((sum, a) => sum + a.score, 0) / anomalies.length
    : 0;
  const overallScore = Math.min(1, 0.4 * maxScore + 0.3 * avgScore + 0.3 * isoScore);

  let riskLevel: "Normal" | "Suspicious" | "Anomalous" | "Critical" = "Normal";
  if (overallScore > 0.75) riskLevel = "Critical";
  else if (overallScore > 0.5) riskLevel = "Anomalous";
  else if (overallScore > 0.25) riskLevel = "Suspicious";

  return {
    overall: {
      isAnomaly: detectedAnomalies.length > 0,
      score: Number(overallScore.toFixed(3)),
      riskLevel,
    },
    anomalies: detectedAnomalies,
    modelInfo: {
      method: "Ensemble (Z-Score + IQR + Moving Avg + Isolation Forest)",
      windowSize: history.length,
      samplesAnalyzed: history.length,
    },
  };
}
