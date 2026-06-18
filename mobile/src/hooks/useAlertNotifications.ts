/**
 * useAlertNotifications
 * ---------------------
 * Fires a **local** device notification when a new high-severity backend alert
 * arrives. It watches the same CURRENT alerts the screens render (from the
 * backend alert engine), so it never invents medical alerts itself.
 *
 * De-duplicated by alert id (stable per condition) so opening the app or
 * polling doesn't replay the same alert. Remote push (server → FCM/APNs while
 * the app is killed) is the documented upgrade path in mobile/README.md.
 */

import { useEffect, useRef } from "react";
import * as Notifications from "expo-notifications";
import type { AlertItem } from "@/lib/api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

function keyFor(a: AlertItem): string {
  return `${a.type ?? a.metric ?? "alert"}:${a.severity ?? ""}`;
}

function titleFor(a: AlertItem): string {
  if (a.type === "low_battery") return "🔋 Bracelet battery low";
  if (a.type === "fall") return "🚨 Fall detected";
  if (a.type === "device") return "📡 Bracelet connection";
  return a.severity === "critical" ? "🚨 Health alert" : "⚠️ Health alert";
}

export function useAlertNotifications(currentAlerts: AlertItem[]) {
  const notifiedRef = useRef<Set<string>>(new Set());
  const grantedRef = useRef(false);

  useEffect(() => {
    (async () => {
      const current = await Notifications.getPermissionsAsync();
      let status = current.status;
      if (status !== "granted") {
        status = (await Notifications.requestPermissionsAsync()).status;
      }
      grantedRef.current = status === "granted";
    })();
  }, []);

  useEffect(() => {
    if (!grantedRef.current) return;
    // A condition that cleared can re-notify if it recurs later.
    const activeKeys = new Set(currentAlerts.map(keyFor));
    for (const k of [...notifiedRef.current]) {
      if (!activeKeys.has(k)) notifiedRef.current.delete(k);
    }
    for (const a of currentAlerts) {
      if (a.severity !== "warning" && a.severity !== "critical") continue;
      const k = keyFor(a);
      if (notifiedRef.current.has(k)) continue;
      notifiedRef.current.add(k);
      Notifications.scheduleNotificationAsync({
        content: { title: titleFor(a), body: a.message, sound: true },
        trigger: null,
      }).catch(() => {/* notifications unavailable — ignore */});
    }
  }, [currentAlerts]);
}
