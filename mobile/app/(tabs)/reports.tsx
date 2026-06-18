import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/hooks/useAuth";
import { api, type DailyReport } from "@/lib/api";
import { colors } from "@/config";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

export default function Reports() {
  const { user } = useAuth();
  const uid = user?.id ?? "";
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!uid) return;
    setLoading(true);
    setError(false);
    const res = await api.getDailyReport(uid);
    setLoading(false);
    if (res.ok) setReport(res.data);
    else setError(true);
  }, [uid]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const bp = report?.blood_pressure as
    | { systolic?: { avg: number }; diastolic?: { avg: number } }
    | null
    | undefined;

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ padding: 16 }}>
      <Text style={styles.title}>Daily report</Text>
      <Text style={styles.subtitle}>Summary of today's live Firebase readings</Text>

      <Pressable style={styles.btn} onPress={load} disabled={loading}>
        {loading ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="refresh" size={16} color="#fff" />}
        <Text style={styles.btnText}>Refresh</Text>
      </Pressable>

      {error ? (
        <View style={styles.empty}>
          <Ionicons name="cloud-offline-outline" size={28} color={colors.textMuted} />
          <Text style={styles.emptyText}>Couldn't reach the backend for the report.</Text>
        </View>
      ) : !report ? (
        <View style={styles.empty}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : report.available === false ? (
        <View style={styles.empty}>
          <Ionicons name="document-text-outline" size={28} color={colors.textMuted} />
          <Text style={styles.emptyText}>{report.summary}</Text>
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.cardPeriod}>Daily summary · {report.count} readings · {report.source}</Text>
          <View style={styles.grid}>
            {report.heart_rate && <Stat label="Avg HR" value={`${report.heart_rate.avg} bpm`} />}
            {report.heart_rate && <Stat label="HR range" value={`${report.heart_rate.min}–${report.heart_rate.max}`} />}
            {report.spo2 && <Stat label="Avg SpO₂" value={`${report.spo2.avg}%`} />}
            {report.temperature_c && <Stat label="Avg Temp" value={`${report.temperature_c.avg}°C`} />}
            {bp?.systolic && bp?.diastolic && <Stat label="Avg BP" value={`${bp.systolic.avg}/${bp.diastolic.avg}`} />}
            {typeof report.steps_total === "number" && <Stat label="Steps" value={`${report.steps_total}`} />}
            {typeof report.sleep_hours === "number" && <Stat label="Sleep" value={`${report.sleep_hours} h`} />}
            {report.battery && <Stat label="Battery" value={`${report.battery.min}–${report.battery.max}%`} />}
          </View>
          {typeof report.fall_events === "number" && report.fall_events > 0 ? (
            <View style={styles.alertTag}>
              <Ionicons name="warning" size={14} color={colors.danger} />
              <Text style={styles.alertTagText}>{report.fall_events} fall event(s)</Text>
            </View>
          ) : null}
          <Text style={styles.summary}>{report.summary}</Text>
          {report.disclaimer ? <Text style={styles.disclaimer}>{report.disclaimer}</Text> : null}
        </View>
      )}

      <Text style={styles.disclaimer}>⚠️ Wellness summaries only — not a medical diagnosis.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  title: { fontSize: 22, fontWeight: "700", color: colors.text },
  subtitle: { color: colors.textMuted, marginTop: 2, marginBottom: 14 },
  btn: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingVertical: 11, borderRadius: 10, marginBottom: 16 },
  btnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  empty: { padding: 28, alignItems: "center", gap: 8, backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border },
  emptyText: { color: colors.textMuted, textAlign: "center", fontSize: 13 },
  card: { backgroundColor: colors.card, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16 },
  cardPeriod: { fontSize: 13, fontWeight: "700", color: colors.text, textTransform: "capitalize", marginBottom: 12 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  stat: { width: "47%", backgroundColor: colors.bg, borderRadius: 10, padding: 10 },
  statLabel: { fontSize: 11, color: colors.textMuted },
  statValue: { fontSize: 18, fontWeight: "700", color: colors.text, marginTop: 2 },
  alertTag: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.dangerSoft, alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, marginTop: 12 },
  alertTagText: { color: colors.danger, fontSize: 12, fontWeight: "600" },
  summary: { color: colors.text, fontSize: 13, lineHeight: 19, marginTop: 12 },
  disclaimer: { fontSize: 11, color: colors.textMuted, textAlign: "center", marginTop: 14, marginBottom: 4 },
});
