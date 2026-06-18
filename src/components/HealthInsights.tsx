/**
 * HealthInsights
 * --------------
 * Plain-language interpretation of the latest reading. Translates the rule
 * engine output (normal/warning/high + reasons) into friendly sentences a
 * non-clinician can read at a glance. No statistics, no Greek letters.
 */
import { Sparkles, Heart, Droplets, Thermometer, Moon, Footprints, Flame } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FirebaseTelemetry } from "@/integrations/firebase/client";

interface Insight {
  icon: React.ComponentType<{ className?: string }>;
  text: string;
  tone: "normal" | "warning" | "high";
}

function buildInsights(t: FirebaseTelemetry | null): Insight[] {
  if (!t) return [];
  const out: Insight[] = [];

  // Heart rate
  if (t.heart_rate > 140) out.push({ icon: Heart, text: "Heart rate is critically high — stop activity and seek help if it persists.", tone: "high" });
  else if (t.heart_rate > 100) out.push({ icon: Heart, text: "Heart rate is elevated above your typical resting range.", tone: "warning" });
  else if (t.heart_rate < 40) out.push({ icon: Heart, text: "Heart rate is critically low — please seek medical advice.", tone: "high" });
  else if (t.heart_rate < 60) out.push({ icon: Heart, text: "Heart rate is on the low side of normal.", tone: "warning" });
  else out.push({ icon: Heart, text: "Heart rate is in a healthy resting range.", tone: "normal" });

  // SpO2
  if (t.spo2 < 92) out.push({ icon: Droplets, text: "Blood oxygen is low — take slow, deep breaths and rest.", tone: "high" });
  else if (t.spo2 < 95) out.push({ icon: Droplets, text: "Blood oxygen is slightly below the typical range.", tone: "warning" });
  else out.push({ icon: Droplets, text: "Blood oxygen looks healthy.", tone: "normal" });

  // Temperature
  if (t.temperature_c >= 38.5) out.push({ icon: Thermometer, text: "Temperature suggests a high fever — rest and hydrate.", tone: "high" });
  else if (t.temperature_c > 37.5) out.push({ icon: Thermometer, text: "Temperature is mildly elevated.", tone: "warning" });
  else if (t.temperature_c < 35.5) out.push({ icon: Thermometer, text: "Body temperature is below the normal range.", tone: "warning" });
  else out.push({ icon: Thermometer, text: "Body temperature is normal.", tone: "normal" });

  // Sleep
  const sleepHrs = (t.sleep_duration_sec || 0) / 3600;
  if (sleepHrs > 0 && sleepHrs < 6) {
    out.push({ icon: Moon, text: `You logged ${sleepHrs.toFixed(1)} hours of sleep — try to rest a little more tonight.`, tone: "warning" });
  } else if (sleepHrs >= 7) {
    out.push({ icon: Moon, text: `You slept ${sleepHrs.toFixed(1)} hours — that's a healthy amount.`, tone: "normal" });
  }

  // Activity (steps)
  if (t.steps >= 8000) out.push({ icon: Footprints, text: `Great job — ${t.steps.toLocaleString()} steps today.`, tone: "normal" });
  else if (t.steps >= 3000) out.push({ icon: Footprints, text: `Steady activity (${t.steps.toLocaleString()} steps). A short walk could help.`, tone: "normal" });

  // Calories
  if (t.calories >= 400) out.push({ icon: Flame, text: `You've burned ${Math.round(t.calories)} kcal today.`, tone: "normal" });

  return out;
}

const tonePalette = {
  normal: "border-health-normal/20 bg-health-normal/5 text-health-normal",
  warning: "border-health-warning/30 bg-health-warning/10 text-health-warning",
  high: "border-health-danger/30 bg-health-danger/10 text-health-danger",
} as const;

export function HealthInsights({ telemetry }: { telemetry: FirebaseTelemetry | null }) {
  const insights = buildInsights(telemetry);

  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      <header className="mb-4 flex items-center gap-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl gradient-health-bg">
          <Sparkles className="h-4 w-4 text-primary-foreground" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-foreground">Today's insights</h3>
          <p className="text-xs text-muted-foreground">Plain-language summary of your latest reading</p>
        </div>
      </header>

      {!telemetry ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          Waiting for the first reading from your wearable…
        </div>
      ) : (
        <ul className="space-y-2">
          {insights.map((ins, i) => {
            const Icon = ins.icon;
            return (
              <li
                key={i}
                className={cn("flex items-start gap-3 rounded-lg border px-3 py-2.5 text-sm", tonePalette[ins.tone])}
              >
                <Icon className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <span className="text-foreground/90">{ins.text}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
