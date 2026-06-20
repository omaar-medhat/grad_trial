import { useEffect, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { router } from "expo-router";
import { useAuth } from "@/hooks/useAuth";
import { api, type ProfileInput } from "@/lib/api";
import { colors } from "@/config";

const GENDERS = ["male", "female", "other"] as const;
const ACTIVITIES = [
  "sedentary", "light", "moderate", "active", "very_active",
] as const;

/**
 * Onboarding / profile setup. Shown ONLY when the backend reports
 * needs_onboarding=true. It loads any existing values, lets the user fill the
 * required fields once, and saves via the backend (PUT /api/profile/me).
 *
 * It never writes Firebase directly. If the profile is already complete it
 * redirects straight to the dashboard (prevents a route loop).
 */
export default function Onboarding() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<string>("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [activity, setActivity] = useState<string>("");
  const [bloodType, setBloodType] = useState("");
  const [emergency, setEmergency] = useState("");

  // Prefill from the backend; if already complete, skip straight to dashboard.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const me = await api.me();
      if (cancelled) return;
      if (me.ok) {
        if (!me.data.needs_onboarding) {
          router.replace("/(tabs)/dashboard");
          return;
        }
        const p = me.data.profile ?? {};
        setName(typeof p.name === "string" ? p.name : "");
        setAge(p.age != null ? String(p.age) : "");
        setGender(typeof p.gender === "string" ? p.gender : "");
        setHeightCm(p.height_cm != null ? String(p.height_cm) : "");
        setWeightKg(p.weight_kg != null ? String(p.weight_kg) : "");
        setActivity(typeof p.activity === "string" ? p.activity : "");
        setBloodType(typeof p.blood_type === "string" ? p.blood_type : "");
        setEmergency(
          typeof p.emergency_contact === "string" ? p.emergency_contact : "",
        );
      }
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const submit = async () => {
    setError(null);
    if (!name.trim()) return setError("Please enter your name.");
    if (!age.trim() || Number.isNaN(Number(age))) return setError("Enter a valid age.");
    if (!gender) return setError("Please select your gender.");
    if (!heightCm.trim() || Number.isNaN(Number(heightCm))) return setError("Enter a valid height (cm).");
    if (!weightKg.trim() || Number.isNaN(Number(weightKg))) return setError("Enter a valid weight (kg).");
    if (!activity) return setError("Please select your activity level.");

    const payload: ProfileInput = {
      name: name.trim(),
      age: Number(age),
      gender,
      height_cm: Number(heightCm),
      weight_kg: Number(weightKg),
      activity,
      blood_type: bloodType.trim(),
      emergency_contact: emergency.trim(),
    };

    setSubmitting(true);
    const res = await api.updateProfile(payload);
    setSubmitting(false);

    if (!res.ok) {
      setError(res.error.message || "Could not save your profile. Try again.");
      return;
    }
    if (res.data.needs_onboarding) {
      setError("Some required fields are still missing: " +
        res.data.missing_fields.join(", "));
      return;
    }
    router.replace("/(tabs)/dashboard");
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.root}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Complete your profile</Text>
        <Text style={styles.subtitle}>
          We use this once to personalise your health insights. You won't be
          asked again after this.
        </Text>

        <Text style={styles.label}>Full name *</Text>
        <TextInput style={styles.input} value={name} onChangeText={setName}
          placeholder="e.g. Sara Ahmed" placeholderTextColor={colors.textMuted} />

        <Text style={styles.label}>Age *</Text>
        <TextInput style={styles.input} value={age} onChangeText={setAge}
          keyboardType="number-pad" placeholder="e.g. 22" placeholderTextColor={colors.textMuted} />

        <Text style={styles.label}>Gender *</Text>
        <View style={styles.chips}>
          {GENDERS.map(g => (
            <Pressable key={g} onPress={() => setGender(g)}
              style={[styles.chip, gender === g && styles.chipOn]}>
              <Text style={[styles.chipText, gender === g && styles.chipTextOn]}>{g}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Height (cm) *</Text>
        <TextInput style={styles.input} value={heightCm} onChangeText={setHeightCm}
          keyboardType="decimal-pad" placeholder="e.g. 175" placeholderTextColor={colors.textMuted} />

        <Text style={styles.label}>Weight (kg) *</Text>
        <TextInput style={styles.input} value={weightKg} onChangeText={setWeightKg}
          keyboardType="decimal-pad" placeholder="e.g. 72" placeholderTextColor={colors.textMuted} />

        <Text style={styles.label}>Activity level *</Text>
        <View style={styles.chips}>
          {ACTIVITIES.map(a => (
            <Pressable key={a} onPress={() => setActivity(a)}
              style={[styles.chip, activity === a && styles.chipOn]}>
              <Text style={[styles.chipText, activity === a && styles.chipTextOn]}>
                {a.replace("_", " ")}
              </Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Blood type (optional)</Text>
        <TextInput style={styles.input} value={bloodType} onChangeText={setBloodType}
          autoCapitalize="characters" placeholder="e.g. O+" placeholderTextColor={colors.textMuted} />

        <Text style={styles.label}>Emergency contact (optional)</Text>
        <TextInput style={styles.input} value={emergency} onChangeText={setEmergency}
          placeholder="Name & phone" placeholderTextColor={colors.textMuted} />

        {error && <Text style={styles.error}>{error}</Text>}

        <Pressable style={styles.primaryBtn} onPress={submit} disabled={submitting}>
          {submitting ? <ActivityIndicator color="#fff" />
            : <Text style={styles.primaryBtnText}>Save and continue</Text>}
        </Pressable>
        <Text style={styles.note}>* required</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
  scroll: { padding: 22, paddingBottom: 48 },
  title: { fontSize: 24, fontWeight: "800", color: colors.text, marginTop: 24 },
  subtitle: { color: colors.textMuted, marginTop: 6, marginBottom: 16, lineHeight: 20 },
  label: { color: colors.text, fontWeight: "600", fontSize: 13, marginTop: 14, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, height: 46, color: colors.text, backgroundColor: colors.card, fontSize: 15 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8, backgroundColor: colors.card },
  chipOn: { borderColor: colors.primary, backgroundColor: colors.primary },
  chipText: { color: colors.text, fontSize: 13, textTransform: "capitalize" },
  chipTextOn: { color: "#fff", fontWeight: "700" },
  error: { color: colors.danger, marginTop: 14, fontSize: 13 },
  primaryBtn: { backgroundColor: colors.primary, paddingVertical: 14, borderRadius: 10, alignItems: "center", marginTop: 22 },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  note: { color: colors.textMuted, fontSize: 12, marginTop: 10, textAlign: "center" },
});
