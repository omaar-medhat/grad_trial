import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { MessageCircle, Send, Loader2, Trash2, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface Msg {
  role: "user" | "assistant";
  content: string;
  source?: string;
  latency_ms?: number;
  telemetryOrigin?: string;
  telemetrySource?: string;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
// The medical chatbot (real TinyLlama LoRA model) is served at the backend
// root, not under /api — strip a trailing /api so both layouts resolve.
const MEDICAL_SLM_URL = `${API_BASE.replace(/\/api$/, "")}/ai/medical-slm`;

const SUGGESTIONS = [
  "How are my vitals right now?",
  "Should I be worried about my heart rate?",
  "Tips for better sleep tonight",
  "What does my SpO₂ reading mean?",
];

const Chat = () => {
  const { user } = useAuth();
  const live = useLiveTelemetry();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const sendMessage = async (text?: string) => {
    const messageText = (text ?? input).trim();
    if (!messageText || isLoading) return;

    setMessages(prev => [...prev, { role: "user", content: messageText }]);
    setInput("");
    setIsLoading(true);

    try {
      // Pass the live vitals as plain-language context so the medical model has
      // some grounding (it takes {question, context}, not a telemetry object).
      const context = live.data
        ? `Current vitals — HR ${live.data.heart_rate} bpm, ` +
          `SpO2 ${live.data.spo2}%, temp ${live.data.temperature_c}°C` +
          (live.data.risk_level ? `, risk level ${live.data.risk_level}` : "")
        : undefined;
      const resp = await fetch(MEDICAL_SLM_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: messageText, context }),
      });
      const envelope = await resp.json();
      // Backend returns {ok, data: {answer, model, fallback, latency_ms}}.
      const payload = envelope?.ok && envelope?.data ? envelope.data : envelope;
      const reply = payload?.answer || "I couldn't generate a reply right now. Please try again.";
      setMessages(prev => [...prev, {
        role: "assistant",
        content: reply,
        source: payload?.model,
        latency_ms: payload?.latency_ms,
      }]);
    } catch (e) {
      console.error("[chat] network error:", e);
      setMessages(prev => [...prev, {
        role: "assistant",
        content:
          "I couldn't reach the AI Health Assistant. Please make sure the backend is running on port 5000 and try again.",
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage();
  };

  const livePill = live.data
    ? `HR ${live.data.heart_rate} · SpO₂ ${live.data.spo2}% · ${live.data.temperature_c}°C`
    : "No live readings yet";

  return (
    <div className="mx-auto max-w-3xl">
      <Card className="flex h-[calc(100vh-9rem)] flex-col border-border/60 shadow-sm">
        <CardHeader className="flex-row items-start justify-between gap-3 border-b border-border pb-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl gradient-health-bg">
              <Sparkles className="h-5 w-5 text-primary-foreground" />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-base flex items-center gap-2">
                AI Health Assistant
                {live.data?.risk_level && (
                  <Badge
                    variant="outline"
                    className={
                      live.data.risk_level === "high"
                        ? "border-health-danger/40 text-health-danger"
                        : live.data.risk_level === "warning"
                        ? "border-health-warning/40 text-health-warning"
                        : "border-health-normal/40 text-health-normal"
                    }
                  >
                    {live.data.risk_level}
                  </Badge>
                )}
              </CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground truncate">{livePill}</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" aria-label="Clear conversation" onClick={() => setMessages([])}>
            <Trash2 className="h-4 w-4 text-muted-foreground" />
          </Button>
        </CardHeader>

        <CardContent className="flex flex-1 flex-col p-0">
          <ScrollArea className="flex-1 p-4">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
                <MessageCircle className="mb-3 h-12 w-12 opacity-30" />
                <p className="font-medium text-foreground">How can I help with your health?</p>
                <p className="mt-1 text-xs max-w-xs">
                  Powered by a local fine-tuned medical AI model, with your live
                  vitals as context. Replies may take a few seconds. I am not a doctor.
                </p>
                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map(q => (
                    <Button
                      key={q}
                      variant="outline"
                      size="sm"
                      className="text-xs hover:bg-primary/10 hover:text-primary hover:border-primary/40"
                      onClick={() => sendMessage(q)}
                    >
                      {q}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`mb-4 flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-primary text-primary-foreground rounded-br-md"
                      : "bg-secondary text-secondary-foreground rounded-bl-md"
                  }`}
                >
                  {m.role === "assistant" ? (
                    <>
                      <div className="prose prose-sm max-w-none text-left text-foreground/90">
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                      </div>
                      {(m.source || m.latency_ms !== undefined) && (
                        <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                          {m.source && <span className="rounded bg-background/50 px-1.5 py-0.5">via {m.source}</span>}
                          {m.telemetryOrigin && (
                            <span className="rounded bg-background/50 px-1.5 py-0.5">
                              data: {m.telemetryOrigin}{m.telemetrySource ? ` (${m.telemetrySource})` : ""}
                            </span>
                          )}
                          {m.latency_ms !== undefined && (
                            <span className="rounded bg-background/50 px-1.5 py-0.5">{m.latency_ms} ms</span>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  )}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="mb-4 flex justify-start">
                <div className="flex items-center gap-2 rounded-2xl rounded-bl-md bg-secondary px-4 py-3">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">
                    Thinking… the local AI model runs on CPU and may take a few seconds.
                  </span>
                </div>
              </div>
            )}
            <div ref={scrollRef} />
          </ScrollArea>

          <div className="border-t border-border p-4">
            <form onSubmit={onSubmit} className="flex gap-2">
              <Input
                placeholder="Ask about your health…"
                value={input}
                onChange={e => setInput(e.target.value)}
                disabled={isLoading}
                aria-label="Message"
              />
              <Button type="submit" size="icon" disabled={isLoading || !input.trim()} aria-label="Send">
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </form>
            <p className="mt-2 text-center text-[10px] text-muted-foreground">
              PulseGuard AI is not a doctor. For medical emergencies call your local emergency number.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Chat;
