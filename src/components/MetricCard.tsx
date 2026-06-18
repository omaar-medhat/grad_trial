import { cn } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";
import type { HealthStatus } from "@/lib/health-data";
import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  unit: string;
  status?: HealthStatus;
  progress?: number;
  delay?: number;
  hint?: string;
}

const accentByStatus: Record<HealthStatus, string> = {
  normal:  "from-health-normal/8 to-transparent",
  warning: "from-health-warning/10 to-transparent",
  danger:  "from-health-danger/10 to-transparent",
  low:     "from-health-low/10 to-transparent",
};

export function MetricCard({ icon: Icon, label, value, unit, status, progress, delay = 0, hint }: MetricCardProps) {
  const accent = status ? accentByStatus[status] : "from-primary/6 to-transparent";

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-2xl border border-border bg-card p-4 transition-all duration-300",
        "hover:-translate-y-0.5 hover:shadow-lg",
        "animate-fade-in-up",
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={cn("pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b opacity-80", accent)} />

      <div className="relative">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-card shadow-sm ring-1 ring-border">
              <Icon className="h-4 w-4 text-primary" />
            </div>
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
          </div>
          {status && <StatusBadge status={status} />}
        </div>

        <div className="mt-3 flex items-baseline gap-1.5">
          <span className="text-3xl font-bold tracking-tight tabular-nums text-foreground animate-count-up">
            {value}
          </span>
          {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
        </div>

        {hint && <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>}

        {progress !== undefined && (
          <div className="mt-3">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-700",
                  progress >= 100 ? "bg-health-normal"
                    : progress >= 60 ? "bg-primary"
                    : "bg-health-warning"
                )}
                style={{ width: `${Math.min(progress, 100)}%` }}
              />
            </div>
            <span className="mt-1 inline-block text-[10px] text-muted-foreground">
              {Math.round(progress)}% of goal
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
