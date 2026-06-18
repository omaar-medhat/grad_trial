/**
 * AlertSummary
 * ------------
 * Quiet inline strip that shows the count of recent alerts (and links to the
 * dedicated /alerts page). No dramatic UI when there's nothing to worry about.
 */
import { Link } from "react-router-dom";
import { Bell, CheckCircle2, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  alerts: { risk_level: "warning" | "high"; message: string; timestamp: number }[];
}

export function AlertSummary({ alerts }: Props) {
  const highCount = alerts.filter(a => a.risk_level === "high").length;
  const warningCount = alerts.length - highCount;
  const hasAny = alerts.length > 0;

  if (!hasAny) {
    return (
      <div className="flex items-center justify-between rounded-2xl border border-health-normal/20 bg-health-normal/5 p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-health-normal/15">
            <CheckCircle2 className="h-4 w-4 text-health-normal" />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">All clear today</p>
            <p className="text-xs text-muted-foreground">No alerts have been raised in the last 24 hours.</p>
          </div>
        </div>
        <Link to="/alerts" className="text-xs font-medium text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          History <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    );
  }

  const newest = alerts[0];

  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-2xl border p-4",
        highCount > 0
          ? "border-health-danger/30 bg-health-danger/5"
          : "border-health-warning/30 bg-health-warning/5"
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <div
          className={cn(
            "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl",
            highCount > 0 ? "bg-health-danger/15" : "bg-health-warning/15"
          )}
        >
          <Bell className={cn("h-4 w-4", highCount > 0 ? "text-health-danger" : "text-health-warning")} />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Current alerts · live state
          </p>
          <p className="truncate text-sm font-semibold text-foreground">{newest.message}</p>
          <p className="text-xs text-muted-foreground">
            {highCount > 0 && <>{highCount} critical · </>}
            {warningCount > 0 && <>{warningCount} watch · </>}
            most recent {new Date(newest.timestamp).toLocaleTimeString()}
          </p>
        </div>
      </div>
      <Link
        to="/alerts"
        className="flex-shrink-0 rounded-full border border-border bg-background/60 px-3 py-1 text-xs font-medium hover:bg-background"
      >
        View all
      </Link>
    </div>
  );
}
