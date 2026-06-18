import { cn } from "@/lib/utils";
import type { HealthStatus } from "@/lib/health-data";

const statusConfig: Record<HealthStatus, { label: string; className: string }> = {
  normal:  { label: "Normal",  className: "bg-health-normal/12  text-health-normal  border-health-normal/30"  },
  warning: { label: "High",    className: "bg-health-warning/15 text-health-warning border-health-warning/30" },
  danger:  { label: "Critical",className: "bg-health-danger/15  text-health-danger  border-health-danger/30"  },
  low:     { label: "Low",     className: "bg-health-low/12     text-health-low     border-health-low/30"     },
};

export function StatusBadge({ status }: { status: HealthStatus }) {
  const config = statusConfig[status];
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider", config.className)}>
      {config.label}
    </span>
  );
}
