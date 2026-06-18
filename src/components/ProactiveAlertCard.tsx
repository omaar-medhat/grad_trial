/**
 * ProactiveAlertCard
 * ------------------
 * Surfaces a single proactive assistant message when a NEW current alert
 * appears from the backend alert engine. It is grounded ONLY in backend
 * current alerts — it never invents alerts.
 *
 * Anti-spam: alerts are de-duplicated by condition (type+severity), not by the
 * per-reading id (which changes every poll). A condition is shown once; it can
 * re-alert only after it clears and returns. Dismissing keeps it suppressed
 * while still active.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, AlertOctagon, X, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LiveAlert } from "@/hooks/useLiveTelemetry";

const SEV_ORDER: Record<string, number> = { watch: 1, warning: 2, critical: 3 };

function key(a: LiveAlert): string {
  return `${a.type ?? a.metric ?? "alert"}:${a.severity ?? "watch"}`;
}

export function ProactiveAlertCard({ alerts }: { alerts: LiveAlert[] }) {
  // Conditions the user has already seen/dismissed while still active.
  const acknowledged = useRef<Set<string>>(new Set());
  const [active, setActive] = useState<LiveAlert | null>(null);

  useEffect(() => {
    const actionable = alerts.filter(
      (a) => a.severity === "watch" || a.severity === "warning" || a.severity === "critical",
    );
    const activeKeys = new Set(actionable.map(key));

    // A condition that cleared can alert again next time it recurs.
    for (const k of [...acknowledged.current]) {
      if (!activeKeys.has(k)) acknowledged.current.delete(k);
    }

    // If the currently shown card's condition is gone, drop it.
    setActive((prev) => (prev && !activeKeys.has(key(prev)) ? null : prev));

    // Pick the most severe unacknowledged condition to surface.
    const fresh = actionable
      .filter((a) => !acknowledged.current.has(key(a)))
      .sort((a, b) => (SEV_ORDER[b.severity ?? ""] ?? 0) - (SEV_ORDER[a.severity ?? ""] ?? 0));
    if (fresh.length) {
      const top = fresh[0];
      acknowledged.current.add(key(top));
      setActive(top);
    }
  }, [alerts]);

  if (!active) return null;

  const critical = active.severity === "critical";
  const Icon = critical ? AlertOctagon : AlertTriangle;
  const dismiss = () => {
    if (active) acknowledged.current.add(key(active));
    setActive(null);
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-start gap-3 rounded-2xl border p-4 shadow-sm",
        critical
          ? "border-health-danger/40 bg-health-danger/5"
          : "border-health-warning/40 bg-health-warning/5",
      )}
    >
      <div
        className={cn(
          "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl",
          critical ? "bg-health-danger/15" : "bg-health-warning/15",
        )}
      >
        <Icon className={cn("h-4 w-4", critical ? "text-health-danger" : "text-health-warning")} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">
          I noticed a current alert from your bracelet: {active.title ?? active.message}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {active.message}
          {active.requiresMedicalAttention
            ? " If you feel unwell, seek medical help."
            : ""}
        </p>
        <Link
          to="/chat"
          className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
        >
          <MessageCircle className="h-3 w-3" /> Explain it
        </Link>
      </div>
      <button
        type="button"
        aria-label="Dismiss alert"
        onClick={dismiss}
        className="flex-shrink-0 rounded-md p-1 text-muted-foreground hover:bg-background/60"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
