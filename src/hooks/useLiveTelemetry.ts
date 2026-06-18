/**
 * useLiveTelemetry
 * -----------------
 * Single Firebase-backed source of truth for the whole web app.
 *
 * Architecture: bracelet → Firebase Realtime DB → backend normalization layer
 * → backend APIs → THIS hook → dashboard / analytics / alerts / chat.
 *
 * The hook polls the backend's normalized endpoints ONLY:
 *   GET /api/vitals/latest    canonical current reading (+ device status)
 *   GET /api/vitals/history   normalized history (invalid BPM already nulled)
 *   GET /api/alerts           current vs historical alerts
 *
 * It does NOT read Firebase directly and NEVER generates synthetic vitals in
 * the browser. If the backend is unreachable it keeps the last known reading
 * and reports an offline/stale state — it never invents new numbers. The
 * backend decides Firebase vs. simulator via its DATA_SOURCE flag, and we
 * faithfully display whichever `source` it reports.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import type { FirebaseTelemetry } from "@/integrations/firebase/client";

export interface UserGoals {
  steps?: number;
  calories?: number;
  sleep?: number;
}

export type TelemetrySource = "firebase" | "simulator" | "offline";
export type DeviceStatus =
  | "connected" | "stale" | "disconnected" | "unknown" | "offline";

export type AlertSeverity = "watch" | "warning" | "critical";

export interface LiveAlert {
  id?: string;
  severity?: AlertSeverity;
  title?: string;
  risk_level: "warning" | "high";   // 2-level UI colour
  message: string;
  timestamp: number;
  source?: string;        // alert type (e.g. low_battery, fall, device)
  type?: string;
  metric?: string;
  scope?: "current" | "history";
  safeGuidance?: string;
  requiresMedicalAttention?: boolean;
}

export interface LiveTelemetry {
  data: FirebaseTelemetry | null;
  history: FirebaseTelemetry[];
  alerts: LiveAlert[];               // CURRENT alerts (live state)
  historicalAlerts: LiveAlert[];     // past alerts (clearly separate)
  goals: UserGoals | null;           // from /users/{uid}/goals (NOT telemetry)
  uid: string | null;                // the active Firebase user id
  source: TelemetrySource;
  isSimulated: boolean;
  simulatorEnabled: boolean;         // DATA_SOURCE allows simulator controls
  deviceStatus: DeviceStatus;
  lastSeenSeconds: number | null;
  stale: boolean;                    // device stale OR disconnected OR offline
  available: boolean;
  lastUpdate: number | null;
}

const apiBase = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
// One active uid for the whole app: the signed-in Firebase user, else a
// configured uid. When empty, the backend resolves it (FIREBASE_ACTIVE_UID or
// the first /users child with telemetry).
const envUid = (import.meta.env.VITE_FIREBASE_ACTIVE_UID || "").trim();
// Poll the live reading fast (vitals change every ~1-2s); refresh the heavier
// history a bit slower. Both are sent with no-store + a cache-buster so a
// frozen reading is never served from a browser/proxy cache.
const POLL_LATEST_MS = 1_500;
const POLL_HISTORY_MS = 4_500;

const EMPTY: LiveTelemetry = {
  data: null, history: [], alerts: [], historicalAlerts: [],
  goals: null, uid: null,
  source: "offline", isSimulated: false, simulatorEnabled: false,
  deviceStatus: "offline", lastSeenSeconds: null, stale: false,
  available: false, lastUpdate: null,
};

function sevToRisk(sev: string): "warning" | "high" {
  // watch → yellow "warning"; warning/critical/high → red "high".
  return sev === "watch" ? "warning" : "high";
}

function mapAlerts(raw: unknown, scope: "current" | "history"): LiveAlert[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((a: Record<string, unknown>) => ({
    id: a.id as string | undefined,
    severity: a.severity as AlertSeverity | undefined,
    title: a.title as string | undefined,
    risk_level: sevToRisk(String(a.severity)),
    message: String(a.message ?? ""),
    timestamp: typeof a.timestamp === "number" ? a.timestamp : Date.now(),
    source: a.type as string | undefined,
    type: a.type as string | undefined,
    metric: a.metric as string | undefined,
    scope,
    safeGuidance: a.safe_guidance as string | undefined,
    requiresMedicalAttention: a.requires_medical_attention === true,
  }));
}

interface Envelope {
  ok?: boolean;
  data?: Record<string, unknown>;
}

/** Fetch JSON with caching fully disabled (live telemetry must be fresh). */
function getFresh(path: string, uid: string): Promise<Envelope> {
  const params = `_=${Date.now()}${uid ? `&uid=${encodeURIComponent(uid)}` : ""}`;
  const sep = path.includes("?") ? "&" : "?";
  return fetch(`${apiBase}${path}${sep}${params}`, {
    cache: "no-store",
    headers: { "Cache-Control": "no-cache" },
  }).then((r) => r.json() as Promise<Envelope>);
}

