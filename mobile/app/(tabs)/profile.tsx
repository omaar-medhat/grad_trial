import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/hooks/useAuth";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { api, type HealthInfo, type UserGoals, type UserProfile } from "@/lib/api";
import { config, colors } from "@/config";

export default function Profile() {
  const { user, signOut, firebaseEnabled } = useAuth();
  const uid = user?.id ?? "";
  const { deviceStatus, source } = useLiveTelemetry(uid);

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [goals, setGoals] = useState<UserGoals | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!uid) { setLoading(false); return; }
    setLoading(true);
    setError(false);
    const [p, g, h] = await Promise.all([
      api.getProfile(uid),
      api.getGoals(uid),
      api.health(),
    ]);
    if (p.ok) setProfile(p.data.profile ?? null); else setError(true);
    if (g.ok) setGoals(g.data.goals ?? null);
    if (h.ok) setHealth(h.data);
    setLoading(false);
  }, [uid]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleSignOut = async () => {
    await signOut();
    router.replace("/auth");
  };

  const val = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ padding: 16, paddingBottom: 32 }}>
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Ionicons name="person" size={28} color={colors.primary} />
        </View>
        <Text style={styles.email}>{user?.email ?? "Not signed in"}</Text>
        {user?.isDemo ? (
          <Text style={styles.demoTag}>DEMO MODE</Text>
        ) : firebaseEnabled ? (
          <Text style={styles.authTag}>Firebase Auth</Text>
        ) : null}
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.primary} /></View>
      ) : (
        <>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Profile</Text>
            {error && !profile ? (
              <Text style={styles.muted}>Couldn't reach the backend for profile data.</Text>
            ) : !profile ? (
              <Text style={styles.muted}>No profile set for this user yet.</Text>
            ) : (
              <>
                <Row label="Name" value={val(profile.name)} />
                <Row label="Age" value={val(profile.age)} />
                <Row label="Gender" value={val(profile.gender)} />
                <Row label="Height (cm)" value={val(profile.height_cm)} />
                <Row label="Weight (kg)" value={val(profile.weight_kg)} />
                <Row label="Activity" value={val(profile.activity)} />
              </>
            )}
            <Text style={styles.note}>Profile is managed where the bracelet is set up. Read-only here.</Text>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Goals</Text>
            {!goals ? (
              <Text style={styles.muted}>No goals set for this user yet.</Text>
            ) : (
              <>
                <Row label="Steps" value={val(goals.steps)} />
                <Row label="Calories" value={val(goals.calories)} />
                <Row label="Sleep (h)" value={val(goals.sleep)} />
              </>
            )}
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Connection</Text>
            <Row label="Backend API" value={config.apiBaseUrl} />
            <Row label="Backend status" value={health ? health.status : (error ? "unreachable" : "—")} />
            <Row label="Firebase (backend)" value={health?.firebase_mode ?? "—"} />
            <Row label="Backend read OK" value={health ? String(health.firebase_read_ok) : "—"} />
            <Row label="Data source" value={source} />
            <Row label="Device status" value={deviceStatus} />
            <Row label="Firebase Auth (app)" value={firebaseEnabled ? "enabled" : "not configured"} />
          </View>
        </>
      )}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Safety</Text>
        <Text style={styles.body}>
          PulseGuard AI surfaces wearable readings and AI-generated insights from the backend. It does
          not diagnose or treat any condition. For medical concerns, always consult a qualified
          clinician. In an emergency, call your local emergency number.
        </Text>
      </View>

      <Pressable style={styles.signOut} onPress={handleSignOut}>
        <Ionicons name="log-out-outline" size={18} color={colors.danger} />
        <Text style={{ color: colors.danger, fontWeight: "700" }}>Sign out</Text>
      </Pressable>
    </ScrollView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={1}>{value || "—"}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  center: { padding: 30, alignItems: "center" },
  header: { alignItems: "center", marginBottom: 8 },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.primarySoft, alignItems: "center", justifyContent: "center" },
  email: { fontSize: 16, fontWeight: "700", color: colors.text, marginTop: 10 },
  demoTag: { fontSize: 10, fontWeight: "700", color: colors.warning, marginTop: 4, letterSpacing: 1 },
  authTag: { fontSize: 10, fontWeight: "700", color: colors.primary, marginTop: 4, letterSpacing: 1 },
  section: { backgroundColor: colors.card, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16, marginTop: 14 },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.text, marginBottom: 10, textTransform: "uppercase", letterSpacing: 0.5 },
  muted: { color: colors.textMuted, fontSize: 13 },
  note: { color: colors.textMuted, fontSize: 11, marginTop: 8 },
  body: { color: colors.text, fontSize: 13, lineHeight: 19 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 7, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, gap: 12 },
  rowLabel: { fontSize: 13, color: colors.textMuted },
  rowValue: { fontSize: 13, color: colors.text, fontWeight: "600", flexShrink: 1, textAlign: "right" },
  signOut: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, marginTop: 20, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.danger },
});
