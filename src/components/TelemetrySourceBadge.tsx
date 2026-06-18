import { CloudOff, Cloud, Cpu, Server, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";

type Source = "firebase" | "simulator" | "offline" | "backend";
type DeviceStatus =
  | "connected" | "stale" | "disconnected" | "unknown" | "offline";

interface Props {
  source: Source;
  stale: boolean;
  lastUpdate: number | null;
  deviceStatus?: DeviceStatus;
  lastSeenSeconds?: number | null;
}

/**
 * Live data-origin indicator. Clearly distinguishes Firebase live sensor data
 * from simulator/demo data, and surfaces stale / disconnected / offline states
 * (so a frozen reading is never mistaken for a fresh one).
 */
export function TelemetrySourceBadge({
  source, stale, lastUpdate, deviceStatus, lastSeenSeconds,
}: Props) {
  const base = {
    firebase: { icon: Cloud, label: "Firebase live", tone: "text-health-normal", dot: "bg-health-normal" },
    backend:  { icon: Server, label: "Connected", tone: "text-health-info", dot: "bg-health-info" },
    simulator:{ icon: Cpu, label: "Simulator demo", tone: "text-muted-foreground", dot: "bg-muted-foreground" },
    offline:  { icon: WifiOff, label: "Offline", tone: "text-health-warning", dot: "bg-health-warning" },
  }[source];

  const isDisconnected = deviceStatus === "disconnected" || source === "offline";
  const isStale = stale || deviceStatus === "stale";

  let Icon = base.icon;
  let tone = base.tone;
  let label = base.label;
  if (isDisconnected) {
    Icon = CloudOff; tone = "text-health-danger"; label = "Disconnected";
  } else if (isStale) {
    Icon = CloudOff; tone = "text-health-warning"; label = "Stale";
  }

  const seconds = typeof lastSeenSeconds === "number"
    ? Math.round(lastSeenSeconds)
    : lastUpdate ? Math.max(0, Math.round((Date.now() - lastUpdate) / 1000)) : null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs shadow-sm",
        isStale && "border-health-warning/40 bg-health-warning/5",
        isDisconnected && "border-health-danger/40 bg-health-danger/5",
      )}
    >
      <span className="relative flex h-2 w-2">
        {!isStale && !isDisconnected && (
          <span className={cn(
            "absolute inline-flex h-full w-full animate-ping rounded-full opacity-60",
            base.dot,
          )} />
        )}
        <span className={cn(
          "inline-flex h-2 w-2 rounded-full",
          isDisconnected ? "bg-health-danger" : isStale ? "bg-health-warning" : base.dot,
        )} />
      </span>
      <Icon className={cn("h-3.5 w-3.5", tone)} />
      <span className={cn("font-medium", tone)}>{label}</span>
      {seconds !== null && (
        <span className="text-muted-foreground">· {seconds}s ago</span>
      )}
    </div>
  );
}
