import { useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable,
  StyleSheet, Text, TextInput, View,
} from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/hooks/useAuth";
import { api, apiBaseUrl, hasAuthToken } from "@/lib/api";
import { colors } from "@/config";

export default function AuthScreen() {
  const { signIn, signUp, resetPassword, signInDemo, firebaseEnabled } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup" | "reset">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      // eslint-disable-next-line no-console
      console.log(
        `[bootstrap] ${mode} ok → POST ${apiBaseUrl()}/api/auth/bootstrap ` +
        `(Authorization attached: ${tokenAttached})`,
      );
    }
    const bs = await api.bootstrap();
    setSubmitting(false);
    if (__DEV__) {
      // eslint-disable-next-line no-console
      console.log("[bootstrap] result:", bs.ok
        ? {
            ok: true, uid: bs.data.uid,
            created_profile: bs.data.created_profile,
            created_goals: bs.data.created_goals,
            write_backend: bs.data.write_backend,
            write_ok: bs.data.write_ok,
          }
        : { ok: false, error: bs.error });
    }
    if (!bs.ok) {
      setError(
        "Account created, but profile initialization failed. " +
        (bs.error.message || "Please check your connection and try again."),
      );
      return;
    }
    router.replace("/(tabs)/dashboard");
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
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center", padding: 24 },
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
});
