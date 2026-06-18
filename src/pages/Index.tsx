import { Activity, Thermometer, Footprints, Flame, Moon, Droplets, Zap, BatteryFull, HeartPulse, AlertTriangle, WifiOff } from "lucide-react";
import { useState } from "react";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
import {
  secondsToTime,
  classifyTemperature, classifyHeartRate, classifySpO2, classifyBattery,
} from "@/lib/health-data";
import { MetricCard } from "@/components/MetricCard";
import { VitalsChart } from "@/components/VitalsChart";
import { HealthInsights } from "@/components/HealthInsights";
import { AlertSummary } from "@/components/AlertSummary";
import { ProactiveAlertCard } from "@/components/ProactiveAlertCard";
import { TelemetrySourceBadge } from "@/components/TelemetrySourceBadge";
import { RiskHeroCard } from "@/components/RiskHeroCard";
import { ModelInsight } from "@/components/ModelInsight";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

// Demo scenarios the backend simulator can be forced into (mirrors
// simulator.AVAILABLE_MODES). label is what the user sees.
const SIMULATOR_MODES: Array<{ value: string; label: string }> = [
  { value: "",            label: "Random" },
  { value: "resting",     label: "Resting" },
  { value: "walking",     label: "Walking" },
  { value: "running",     label: "Running" },
  { value: "sleep",       label: "Sleep" },
  { value: "fever",       label: "Fever" },
  { value: "stress",      label: "Stress" },
  { value: "anomaly",     label: "Anomaly" },
  { value: "low_battery", label: "Low battery" },
];

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

// Static goal targets for the progress rings. These are user *goals*, NOT
// telemetry — so no in-browser simulator is involved in any displayed vital.
const GOALS = { stepsGoal: 10000, caloriesGoal: 2000, sleepGoalHours: 8 };

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

