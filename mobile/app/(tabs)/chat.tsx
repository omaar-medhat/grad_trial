import { useRef, useState } from "react";
import {
  ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable,
  StyleSheet, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/hooks/useAuth";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { api } from "@/lib/api";
import { colors } from "@/config";

interface Msg { role: "user" | "assistant"; content: string }

export default function Chat() {
  const { user } = useAuth();
  const uid = user?.id ?? "";
  const { data: liveData } = useLiveTelemetry(uid);
  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", content: "Hi! I can explain your live bracelet readings and alerts. I'm not a doctor — for medical concerns please consult a professional." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<FlatList<Msg>>(null);

  const send = async () => {
    const msg = input.trim();
    if (!msg || busy) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: msg }]);
    setBusy(true);
    const res = await api.chat(uid, msg, liveData);
    setBusy(false);
    setMessages(prev => [
      ...prev,
      {
        role: "assistant",
        content: res.ok
          ? res.data.response
          : "I couldn't reach the assistant right now. Please try again in a moment.",
      },
    ]);
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={80}
    >
      <FlatList
        ref={listRef}
        data={messages}
        contentContainerStyle={{ padding: 16, gap: 10 }}
        keyExtractor={(_, i) => String(i)}
        renderItem={({ item }) => (
          <View style={[
            styles.bubble,
            item.role === "user" ? styles.user : styles.assistant,
          ]}>
            <Text style={item.role === "user" ? styles.userText : styles.assistantText}>
              {item.content}
            </Text>
          </View>
        )}
        ListFooterComponent={busy ? <ActivityIndicator color={colors.primary} style={{ marginTop: 8 }} /> : null}
      />
      <View style={styles.inputBar}>
        <TextInput
          style={styles.input}
          placeholder="Ask about your vitals..."
          placeholderTextColor={colors.textMuted}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={send}
          returnKeyType="send"
          editable={!busy}
        />
        <Pressable style={styles.sendBtn} onPress={send} disabled={busy || !input.trim()}>
          <Ionicons name="send" size={18} color="#fff" />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  bubble: { maxWidth: "85%", padding: 12, borderRadius: 14 },
  user: { alignSelf: "flex-end", backgroundColor: colors.primary, borderBottomRightRadius: 4 },
  assistant: { alignSelf: "flex-start", backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 4 },
  userText: { color: "#fff" },
  assistantText: { color: colors.text },
  inputBar: { flexDirection: "row", padding: 12, gap: 8, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.card },
  input: { flex: 1, paddingHorizontal: 14, height: 44, borderRadius: 22, backgroundColor: colors.bg, color: colors.text },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
});
