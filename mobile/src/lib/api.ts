import { config } from "@/config";

/**
 * Mobile API client — the ONLY way the app gets data.
 *
 * The app talks exclusively to the Flask backend (which reads the locked
 * Firebase RTDB via the Admin SDK). The app never reads Firebase data directly
 * and never holds Admin credentials. Every call is user-scoped by `uid`.
 *
 * Backend base URL comes from EXPO_PUBLIC_API_BASE_URL (see mobile/.env):
 *   Android emulator → http://10.0.2.2:5000
 *   iOS simulator    → http://localhost:5000
 *   Physical phone   → http://<your-LAN-IP>:5000
 */

export type ApiResponse<T> =
  | { ok: true; data: T; message?: string }
  | { ok: false; error: { code: string; message: string } };

/** Canonical telemetry contract returned by /api/vitals/latest. */
export interface Vitals {
  available: boolean;
  uid?: string | null;
  heart_rate: number | null;
  spo2: number | null;
  temperature_c: number | null;
  temperature_f?: number | null;
  steps: number | null;
  calories: number | null;
  sleep_duration?: number | null;
  sleep_duration_sec?: number | null;
  battery_level: number | null;
  systolic?: number | null;
  diastolic?: number | null;
  bp_estimated?: boolean | null;
  fall_alert?: boolean | null;
  risk_level?: string | null;
  raw_risk?: string | number | null;
  stress_label?: string | null;
  raw_stress?: string | number | null;
  activity?: string | null;
  wellness_score?: number | null;
  derived_risk_level?: string | null;
  anomaly_status?: string | null;
  source?: string;
  is_simulated?: boolean;
  timestamp?: number | string | null;
  date_time?: string | null;
  device_status?: "connected" | "stale" | "disconnected" | "unknown";
  last_seen_seconds?: number | null;
}

export type Severity = "watch" | "warning" | "critical";

export interface AlertItem {
  id?: string;
  type?: string;
  severity?: Severity;
  title?: string;
  message: string;
  metric?: string;
  value?: number | string | boolean | (number | string)[] | null;
  threshold?: number | string | (number | string)[] | null;
  is_current?: boolean;
  scope?: "current" | "history";
  source?: string;
  timestamp?: number | string | null;
  safe_guidance?: string;
  emergency_guidance?: string | null;
  requires_medical_attention?: boolean;
}

export interface AlertsResponse {
  uid?: string | null;
  source?: string;
  is_simulated?: boolean;
  device_status?: string;
  last_seen_seconds?: number | null;
  top_severity?: string;
  has_current_critical?: boolean;
  current: AlertItem[];
  history?: AlertItem[];
}

export interface VitalsHistory {
  uid?: string | null;
  source?: string;
  is_simulated?: boolean;
  count: number;
  readings: Vitals[];
}

export interface DailyReport {
  available: boolean;
  uid?: string | null;
  period?: string;
  count?: number;
  source?: string;
  heart_rate?: { avg: number; min: number; max: number } | null;
  spo2?: { avg: number; min: number; max: number } | null;
  temperature_c?: { avg: number; min: number; max: number } | null;
  steps_total?: number | null;
  calories?: number | null;
  sleep_hours?: number | null;
  battery?: { avg: number; min: number; max: number } | null;
  blood_pressure?: Record<string, unknown> | null;
  fall_events?: number;
  summary: string;
  disclaimer?: string;
  profile?: Record<string, unknown> | null;
  goals?: UserGoals | null;
}

export interface UserProfile {
  name?: string;
  age?: number;
  gender?: string;
  height_cm?: number | string;
  weight_kg?: number | string;
  activity?: string;
  [k: string]: unknown;
}

export interface UserGoals {
  steps?: number;
  calories?: number;
  sleep?: number;
}

export interface ChatReply {
  response: string;
  source?: string;
  intent?: string;
  latency_ms?: number;
  suggestions?: string[];
  telemetry_origin?: string;
  telemetry_source?: string;
}