const Index = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const live = useLiveTelemetry();
  const [simulating, setSimulating] = useState(false);

  // SINGLE SOURCE OF TRUTH: every vital + the chart come from `live`, which
  // polls the backend's Firebase-backed /api/vitals/* endpoints. There is no
  // in-browser simulator: when the bracelet stops, we keep showing the last
  // known reading and clearly mark it stale/disconnected.
  const live_t = live.data;
  const hasData = live_t != null;
  const tempC = live_t?.temperature_c ?? null;   // null → shown as "—"
  const heartRate = live_t?.heart_rate ?? 0;
  const spO2 = live_t?.spo2 ?? 0;
  const steps = live_t?.steps ?? 0;
  const calories = live_t?.calories ?? 0;
  const sleepSec = live_t?.sleep_duration_sec ?? 0;
  const sleep = secondsToTime(sleepSec);
  const battery = live_t?.battery_level ?? undefined;   // undefined when omitted
  const systolic = live_t?.systolic ?? null;
  const diastolic = live_t?.diastolic ?? null;
  const hasBp = systolic != null && diastolic != null;
  const fallDetected = live_t?.fall_alert === true;
  const offline = live.deviceStatus === "stale" ||
    live.deviceStatus === "disconnected" || live.source === "offline";
  const lastSeen = live.lastSeenSeconds;

  // Goals come from /users/{uid}/goals (NOT telemetry); fall back to defaults.
  const goals = {
    stepsGoal: live.goals?.steps ?? GOALS.stepsGoal,
    caloriesGoal: live.goals?.calories ?? GOALS.caloriesGoal,
    sleepGoalHours: live.goals?.sleep ?? GOALS.sleepGoalHours,
  };

  // Chart uses the SAME live history as the cards/Analytics — no second
  // simulator. Plot only real BPM; <2 points shows the "building" state.
  const validBpm = (n: number) => Number.isFinite(n) && n >= 20 && n <= 250;
  const chartHistory = live.history
    .filter(h => validBpm(h.heart_rate))
    .map(h => ({ heart_rate: h.heart_rate, timestamp: h.timestamp }));

  const name = user?.email ? user.email.split("@")[0].replace(/[._-]/g, " ") : "";

  const triggerSimulate = async (mode = "") => {
    setSimulating(true);
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user?.id || "demo-user-001", ...(mode ? { mode } : {}) }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok || !body?.ok) throw new Error(body?.error?.message || `HTTP ${res.status}`);
      const risk = body?.data?.analysis?.risk_level ?? "normal";
      toast({
        title: "New reading received",
        description: `Status: ${risk === "normal" ? "All good" : risk === "warning" ? "Watch" : "Needs attention"}.`,
      });
    } catch (e) {
      toast({
        title: "Couldn't reach the backend",
        description:
          "Start it with `python -m backend.app` (or `docker compose up`) and try again. The dashboard keeps working in demo mode.",
        variant: "destructive",
      });
      console.warn("[simulate] failed:", e);
    } finally {
      setSimulating(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Greeting + actions */}
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{greeting()}{name ? `, ${name}` : ""}</p>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Here's how you're doing today
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <TelemetrySourceBadge
            source={live.source}
            stale={live.stale}
            lastUpdate={live.lastUpdate}
            deviceStatus={live.deviceStatus}
            lastSeenSeconds={live.lastSeenSeconds}
          />
          {live.source === "firebase" && live.deviceStatus === "connected" && (
            <span className="inline-flex items-center rounded-full bg-emerald-600/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
              ● Live bracelet
            </span>
          )}
          {/* Simulator controls only exist in simulator/demo mode — in Firebase
              live mode the bracelet is the only source of readings. */}
          {live.simulatorEnabled ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" disabled={simulating} className="gap-2 shadow-sm">
                  <Zap className="h-4 w-4" />
                  {simulating ? "Sending…" : "New reading"}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuLabel>Simulate scenario</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {SIMULATOR_MODES.map(m => (
                  <DropdownMenuItem key={m.value || "random"} onClick={() => triggerSimulate(m.value)}>
                    {m.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <span className="inline-flex items-center rounded-full border border-border bg-muted/40 px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
              Simulator disabled · Firebase live mode
            </span>
          )}
        </div>
      </header>

      {/* Stale / disconnected banner — last known reading, clearly marked */}
      {offline && hasData && (
        <div className="flex items-center gap-3 rounded-2xl border border-health-warning/40 bg-health-warning/5 p-4">
          <WifiOff className="h-5 w-5 flex-shrink-0 text-health-warning" />
          <div>
            <p className="text-sm font-semibold text-foreground">
              {live.deviceStatus === "disconnected" || live.source === "offline"
                ? "Bracelet disconnected"
                : "Bracelet data is stale"}
            </p>
            <p className="text-xs text-muted-foreground">
              Showing your last known reading
              {typeof lastSeen === "number" ? ` from ${Math.round(lastSeen)}s ago` : ""}.
              No new values are being invented while the sensor is offline.
            </p>
          </div>
        </div>
      )}

      {/* Fall alert banner */}
      {fallDetected && (
        <div className="flex items-center gap-3 rounded-2xl border border-health-danger/40 bg-health-danger/5 p-4">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 text-health-danger" />
          <div>
            <p className="text-sm font-semibold text-health-danger">Fall detected</p>
            <p className="text-xs text-muted-foreground">
              The bracelet reported a fall. If you need help, contact someone now.
            </p>
          </div>
        </div>
      )}

      {/* Risk hero */}
      <RiskHeroCard telemetry={live_t} />

      {/* Activity + stress chips (deterministic, explainable signals) */}
      {(live_t?.activity || live_t?.stress_label) && (
        <div className="flex flex-wrap gap-2">
          {live_t?.activity && live_t.activity !== "unknown" && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium capitalize text-foreground">
              <Footprints className="h-3.5 w-3.5 text-primary" /> {live_t.activity}
            </span>
          )}
          {live_t?.stress_label && (
            <span className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium capitalize",
              live_t.stress_label === "stressed" ? "bg-health-warning/15 text-health-warning"
                : live_t.stress_label === "normal" ? "bg-secondary text-foreground"
                : "bg-health-normal/15 text-health-normal",
            )}>
              <Activity className="h-3.5 w-3.5" /> Stress: {live_t.stress_label}
              {typeof live_t.stress_score === "number" ? ` (${live_t.stress_score})` : ""}
            </span>
          )}
        </div>
      )}

      {/* Proactive assistant card for a NEW current alert (deduped, no spam) */}
      <ProactiveAlertCard alerts={live.alerts} />

      {/* Quiet alert summary strip */}
      <AlertSummary alerts={live.alerts} />

      {/* Metric grid (mobile-first 2-col → wide on large screens) */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-8">
        <MetricCard icon={Activity}    label="Heart Rate"  value={hasData ? Math.round(heartRate) : "—"}  unit={hasData ? "bpm" : ""} status={hasData ? classifyHeartRate(heartRate) : undefined} delay={0}   hint="Resting baseline" />
        <MetricCard icon={Thermometer} label="Temperature" value={tempC != null ? tempC.toFixed(1) : "—"} unit={tempC != null ? "°C" : ""} status={tempC != null ? classifyTemperature(tempC) : undefined} delay={50}  hint="Body temperature" />
        <MetricCard icon={Droplets}    label="SpO₂"        value={hasData ? Math.round(spO2) : "—"}       unit={hasData ? "%" : ""}   status={hasData ? classifySpO2(spO2) : undefined}     delay={100} hint="Blood oxygen" />
        {hasBp && (
          <MetricCard icon={HeartPulse} label="Blood Pressure" value={`${systolic}/${diastolic}`} unit="mmHg" delay={120} hint="Systolic / diastolic" />
        )}
        <MetricCard icon={Footprints}  label="Steps"       value={steps.toLocaleString()}                 unit=""      progress={(steps / goals.stepsGoal) * 100}     delay={150} hint={`Goal ${goals.stepsGoal.toLocaleString()}`} />
        <MetricCard icon={Flame}       label="Calories"    value={Math.round(calories)}                   unit="kcal"  progress={(calories / goals.caloriesGoal) * 100} delay={200} hint={`Goal ${goals.caloriesGoal.toLocaleString()}`} />
        <MetricCard icon={Moon}        label="Sleep"       value={`${sleep.hours}h ${sleep.minutes}m`}    unit=""      progress={(sleepSec / 3600 / goals.sleepGoalHours) * 100} delay={250} hint={`Goal ${goals.sleepGoalHours}h`} />
        {battery !== undefined && (
          <MetricCard icon={BatteryFull} label="Battery" value={Math.round(battery)} unit="%" status={classifyBattery(battery)} delay={300} hint="Bracelet charge" />
        )}
      </div>

      {/* Trained neural-network insight */}
      <ModelInsight riskLabel={live_t?.ml_risk_label} anomalyScore={live_t?.ml_anomaly_score} />

      {/* Chart + insights side-by-side on lg */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <VitalsChart history={chartHistory} title="Heart rate" subtitle="Last few minutes" />
        </div>
        <div>
          <HealthInsights telemetry={live_t} />
        </div>
      </div>
    </div>
  );
};

export default Index;
