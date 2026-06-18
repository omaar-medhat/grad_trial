import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type AlertItem,
  type Vitals,
} from "@/lib/api";

/**
 * useLiveTelemetry (mobile)
 * -------------------------
 * Single source of truth for live data: polls the BACKEND APIs (which read the
 * locked Firebase RTDB server-side). It never reads Firebase directly and never
 * fabricates readings. On backend error it keeps the last known reading and
 * marks the source "offline" — never a blank/fake state.
 */

export type Source = "firebase" | "simulator" | "offline";
export type DeviceStatus =
  | "connected" | "stale" | "disconnected" | "unknown" | "offline";

export interface LiveState {
  data: Vitals | null;
  history: Vitals[];
  currentAlerts: AlertItem[];
  historyAlerts: AlertItem[];
  source: Source;
  isSimulated: boolean;
  deviceStatus: DeviceStatus;
  lastSeenSeconds: number | null;
  stale: boolean;
  available: boolean;
  lastUpdate: number | null;
  loading: boolean;
}

const POLL_LATEST_MS = 2000;
const POLL_HISTORY_MS = 5000;

const EMPTY: LiveState = {
  data: null, history: [], currentAlerts: [], historyAlerts: [],
  source: "offline", isSimulated: false, deviceStatus: "offline",
  lastSeenSeconds: null, stale: false, available: false, lastUpdate: null,
  loading: true,
};

export function useLiveTelemetry(uid: string): LiveState {
  const [state, setState] = useState<LiveState>(EMPTY);
  const lastGood = useRef<LiveState | null>(null);
  const historyRef = useRef<Vitals[]>([]);

  const fetchLatest = useCallback(async () => {
    if (!uid) return;
    const [latestRes, alertsRes] = await Promise.all([
      api.getLatest(uid),
      api.getCurrentAlerts(uid),
    ]);

    if (!latestRes.ok) {
      // Backend unreachable — keep last known reading, mark offline.
      setState((prev) => {
        const base = lastGood.current ?? prev;
        return {
          ...base, history: historyRef.current,
          source: "offline", deviceStatus: "offline", stale: true,
          loading: false,
        };
      });
      return;
    }

    const v = latestRes.data;
    const available = v.available === true && v.heart_rate != null;
    const source = (v.source as Source) ?? "firebase";
    const deviceStatus = (v.device_status as DeviceStatus) ?? "unknown";
    const next: LiveState = {
      data: v.available ? v : null,
      history: historyRef.current,
      currentAlerts: alertsRes.ok ? alertsRes.data.current ?? [] : [],
      historyAlerts: lastGood.current?.historyAlerts ?? [],
      source,
      isSimulated: v.is_simulated === true || source === "simulator",
      deviceStatus,
      lastSeenSeconds:
        typeof v.last_seen_seconds === "number" ? v.last_seen_seconds : null,
      stale: deviceStatus === "stale" || deviceStatus === "disconnected",
      available,
      lastUpdate: Date.now(),
      loading: false,
    };
    lastGood.current = next;
    setState(next);
  }, [uid]);

  const fetchHistory = useCallback(async () => {
    if (!uid) return;
    const [histRes, alertsRes] = await Promise.all([
      api.getHistory(uid, 120),
      api.getAlerts(uid),
    ]);
    if (histRes.ok) {
      historyRef.current = histRes.data.readings ?? [];
    }
    setState((prev) => ({
      ...prev,
      history: historyRef.current,
      historyAlerts: alertsRes.ok ? alertsRes.data.history ?? [] : prev.historyAlerts,
    }));
  }, [uid]);

  useEffect(() => {
    setState((s) => ({ ...s, loading: true }));
    fetchLatest();
    fetchHistory();
    const h1 = setInterval(fetchLatest, POLL_LATEST_MS);
    const h2 = setInterval(fetchHistory, POLL_HISTORY_MS);
    return () => { clearInterval(h1); clearInterval(h2); };
  }, [fetchLatest, fetchHistory]);

  return state;
}
