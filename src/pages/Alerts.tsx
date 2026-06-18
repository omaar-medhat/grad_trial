import { AlertOctagon, AlertTriangle, CheckCircle2, Bell, BatteryWarning, BatteryLow } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { cn } from "@/lib/utils";

function timeAgo(ts: number): string {
  const seconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(ts).toLocaleDateString();
}

const Alerts = () => {
  const { alerts, historicalAlerts } = useLiveTelemetry();
  const high = alerts.filter(a => a.risk_level === "high");
  const warning = alerts.filter(a => a.risk_level === "warning");

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Alerts</h1>
        <p className="text-sm text-muted-foreground">Your bracelet's current state, plus recent history — kept clearly separate.</p>
      </header>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <SummaryTile
          tone="normal"
          icon={CheckCircle2}
          label="All clear"
          value={alerts.length === 0 ? "Yes" : "No"}
        />
        <SummaryTile
          tone="warning"
          icon={AlertTriangle}
          label="Watch"
          value={warning.length}
        />
        <SummaryTile
          tone="high"
          icon={AlertOctagon}
          label="Needs attention"
          value={high.length}
        />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-base">Current alerts <span className="text-xs font-normal text-muted-foreground">(live state)</span></CardTitle>
          {alerts.length > 0 && (
            <Badge variant="outline">{alerts.length} active</Badge>
          )}
        </CardHeader>
        <CardContent>
          {alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-health-normal/10">
                <CheckCircle2 className="h-7 w-7 text-health-normal" />
              </div>
              <p className="mt-4 text-base font-semibold text-foreground">You're all caught up</p>
              <p className="mt-1 max-w-sm text-sm text-muted-foreground">
                No alerts have been raised. We'll let you know here the moment something looks off.
              </p>
            </div>
          ) : (
            <ul className="space-y-3">
              {alerts.map((a, i) => {
                const isHigh = a.risk_level === "high";
                const isBattery = a.type === "low_battery";
                const Icon = isBattery
                  ? (isHigh ? BatteryWarning : BatteryLow)
                  : (isHigh ? AlertOctagon : AlertTriangle);
                return (
                  <li
                    key={`${a.timestamp}-${i}`}
                    className={cn(
                      "rounded-xl border p-4",
                      isHigh
                        ? "border-health-danger/30 bg-health-danger/5"
                        : "border-health-warning/30 bg-health-warning/5"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={cn(
                          "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl",
                          isHigh ? "bg-health-danger/15" : "bg-health-warning/15"
                        )}
                      >
                        <Icon className={cn("h-4 w-4", isHigh ? "text-health-danger" : "text-health-warning")} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground">{a.message}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {timeAgo(a.timestamp)}
                          {a.source ? <> · from {a.source.replace("_", " ")}</> : null}
                        </p>
                      </div>
                      <Badge
                        className={cn(
                          "text-[10px] font-bold uppercase",
                          isHigh ? "bg-health-danger text-white" : "bg-health-warning text-white"
                        )}
                      >
                        {isBattery ? "Battery" : isHigh ? "Critical" : "Watch"}
                      </Badge>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Historical alerts — clearly labelled as past, not current state. */}
      {historicalAlerts.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-base">
              History <span className="text-xs font-normal text-muted-foreground">(past readings, not current state)</span>
            </CardTitle>
            <Badge variant="outline">{historicalAlerts.length}</Badge>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {historicalAlerts.slice(-30).reverse().map((a, i) => (
                <li key={`${a.timestamp}-${i}`} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-3 py-2">
                  <span className="min-w-0 truncate text-sm text-foreground/80">{a.message}</span>
                  <span className="flex-shrink-0 text-xs text-muted-foreground">{timeAgo(a.timestamp)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

function SummaryTile({
  tone, icon: Icon, label, value,
}: { tone: "normal" | "warning" | "high"; icon: React.ComponentType<{ className?: string }>; label: string; value: string | number }) {
  const palette = {
    normal:  { bg: "bg-health-normal/10",  fg: "text-health-normal" },
    warning: { bg: "bg-health-warning/10", fg: "text-health-warning" },
    high:    { bg: "bg-health-danger/10",  fg: "text-health-danger" },
  }[tone];
  return (
    <Card className="border-border/70">
      <CardContent className="flex items-center gap-3 p-4">
        <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl", palette.bg)}>
          <Icon className={cn("h-5 w-5", palette.fg)} />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-xl font-bold text-foreground">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export default Alerts;
