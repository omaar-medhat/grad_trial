import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useAuth } from "@/hooks/useAuth";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { colors } from "@/config";

function badge(r?: string | null) {
  const k = (r ?? "").toString().toLowerCase();
  if (k === "high") return { color: colors.danger, backgroundColor: colors.dangerSoft };
  if (k === "warning" || k === "moderate") return { color: colors.warning, backgroundColor: colors.warningSoft };
  return { color: colors.primary, backgroundColor: colors.primarySoft };
}

export default function History() {
  const { user } = useAuth();
  const { history, deviceStatus, loading } = useLiveTelemetry(user?.id ?? "");
  const last = [...history].slice(-30).reverse();

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ padding: 16 }}>
      <Text style={styles.title}>History</Text>
      <Text style={styles.subtitle}>
        {last.length > 0 ? `Last ${last.length} Firebase readings` : "Firebase history for this user"}
      </Text>

      {loading && last.length === 0 ? (
        <View style={styles.empty}><Text style={{ color: colors.textMuted }}>Loading…</Text></View>
      ) : last.length === 0 ? (
        <View style={styles.empty}>
          <Text style={{ color: colors.textMuted, textAlign: "center" }}>
            {deviceStatus === "offline"
              ? "Can't reach the backend for history."
              : "Waiting for live Firebase history for this user."}
          </Text>
        </View>
      ) : (
        <View style={styles.list}>
          {last.map((r, i) => {
            const sleep = r.sleep_duration ?? r.sleep_duration_sec ?? 0;
            const tsLabel = typeof r.timestamp === "number" ? new Date(r.timestamp).toLocaleString() : "—";
            return (
              <View key={String(r.timestamp) + "_" + i} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTime}>{tsLabel}</Text>
                  <Text style={styles.rowMain}>
                    HR {r.heart_rate ?? "—"}bpm · SpO₂ {r.spo2 ?? "—"}% · {r.temperature_c ?? "—"}°C
                  </Text>
                  <Text style={styles.rowSub}>
                    steps {r.steps ?? "—"} · sleep {(sleep / 3600).toFixed(1)}h
                    {r.systolic != null && r.diastolic != null ? ` · BP ${r.systolic}/${r.diastolic}` : ""}
                  </Text>
                </View>
                <Text style={[styles.tag, badge(r.derived_risk_level ?? r.risk_level)]}>
                  {(r.derived_risk_level ?? r.risk_level ?? "—").toString().toUpperCase()}
                </Text>
              </View>
            );
          })}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  title: { fontSize: 22, fontWeight: "700", color: colors.text },
  subtitle: { color: colors.textMuted, marginTop: 2, marginBottom: 12 },
  empty: { padding: 24, alignItems: "center", backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border },
  list: { gap: 10 },
  row: { flexDirection: "row", alignItems: "center", backgroundColor: colors.card, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, gap: 8 },
  rowTime: { fontSize: 11, color: colors.textMuted },
  rowMain: { fontSize: 14, fontWeight: "600", color: colors.text, marginTop: 2 },
  rowSub: { fontSize: 12, color: colors.textMuted, marginTop: 1 },
  tag: { fontSize: 10, fontWeight: "700", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, overflow: "hidden" },
});
