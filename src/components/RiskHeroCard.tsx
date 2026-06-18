import { ShieldCheck, AlertTriangle, AlertOctagon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FirebaseTelemetry } from "@/integrations/firebase/client";

interface Props {
  telemetry: FirebaseTelemetry | null;
}

const palette = {
  normal: {
    bg: "bg-gradient-to-br from-emerald-50 to-emerald-100/60 dark:from-emerald-950/40 dark:to-emerald-900/30",
    border: "border-emerald-200",
    text: "text-emerald-700 dark:text-emerald-300",
    pill: "bg-emerald-600 text-white",
    icon: ShieldCheck,
    label: "All Good",
    subtitle: "Your vitals look healthy.",
  },
  warning: {
    bg: "bg-gradient-to-br from-amber-50 to-amber-100/60 dark:from-amber-950/40 dark:to-amber-900/30",
    border: "border-amber-200",
    text: "text-amber-700 dark:text-amber-300",
    pill: "bg-amber-500 text-white",
    icon: AlertTriangle,
    label: "Watch",
    subtitle: "Something is slightly outside your normal range.",
  },
  high: {
    bg: "bg-gradient-to-br from-red-50 to-red-100/60 dark:from-red-950/40 dark:to-red-900/30",
    border: "border-red-200",
    text: "text-red-700 dark:text-red-300",
    pill: "bg-red-600 text-white",
    icon: AlertOctagon,
    label: "Needs Attention",
    subtitle: "Please slow down and review your readings.",
  },
} as const;

export function RiskHeroCard({ telemetry }: Props) {
  const risk = (telemetry?.risk_level ?? "normal") as keyof typeof palette;
  const cfg = palette[risk];
  const Icon = cfg.icon;
  const message = telemetry?.alert_message ?? cfg.subtitle;
  const updated = telemetry?.timestamp
    ? new Date(telemetry.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "—";

  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-2xl border p-6 transition-colors animate-fade-in-up",
        cfg.bg,
        cfg.border,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-5">
        <div
          className={cn(
            "flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-2xl bg-white/80 shadow-sm dark:bg-black/20",
            cfg.text
          )}
        >
          <Icon className="h-8 w-8" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider", cfg.pill)}>
              {risk}
            </span>
            <span className="text-[11px] text-muted-foreground">updated {updated}</span>
          </div>
          <h2 className={cn("mt-2 text-2xl sm:text-3xl font-bold leading-tight tracking-tight", cfg.text)}>
            {cfg.label}
          </h2>
          <p className="mt-1 text-sm text-foreground/75 break-words max-w-prose">{message}</p>
        </div>

        {typeof telemetry?.wellness_score === "number" && (
          <div className={cn("hidden flex-shrink-0 flex-col items-center sm:flex", cfg.text)} title="Wellness score (0–100, not a diagnosis)">
            <span className="text-4xl font-extrabold leading-none tabular-nums">{telemetry.wellness_score}</span>
            <span className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Wellness</span>
          </div>
        )}
      </div>
    </section>
  );
}
