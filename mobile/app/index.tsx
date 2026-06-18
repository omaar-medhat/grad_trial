import { useEffect } from "react";
import { ActivityIndicator, Image, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { useAuth } from "@/hooks/useAuth";
import { colors } from "@/config";

export default function Splash() {
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    const t = setTimeout(() => {
      router.replace(user ? "/(tabs)/dashboard" : "/auth");
    }, 600);
    return () => clearTimeout(t);
  }, [user, loading]);

  return (
    <View style={styles.container}>
      <Image
        // eslint-disable-next-line @typescript-eslint/no-require-imports -- Metro asset loader requires require() for static images
        source={require("../assets/icon.png")}
        style={styles.logo}
        resizeMode="contain"
      />
      <Text style={styles.title}>PulseGuard AI</Text>
      <Text style={styles.subtitle}>Smart Health Monitoring</Text>
      <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center", padding: 24 },
  logo: { width: 96, height: 96, marginBottom: 16 },
  title: { fontSize: 28, fontWeight: "700", color: colors.text },
  subtitle: { marginTop: 4, color: colors.textMuted },
});
