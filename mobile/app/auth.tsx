import { useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/hooks/useAuth";
import { api, apiBaseUrl, hasAuthToken } from "@/lib/api";
import { colors, config } from "@/config";

const GENDERS = ["male", "female", "other"] as const;
const ACTIVITIES = [
  "sedentary", "light", "moderate", "active", "very_active",
] as const;

export default function AuthScreen() {
  const { user, signIn, signUp, resetPassword, signInDemo, firebaseEnabled } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup" | "reset">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // Signup profile fields — collected on the SAME screen as email/password.
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [activity, setActivity] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setError(null);
    setInfo(null);
    if (!email) {
      setError("Please enter your email.");
      return;
    }
    if (mode !== "reset" && password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    // Validate the profile fields BEFORE creating the Firebase Auth account, so
    // a half-filled signup never creates an orphan auth user.
    if (mode === "signup") {
      if (!name.trim()) { setError("Please enter your name."); return; }
      if (!age.trim() || Number.isNaN(Number(age))) { setError("Enter a valid age."); return; }
      if (!gender) { setError("Please select your gender."); return; }
      if (!heightCm.trim() || Number.isNaN(Number(heightCm))) { setError("Enter a valid height (cm)."); return; }
      if (!weightKg.trim() || Number.isNaN(Number(weightKg))) { setError("Enter a valid weight (kg)."); return; }
      if (!activity) { setError("Please select your activity level."); return; }
    }
    setSubmitting(true);
    let res: { ok: boolean; error?: string };
    if (mode === "reset") {
      res = await resetPassword(email);
    } else if (mode === "signin") {
      res = await signIn(email, password);
    } else {
      res = await signUp(email, password);
    }
    setSubmitting(false);

    if (!res.ok) {
      setError(res.error ?? "Unknown error");
      return;
    }
    if (mode === "reset") {
      setInfo("Reset link sent. Check your email.");
      setMode("signin");
      return;
    }

    // Firebase Auth succeeded → ensure the backend has this user's
    // /users/{uid}/profile + goals (idempotent; uses the verified token uid).
    // We do NOT navigate until bootstrap returns ok:true.
    setSubmitting(true);
    
    // Safe debug (no token/secret): where we're calling + whether a token is
    // attached. Helps diagnose wrong API URL / missing token in the field.
    const tokenAttached = await hasAuthToken();
    if (__DEV__) {
      // Safe dev diagnostics — never logs the token itself.
      // eslint-disable-next-line no-console
      console.log(
        `[auth.${mode}] Firebase Auth succeeded. Calling bootstrap...\\n` +
        `API Base URL: ${apiBaseUrl()}\\n` +
        `Firebase Project ID: ${config.firebase.projectId || "(unset)"}\\n` +
        `Token Available: ${tokenAttached}\\n` +
        `Current User: ${user?.email || "(unknown)"}`,
      );
    }
    
    // Call bootstrap to ensure profile/goals exist in RTDB. On signup we send
    // the collected profile so the backend saves it (one-screen signup) and
    // returns profile_complete=true → straight to dashboard, no second page.
    const bs = mode === "signup"
      ? await api.bootstrap({
          name: name.trim(),
          age: Number(age),
          gender,
          height_cm: Number(heightCm),
          weight_kg: Number(weightKg),
          activity,
        })
      : await api.bootstrap();
    setSubmitting(false);
    
    if (__DEV__) {
      // eslint-disable-next-line no-console
      console.log(
        `[auth.bootstrap] response:`,
        bs.ok
          ? {
              ok: true,
              uid: bs.data.uid,
              firebase_mode: bs.data.firebase_mode,
              write_backend: bs.data.write_backend,
              write_ok: bs.data.write_ok,
              created_profile: bs.data.created_profile,
              created_goals: bs.data.created_goals,
              needs_onboarding: bs.data.needs_onboarding,
            }
          : {
              ok: false,
              code: bs.error?.code,
              message: bs.error?.message,
            },
      );
    }
    
    if (!bs.ok) {
      // Auth succeeded but bootstrap failed. This is critical — do NOT
      // navigate and do NOT show onboarding. Surface the error clearly.
      const msg = bs.error?.message || "Unknown error";
      const code = bs.error?.code || "";
      setError(
        code === "NETWORK_ERROR"
          ? `Network error during profile setup. Please check your connection and try again. (${msg})`
          : `Account created, but profile initialization failed. Please restart the app or contact support. (${msg})`,
      );
      return;
    }
    
    // Bootstrap succeeded. Only now do we navigate based on onboarding needs.
    // Never navigate without a confirmed bootstrap ok:true.
    router.replace(
      bs.data.needs_onboarding ? "/onboarding" : "/(tabs)/dashboard",
    );
  };

  const useDemo = () => {
    signInDemo();
    router.replace("/(tabs)/dashboard");
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.root}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
      <View style={styles.card}>
        <Text style={styles.title}>PulseGuard AI</Text>
        <Text style={styles.subtitle}>
          {mode === "reset" ? "Reset your password"
            : mode === "signin" ? "Sign in to your dashboard"
            : "Create your PulseGuard account"}
        </Text>

        {!firebaseEnabled && (
          <View style={styles.warnBox}>
            <Text style={styles.warnText}>
              Firebase auth is not configured — use "Continue as demo" below.
            </Text>
          </View>
        )}

        <View style={styles.inputRow}>
          <Ionicons name="mail-outline" size={18} color={colors.textMuted} />
          <TextInput
            style={styles.input}
            placeholder="Email"
            autoCapitalize="none"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
            placeholderTextColor={colors.textMuted}
          />
        </View>
        {mode !== "reset" && (
          <View style={styles.inputRow}>
            <Ionicons name="lock-closed-outline" size={18} color={colors.textMuted} />
            <TextInput
              style={styles.input}
              placeholder="Password (min 6 chars)"
              secureTextEntry
              value={password}
              onChangeText={setPassword}
              placeholderTextColor={colors.textMuted}
            />
          </View>
        )}

        {mode === "signup" && (
          <>
            <View style={styles.inputRow}>
              <Ionicons name="person-outline" size={18} color={colors.textMuted} />
              <TextInput style={styles.input} placeholder="Full name" value={name}
                onChangeText={setName} placeholderTextColor={colors.textMuted} />
            </View>
            <View style={styles.inputRow}>
              <Ionicons name="calendar-outline" size={18} color={colors.textMuted} />
              <TextInput style={styles.input} placeholder="Age" keyboardType="number-pad"
                value={age} onChangeText={setAge} placeholderTextColor={colors.textMuted} />
            </View>
            <Text style={styles.fieldLabel}>Gender</Text>
            <View style={styles.chips}>
              {GENDERS.map(g => (
                <Pressable key={g} onPress={() => setGender(g)}
                  style={[styles.chip, gender === g && styles.chipOn]}>
                  <Text style={[styles.chipText, gender === g && styles.chipTextOn]}>{g}</Text>
                </Pressable>
              ))}
            </View>
            <View style={styles.inputRow}>
              <Ionicons name="resize-outline" size={18} color={colors.textMuted} />
              <TextInput style={styles.input} placeholder="Height (cm)" keyboardType="decimal-pad"
                value={heightCm} onChangeText={setHeightCm} placeholderTextColor={colors.textMuted} />
            </View>
            <View style={styles.inputRow}>
              <Ionicons name="barbell-outline" size={18} color={colors.textMuted} />
              <TextInput style={styles.input} placeholder="Weight (kg)" keyboardType="decimal-pad"
                value={weightKg} onChangeText={setWeightKg} placeholderTextColor={colors.textMuted} />
            </View>
            <Text style={styles.fieldLabel}>Activity level</Text>
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
          </>
        )}

        {error && <Text style={styles.error}>{error}</Text>}
        {info && <Text style={styles.info}>{info}</Text>}

        <Pressable
          style={[styles.primaryBtn, !firebaseEnabled && { opacity: 0.5 }]}
          onPress={submit}
          disabled={submitting || !firebaseEnabled}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.primaryBtnText}>
              {mode === "reset" ? "Send reset link"
                : mode === "signin" ? "Sign In"
                : "Sign Up"}
            </Text>
          )}
        </Pressable>

        <View style={styles.linksRow}>
          {mode === "signin" && (
            <>
              <Pressable onPress={() => setMode("signup")}>
                <Text style={styles.linkText}>Create account</Text>
              </Pressable>
              <Pressable onPress={() => setMode("reset")}>
                <Text style={styles.linkSmall}>Forgot password?</Text>
              </Pressable>
            </>
          )}
          {mode === "signup" && (
            <Pressable onPress={() => setMode("signin")}>
              <Text style={styles.linkText}>Have an account? Sign in</Text>
            </Pressable>
          )}
          {mode === "reset" && (
            <Pressable onPress={() => setMode("signin")}>
              <Text style={styles.linkText}>Back to sign in</Text>
            </Pressable>
          )}
        </View>

        <View style={styles.divider} />

        <Pressable style={styles.demoBtn} onPress={useDemo}>
          <Ionicons name="play-circle-outline" size={18} color={colors.primary} />
          <Text style={styles.demoText}>Continue as demo</Text>
        </Pressable>
        <Text style={styles.disclaimer}>
          Demo mode skips authentication and uses a simulated user — useful when Firebase Auth is not
          configured or you just want to explore the dashboard.
        </Text>
      </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  scroll: { flexGrow: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  card: { width: "100%", maxWidth: 420, backgroundColor: colors.card, padding: 22, borderRadius: 16, borderWidth: 1, borderColor: colors.border, shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 2 },
  title: { fontSize: 26, fontWeight: "800", color: colors.text, textAlign: "center" },
  subtitle: { color: colors.textMuted, textAlign: "center", marginTop: 4, marginBottom: 16 },
  warnBox: { backgroundColor: "#fff7ed", borderColor: "#fdba74", borderWidth: 1, padding: 10, borderRadius: 8, marginBottom: 12 },
  warnText: { color: "#9a3412", fontSize: 12, textAlign: "center" },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, marginBottom: 10, backgroundColor: "#fafafa" },
  input: { flex: 1, height: 46, color: colors.text, fontSize: 15 },
  error: { color: colors.danger, marginVertical: 6, fontSize: 13, textAlign: "center" },
  info: { color: colors.primary, marginVertical: 6, fontSize: 13, textAlign: "center" },
  primaryBtn: { backgroundColor: colors.primary, paddingVertical: 13, borderRadius: 10, alignItems: "center", marginTop: 6 },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  linksRow: { flexDirection: "column", alignItems: "center", gap: 6, marginTop: 12 },
  linkText: { color: colors.primary, fontSize: 13, fontWeight: "500" },
  linkSmall: { color: colors.textMuted, fontSize: 12 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 16 },
  demoBtn: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, borderWidth: 1, borderColor: colors.primary, borderRadius: 10, paddingVertical: 12 },
  demoText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  disclaimer: { fontSize: 11, color: colors.textMuted, textAlign: "center", marginTop: 10, lineHeight: 16 },
  fieldLabel: { color: colors.text, fontWeight: "600", fontSize: 13, marginTop: 2, marginBottom: 6 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 10 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: "#fafafa" },
  chipOn: { borderColor: colors.primary, backgroundColor: colors.primary },
  chipText: { color: colors.text, fontSize: 12, textTransform: "capitalize" },
  chipTextOn: { color: "#fff", fontWeight: "700" },
});
