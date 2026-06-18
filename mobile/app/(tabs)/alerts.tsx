import { ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/hooks/useAuth";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import type { AlertItem, Severity } from "@/lib/api";
import { colors } from "@/config";

const tone: Record<string, { bg: string; fg: string }> = {
  watch: { bg: colors.warningSoft, fg: colors.warning },
  warning: { bg: colors.dangerSoft, fg: colors.danger },
  critical: { bg: colors.dangerSoft, fg: colors.danger },
};

function AlertRow({ a }: { a: AlertItem }) {
  const t = tone[a.severity ?? "watch"] ?? tone.watch;
  const ts = typeof a.timestamp === "number" ? new Date(a.timestamp).toLocaleString() : null;
  return (
    <View style={[styles.alert, { backgroundColor: t.bg, borderColor: t.fg }]}>
      <Ionicons
        name={a.severity === "critical" ? "alert-circle" : "warning"}
        size={18}
        color={t.fg}
      />
      <View style={{ flex: 1 }}>
        <Text style={{ fontWeight: "700", color: colors.text }}>{a.title ?? a.message}</Text>
        <Text style={{ fontSize: 13, color: colors.text, marginTop: 2 }}>{a.message}</Text>
        {a.safe_guidance ? (
          <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 4 }}>{a.safe_guidance}</Text>
        ) : null}
        {a.emergency_guidance ? (
          <Text style={{ fontSize: 12, color: colors.danger, marginTop: 4, fontWeight: "600" }}>
            {a.emergency_guidance}
          </Text>
        ) : null}
        {ts ? <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }}>{ts}</Text> : null}
      </View>
      <Text style={[styles.tag, { color: t.fg }]}>{(a.severity ?? "watch").toUpperCase()}</Text>
    </View>
  );
}

export default function Alerts() {
  const { user } = useAuth();
  const { currentAlerts, historyAlerts, deviceStatus, loading } = useLiveTelemetry(user?.id ?? "");

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ padding: 16, paddingBottom: 32 }}>
      <Text style={styles.title}>Alerts</Text>
      <Text style={styles.subtitle}>From the backend alert engine (Firebase-backed)</Text>

      <Text style={styles.section}>Current{deviceStatus === "offline" ? " · backend offline" : ""}</Text>
      {loading && currentAlerts.length === 0 ? (
        <View style={styles.empty}><Text style={{ color: colors.textMuted }}>Loading…</Text></View>
      ) : currentAlerts.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="checkmark-circle-outline" size={32} color={colors.primary} />
          <Text style={{ color: colors.textMuted, marginTop: 8 }}>No current alerts — vitals look within range.</Text>
        </View>
      ) : (
        <View style={{ gap: 10 }}>
          {currentAlerts.map((a, i) => <AlertRow key={(a.id ?? "") + "_c_" + i} a={a} />)}
        </View>
      )}

      <Text style={styles.section}>History <Text style={{ color: colors.textMuted, fontWeight: "400" }}>(past readings, not current state)</Text></Text>
      {historyAlerts.length === 0 ? (
        <View style={styles.empty}><Text style={{ color: colors.textMuted }}>No historical alerts.</Text></View>
      ) : (
        <View style={{ gap: 8 }}>
          {historyAlerts.slice(-30).reverse().map((a, i) => (
            <View key={(a.id ?? "") + "_h_" + i} style={styles.histRow}>
              <Text style={{ color: colors.text, fontSize: 13, flex: 1 }} numberOfLines={1}>{a.title ?? a.message}</Text>
              <Text style={{ fontSize: 11, color: colors.textMuted }}>{(a.severity ?? "").toUpperCase()}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  title: { fontSize: 22, fontWeight: "700", color: colors.text },
  subtitle: { color: colors.textMuted, marginTop: 2, marginBottom: 12 },
  section: { fontSize: 13, fontWeight: "700", color: colors.text, marginTop: 18, marginBottom: 8 },
  empty: { padding: 24, alignItems: "center", backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border },
  alert: { padding: 12, borderRadius: 10, borderWidth: 1, flexDirection: "row", alignItems: "flex-start", gap: 10 },
  histRow: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.card, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 8, borderWidth: 1, borderColor: colors.border },
  tag: { fontSize: 10, fontWeight: "700" },
});
