/**
 * Firebase client (single source of truth for the web app).
 *
 * Used services:
 *   - Authentication          (firebase/auth)        — Email/Password
 *   - Realtime Database       (firebase/database)    — users/{uid}/...
 *
 * NOT used (and never imported):
 *   - Firestore               (firebase/firestore)
 *   - Cloud Storage           (firebase/storage)
 *
 * The Firebase web config values are PUBLIC client config — safe to inline.
 * Security is enforced by Firebase Auth + Realtime Database rules
 * (see firebase.rules.json).
 *
 * Standard RTDB paths:
 *   users/{uid}/latest_telemetry
 *   users/{uid}/history/{push_id}
 *   users/{uid}/alerts/{push_id}
 *   users/{uid}/profile
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getDatabase, type Database } from "firebase/database";
import { getAuth, type Auth } from "firebase/auth";

export interface FirebaseTelemetry {
  heart_rate: number;
  spo2: number;
  temperature_c: number;
  steps: number;
  calories: number;
  sleep_duration_sec: number;
  battery_level?: number;        // bracelet charge %, present when reported
  wellness_score?: number;       // 0–100 wellness indicator (not a diagnosis)
  activity_level?: number;       // instantaneous motion index 0–100
  activity?: string;             // resting | active | walking | running | unknown
  stress_label?: string;         // relaxed | normal | stressed | mapped device label
  stress_score?: number;         // 0–100
  source?: string;               // "firebase" | "simulator" | "real_bracelet" | …
  risk_level?: string;           // clinical risk (derived) or device-mapped label
  alert_message?: string;
  timestamp: number;
  // Blood pressure (from the bracelet, when reported).
  systolic?: number | null;
  diastolic?: number | null;
  bp_estimated?: boolean | null;
  // Fall detection.
  fall_alert?: boolean | null;
  // New user-scoped schema extras.
  uid?: string | null;
  temperature_f?: number | null;
  sleep_duration?: number | null;     // seconds (new schema)
  raw_risk?: string | number | null;
  raw_stress?: string | number | null;
  // Canonical contract extras surfaced by the Firebase-backed backend.
  available?: boolean;
  is_simulated?: boolean;
  date_time?: string | null;
  device_status?: "connected" | "stale" | "disconnected" | "unknown";
  last_seen_seconds?: number | null;
  derived_risk_level?: string | null;   // rule-engine verdict (normal/warning/high)
  device_risk_level?: string | null;    // device's own mapped risk label
  raw_risk_level?: number | string | null;
  raw_stress_label?: number | string | null;
  anomaly_status?: string | null;       // normal | flagged
  // Outputs from the trained NN models (when the backend has them loaded).
  ml_risk_label?: "normal" | "warning" | "high";
  ml_anomaly_score?: number;
}

/**
 * Coerce a raw temperature to canonical Celsius. Handles Celsius, legacy
 * Fahrenheit (`temperature_f`) and accidentally-×10 values; returns undefined
 * for anything implausible so the UI shows "—" instead of garbage.
 */
export function normalizeTemperatureC(raw: unknown): number | undefined {
  const v = Number(raw);
  if (!Number.isFinite(v)) return undefined;
  if (v >= 30 && v <= 45) return Math.round(v * 100) / 100;
  if (v >= 86 && v <= 113) return Math.round((v - 32) * (5 / 9) * 100) / 100;
  if (v >= 300 && v <= 450) {
    const c = v / 10;
    if (c >= 30 && c <= 45) return Math.round(c * 100) / 100;
  }
  return undefined;
}

/**
 * Normalize a raw Realtime-DB record into the canonical telemetry contract.
 * Firebase may hold a legacy/partial schema (e.g. `temperature_f`, no spo2),
 * so we map names, convert units, and drop physiologically-impossible values
 * (heart_rate, spo2) to `undefined` rather than trusting them blindly.
 */
export function normalizeTelemetry(
  raw: Record<string, unknown> | null | undefined,
): FirebaseTelemetry | null {
  if (!raw || typeof raw !== "object") return null;
  const num = (x: unknown, lo: number, hi: number): number | undefined => {
    const v = Number(x);
    return Number.isFinite(v) && v >= lo && v <= hi ? v : undefined;
  };
  return {
    ...(raw as object),
    heart_rate: num(raw.heart_rate, 20, 250) as number,
    spo2: num(raw.spo2, 50, 100) as number,
    temperature_c: normalizeTemperatureC(
      raw.temperature_c ?? (raw as Record<string, unknown>).temperature_f,
    ) as number,
  } as FirebaseTelemetry;
}

let _app: FirebaseApp | null = null;
let _db: Database | null = null;
let _auth: Auth | null = null;
let _initAttempted = false;

function readConfig() {
  const cfg = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    databaseURL: import.meta.env.VITE_FIREBASE_DATABASE_URL,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    // storageBucket is part of the Firebase web config but Cloud Storage is
    // NOT used in this project. Including it is safe; we never call getStorage.
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID,
    measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
  };
  // Required minimum to talk to Realtime Database + Auth.
  if (!cfg.apiKey || !cfg.databaseURL || !cfg.projectId || !cfg.authDomain) return null;
  return cfg;
}

function initFirebase() {
  if (_initAttempted) return;
  _initAttempted = true;
  const cfg = readConfig();
  if (!cfg) {
    console.info("[firebase] env vars missing — running in demo/local mode");
    return;
  }
  try {
    _app = getApps().length ? getApps()[0]! : initializeApp(cfg);
    _db = getDatabase(_app);
    _auth = getAuth(_app);
  } catch (e) {
    console.warn("[firebase] init failed:", e);
  }
}

export function getFirebaseDb(): Database | null {
  initFirebase();
  return _db;
}

export function getFirebaseAuth(): Auth | null {
  initFirebase();
  return _auth;
}

export function isFirebaseEnabled(): boolean {
  initFirebase();
  return _db !== null && _auth !== null;
}

/** Path helpers — keep all "magic strings" here. */
export const fbPath = {
  latest: (uid: string) => `users/${uid}/latest_telemetry`,
  history: (uid: string) => `users/${uid}/history`,
  alerts: (uid: string) => `users/${uid}/alerts`,
  profile: (uid: string) => `users/${uid}/profile`,
};
