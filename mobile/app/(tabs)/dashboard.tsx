import { useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/hooks/useAuth";
import { useLiveTelemetry, type DeviceStatus } from "@/hooks/useLiveTelemetry";
import { colors } from "@/config";

const riskPalette: Record<string, { bg: string; fg: string; label: string }> = {
  normal: { bg: colors.primarySoft, fg: colors.primary, label: "Normal" },
  low: { bg: colors.primarySoft, fg: colors.primary, label: "Low" },
  warning: { bg: colors.warningSoft, fg: colors.warning, label: "Warning" },
  moderate: { bg: colors.warningSoft, fg: colors.warning, label: "Moderate" },
  high: { bg: colors.dangerSoft, fg: colors.danger, label: "High" },
};

type IoniconName = React.ComponentProps<typeof Ionicons>["name"];

function batteryIcon(p: number): IoniconName {
  if (p <= 5) return "battery-dead";
  if (p <= 20) return "battery-half";
  return "battery-full";
}

const STATUS_UI: Record<DeviceStatus, { icon: IoniconName; fg: string; label: string }> = {
  connected: { icon: "cloud-done-outline", fg: colors.primary, label: "Firebase live" },
  stale: { icon: "cloud-offline-outline", fg: colors.warning, label: "Stale" },
  disconnected: { icon: "cloud-offline-outline", fg: colors.danger, label: "Disconnected" },
  offline: { icon: "wifi-outline", fg: colors.danger, label: "Backend offline" },
  unknown: { icon: "help-circle-outline", fg: colors.textMuted, label: "Unknown" },
};

function fmtAge(secs: number | null): string {
  if (secs == null) return "";
  if (secs < 90) return `${Math.round(secs)}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  return `${(secs / 3600).toFixed(1)}h ago`;
}

function MetricCard({ icon, label, value, unit }: { icon: IoniconName; label: string; value: string | number; unit?: string }) {
  return (
    <View style={styles.metric}>
      <Ionicons name={icon} size={18} color={colors.primary} />
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>
        {value}{unit ? <Text style={styles.metricUnit}> {unit}</Text> : null}
      </Text>
    </View>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const uid = user?.id ?? "";
  const live = useLiveTelemetry(uid);
  const { data, deviceStatus, currentAlerts, lastSeenSeconds, loading, available } = live;
  const [refreshing, setRefreshing] = useState(false);

  const riskKey = (data?.derived_risk_level ?? data?.risk_level ?? "normal").toString().toLowerCase();
  const palette = riskPalette[riskKey] ?? riskPalette.normal;
  const status = STATUS_UI[deviceStatus] ?? STATUS_UI.unknown;
  const offline = deviceStatus === "offline";

  const topAlert = currentAlerts.find(a => a.severity === "critical")
    ?? currentAlerts.find(a => a.severity === "warning")
    ?? currentAlerts[0];

  const onRefresh = async () => { setRefreshing(true); setTimeout(() => setRefreshing(false), 600); };

  const dash = (v: unknown) => (v === null || v === undefined ? "—" : `${v}`);
  const sleepSecs = data?.sleep_duration ?? data?.sleep_duration_sec;

  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={{ padding: 16 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <Text style={styles.title}>Hello{user?.email ? `, ${user.email.split("@")[0]}` : ""}</Text>
      <Text style={styles.subtitle}>Live health overview</Text>

      <View style={[styles.sourceBadge, { borderColor: status.fg }]}>
        <Ionicons name={status.icon} size={14} color={status.fg} />
        <Text style={{ fontSize: 12, color: status.fg, fontWeight: "600" }}>{status.label}</Text>
        {lastSeenSeconds != null && deviceStatus !== "offline" ? (
          <Text style={{ fontSize: 12, color: colors.textMuted }}>· {fmtAge(lastSeenSeconds)}</Text>
        ) : null}
      </View>

      {loading && !data ? (
        <View style={styles.notice}><Text style={styles.noticeText}>Loading live data…</Text></View>
      ) : !available ? (
        <View style={styles.notice}>
          <Ionicons name="cloud-offline-outline" size={22} color={colors.textMuted} />
          <Text style={styles.noticeText}>
            {offline
              ? "Can't reach the backend. Showing the last known reading if any."
              : "No live Firebase reading available yet for this user."}
          </Text>
        </View>
      ) : null}

      {(deviceStatus === "stale" || deviceStatus === "disconnected") && data ? (
        <View style={[styles.banner, { borderColor: colors.warning, backgroundColor: colors.warningSoft }]}>
          <Ionicons name="time-outline" size={16} color={colors.warning} />
          <Text style={styles.bannerText}>
            Showing the last known reading{lastSeenSeconds != null ? ` from ${fmtAge(lastSeenSeconds)}` : ""}.
          </Text>
        </View>
      ) : null}

      {data?.fall_alert === true ? (
        <View style={[styles.banner, { borderColor: colors.danger, backgroundColor: colors.dangerSoft }]}>
          <Ionicons name="alert-circle" size={16} color={colors.danger} />
          <Text style={[styles.bannerText, { color: colors.danger }]}>Fall detected by the bracelet.</Text>
        </View>
      ) : null}

      <View style={[styles.riskCard, { backgroundColor: palette.bg, borderColor: palette.fg }]}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.riskLabel, { color: palette.fg }]}>Current status</Text>
          <Text style={[styles.riskValue, { color: palette.fg }]}>{available ? palette.label : "—"}</Text>
          <Text style={styles.riskMessage} numberOfLines={3}>
            {topAlert ? topAlert.message : available ? "Your vitals look within range." : "Waiting for a live reading…"}
          </Text>
        </View>
        {typeof data?.wellness_score === "number" ? (
          <View style={{ alignItems: "center" }}>
            <Text style={[styles.wellnessValue, { color: palette.fg }]}>{data.wellness_score}</Text>
            <Text style={styles.wellnessLabel}>Wellness</Text>
          </View>
        ) : null}
      </View>

      {(data?.risk_level || data?.stress_label) ? (
        <View style={styles.chips}>
          {data?.risk_level ? (
            <View style={styles.chip}><Ionicons name="shield-outline" size={13} color={colors.primary} /><Text style={styles.chipText}>Risk: {String(data.risk_level)}</Text></View>
          ) : null}
          {data?.stress_label ? (
            <View style={styles.chip}><Ionicons name="pulse" size={13} color={colors.primary} /><Text style={styles.chipText}>Stress: {String(data.stress_label)}</Text></View>
          ) : null}
        </View>
      ) : null}

      <View style={styles.grid}>
        <MetricCard icon="heart" label="Heart Rate" value={dash(data?.heart_rate)} unit="bpm" />
        <MetricCard icon="thermometer" label="Temperature" value={dash(data?.temperature_c)} unit="°C" />
        <MetricCard icon="water" label="SpO₂" value={dash(data?.spo2)} unit="%" />
        <MetricCard
          icon="fitness"
          label="Blood Pressure"
          value={data?.systolic != null && data?.diastolic != null ? `${data.systolic}/${data.diastolic}` : "—"}
          unit="mmHg"
        />
        <MetricCard icon="walk" label="Steps" value={data?.steps != null ? data.steps.toLocaleString() : "—"} />
        <MetricCard icon="flame" label="Calories" value={dash(data?.calories)} unit="kcal" />
        <MetricCard icon="moon" label="Sleep" value={sleepSecs != null ? (sleepSecs / 3600).toFixed(1) : "—"} unit="h" />
        {data?.battery_level != null ? (
          <MetricCard icon={batteryIcon(data.battery_level)} label="Battery" value={Math.round(data.battery_level)} unit="%" />
        ) : null}
        <MetricCard icon="footsteps-outline" label="Fall" value={data?.fall_alert === true ? "Detected" : data ? "None" : "—"} />
      </View>

      <Text style={styles.disclaimer}>
        ⚠️ PulseGuard AI provides wellness information for educational purposes only — not a substitute
        for professional medical advice, diagnosis, or treatment.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  title: { fontSize: 22, fontWeight: "700", color: colors.text },
  subtitle: { color: colors.textMuted, marginTop: 2 },
  sourceBadge: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", borderWidth: 1, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, marginTop: 12, backgroundColor: colors.card },
  notice: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 12, padding: 14, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card },
  noticeText: { color: colors.textMuted, fontSize: 13, flex: 1 },
  banner: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 12, padding: 12, borderRadius: 12, borderWidth: 1 },
  bannerText: { color: colors.text, fontSize: 13, flex: 1 },
  riskCard: { marginTop: 14, padding: 16, borderRadius: 14, borderWidth: 1, flexDirection: "row", alignItems: "center" },
  riskLabel: { fontSize: 11, textTransform: "uppercase", letterSpacing: 1, fontWeight: "600" },
  riskValue: { fontSize: 26, fontWeight: "800", marginTop: 2 },
  riskMessage: { color: colors.text, marginTop: 4, fontSize: 13 },
  wellnessValue: { fontSize: 34, fontWeight: "800", lineHeight: 36 },
  wellnessLabel: { fontSize: 10, color: colors.textMuted, textTransform: "uppercase", letterSpacing: 1, marginTop: 2 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 },
  chip: { flexDirection: "row", alignItems: "center", gap: 5, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  chipText: { fontSize: 12, color: colors.text, textTransform: "capitalize" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 14 },
  metric: { width: "47%", backgroundColor: colors.card, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, gap: 4 },
  metricLabel: { fontSize: 12, color: colors.textMuted },
  metricValue: { fontSize: 20, fontWeight: "700", color: colors.text },
  metricUnit: { fontSize: 13, color: colors.textMuted, fontWeight: "500" },
  disclaimer: { fontSize: 11, color: colors.textMuted, textAlign: "center", marginTop: 20, marginBottom: 24 },
});