export interface HealthInfo {
  status: string;
  version?: string;
  firebase_mode?: string;
  firebase_read_ok?: boolean | null;
  firebase_error?: string | null;
  services?: Record<string, string>;
}

function base(): string {
  return (config.apiBaseUrl || "").replace(/\/$/, "");
}

// The auth layer (useAuth) registers a getter that returns a fresh Firebase ID
// token. We attach it as `Authorization: Bearer <token>` so the backend can
// verify it and resolve the authoritative uid. No token (demo) → omitted.
let _tokenGetter: (() => Promise<string | null>) | null = null;
export function setAuthTokenGetter(fn: (() => Promise<string | null>) | null) {
  _tokenGetter = fn;
}

async function call<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 8000,
): Promise<ApiResponse<T>> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let authHeader: Record<string, string> = {};
  try {
    const token = _tokenGetter ? await _tokenGetter() : null;
    if (token) authHeader = { Authorization: `Bearer ${token}` };
  } catch {
    /* no token available — proceed unauthenticated (demo/dev) */
  }
  try {
    const res = await fetch(`${base()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        ...authHeader,
        ...(init?.headers ?? {}),
      },
      signal: ctrl.signal,
    });
    const body = (await res.json()) as ApiResponse<T>;
    return body;
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : "Network error";
    return { ok: false, error: { code: "NETWORK_ERROR", message } };
  } finally {
    clearTimeout(timer);
  }
}

const uidQ = (uid: string) => `uid=${encodeURIComponent(uid)}&_=${Date.now()}`;

export interface BootstrapResult {
  uid: string;
  created_profile: boolean;
  created_goals: boolean;
  firebase_mode?: string;
  write_backend?: string;
  write_ok?: boolean;
  profile: UserProfile;
  goals: UserGoals;
}

/** Debug helper: is an auth token currently available? (never returns the token) */
export async function hasAuthToken(): Promise<boolean> {
  try {
    const t = _tokenGetter ? await _tokenGetter() : null;
    return !!t;
  } catch {
    return false;
  }
}

/** The backend base URL the app is calling (safe to log). */
export function apiBaseUrl(): string {
  return base();
}

export const api = {
  health: () => call<HealthInfo>("/api/health"),
  // Idempotently ensure the signed-in user's /users/{uid}/profile + goals
  // exist. The backend uses the VERIFIED token uid (attached automatically).
  bootstrap: (profile?: Partial<UserProfile>) =>
    call<BootstrapResult>("/api/auth/bootstrap", {
      method: "POST",
      body: JSON.stringify(profile ?? {}),
    }),
  getLatest: (uid: string) => call<Vitals>(`/api/vitals/latest?${uidQ(uid)}`),
  getDeviceStatus: (uid: string) =>
    call<Record<string, unknown>>(`/api/device/status?${uidQ(uid)}`),
  getHistory: (uid: string, limit = 100) =>
    call<VitalsHistory>(`/api/vitals/history?${uidQ(uid)}&limit=${limit}`),
  getAlerts: (uid: string) => call<AlertsResponse>(`/api/alerts?${uidQ(uid)}`),
  getCurrentAlerts: (uid: string) =>
    call<AlertsResponse>(`/api/alerts/current?${uidQ(uid)}`),
  getDailyReport: (uid: string) =>
    call<DailyReport>(`/api/reports/daily?${uidQ(uid)}`),
  getProfile: (uid: string) =>
    call<{ uid: string; profile: UserProfile | null }>(`/api/profile?${uidQ(uid)}`),
  getGoals: (uid: string) =>
    call<{ uid: string; goals: UserGoals | null }>(`/api/goals?${uidQ(uid)}`),
  chat: (uid: string, message: string, telemetry?: Vitals | null) =>
    call<ChatReply>(
      "/api/chat",
      {
        method: "POST",
        body: JSON.stringify({
          user_id: uid,
          message,
          // Send the same live vitals the app shows so the assistant's numbers
          // match the dashboard (single source of truth).
          ...(telemetry && telemetry.available ? { telemetry } : {}),
        }),
      },
      25000,
    ),
};