export function useLiveTelemetry(): LiveTelemetry {
  const { user } = useAuth();
  // One active uid for the whole app: a REAL signed-in user reads their own
  // data; a guest/demo (or no auth) falls back to the configured uid, else the
  // backend resolves it (FIREBASE_ACTIVE_UID / first user with telemetry).
  const uid = (user && !user.isDemo ? user.id : "") || envUid;
  const [state, setState] = useState<LiveTelemetry>(EMPTY);
  const lastGood = useRef<LiveTelemetry | null>(null);
  const historyRef = useRef<FirebaseTelemetry[]>([]);
  const goalsRef = useRef<UserGoals | null>(null);

  const fetchLatest = useCallback(async () => {
    try {
      const [latestRes, alertsRes] = await Promise.all([
        getFresh("/vitals/latest", uid),
        getFresh("/alerts", uid),
      ]);

      const v = (latestRes?.data ?? {}) as Record<string, unknown>;
      const available = v.available === true && v.heart_rate != null;

      // Map the canonical contract → the display shape. The dashboard's
      // clinical risk uses the rule-engine verdict (derived_risk_level); the
      // device's own mapped label is preserved as device_risk_level.
      const data: FirebaseTelemetry | null = v.available
        ? ({
            ...(v as unknown as FirebaseTelemetry),
            risk_level: (v.derived_risk_level as string) ?? (v.risk_level as string),
            device_risk_level: v.risk_level as string,
          } as FirebaseTelemetry)
        : null;

      const source = (v.source as TelemetrySource) ??
        (alertsRes?.data?.source as TelemetrySource) ?? "firebase";
      const deviceStatus = (v.device_status as DeviceStatus) ?? "unknown";

      const next: LiveTelemetry = {
        // Always reflect what the API says now — if it reports connected,
        // we drop any previous disconnected/offline state immediately.
        data,
        history: historyRef.current,
        alerts: mapAlerts(alertsRes?.data?.current, "current"),
        historicalAlerts: mapAlerts(alertsRes?.data?.history, "history"),
        goals: goalsRef.current,
        uid: (v.uid as string) ?? (uid || null),
        source,
        isSimulated: v.is_simulated === true || source === "simulator",
        simulatorEnabled: source === "simulator" || v.is_simulated === true,
        deviceStatus,
        lastSeenSeconds:
          typeof v.last_seen_seconds === "number" ? v.last_seen_seconds : null,
        stale: deviceStatus === "stale" || deviceStatus === "disconnected",
        available: Boolean(available),
        lastUpdate: Date.now(),
      };
      lastGood.current = next;
      setState(next);
    } catch {
      // Backend unreachable — keep the LAST KNOWN reading, mark it offline,
      // and never fabricate new vitals.
      setState((prev) => {
        const base = lastGood.current ?? prev;
        return {
          ...base, history: historyRef.current,
          source: "offline", deviceStatus: "offline", stale: true,
        };
      });
    }
  }, [uid]);

  const fetchHistory = useCallback(async () => {
    try {
      const [histRes, goalsRes] = await Promise.all([
        getFresh("/vitals/history?limit=200", uid),
        getFresh("/goals", uid),
      ]);
      const readings = (histRes?.data?.readings ?? []) as FirebaseTelemetry[];
      historyRef.current = readings;
      const goals = (goalsRes?.data?.goals ?? null) as UserGoals | null;
      goalsRef.current = goals;
      setState((prev) => ({ ...prev, history: readings, goals }));
    } catch {
      /* keep last known history/goals */
    }
  }, [uid]);

  useEffect(() => {
    fetchLatest();
    fetchHistory();
    const h1 = setInterval(fetchLatest, POLL_LATEST_MS);
    const h2 = setInterval(fetchHistory, POLL_HISTORY_MS);
    return () => { clearInterval(h1); clearInterval(h2); };
  }, [fetchLatest, fetchHistory]);

  return state;
}
