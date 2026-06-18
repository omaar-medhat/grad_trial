import { useMemo, useState } from "react";
import { Download, FileText, Loader2 } from "lucide-react";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { useAuth } from "@/hooks/useAuth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, LineChart, Line,
} from "recharts";
import { TelemetrySourceBadge } from "@/components/TelemetrySourceBadge";

interface Point {
  time: number;
  heartRate: number;
  temperature: number;
  spO2: number;
  steps: number;
  calories: number;
  activity: number;
}

type Range = 15 | 60 | 240 | 0;

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

interface ReportData {
  available?: boolean;
  period: string;
  count: number;
  summary: string;
  source?: string;
  heart_rate?: { avg: number; min: number; max: number };
  spo2?: { avg: number; min: number; max: number };
  temperature_c?: { avg: number; min: number; max: number };
  blood_pressure?: {
    systolic?: { avg: number; min: number; max: number } | null;
    diastolic?: { avg: number; min: number; max: number } | null;
  } | null;
  steps_total?: number;
  sleep_hours?: number | null;
  fall_events?: number;
  disclaimer?: string;
  // legacy weekly report fields
  wellness_avg?: number | null;
  steps_taken?: number;
  alerts_total?: number;
  alerts_high?: number;
}

const Analytics = () => {
  const live = useLiveTelemetry();
  const { user } = useAuth();
  const uid = user?.id || "demo-user-001";
  const [range, setRange] = useState<Range>(60);
  const [report, setReport] = useState<ReportData | null>(null);
  const [reportLoading, setReportLoading] = useState<"daily" | "weekly" | null>(null);
  const [reportError, setReportError] = useState(false);

  const loadReport = async (period: "daily" | "weekly") => {
    setReportLoading(period);
    setReportError(false);
    try {
      const res = await fetch(`${API_BASE}/reports/${period}?uid=${encodeURIComponent(uid)}`);
      const body = await res.json();
      if (body?.ok) setReport(body.data as ReportData);
      else setReportError(true);
    } catch {
      setReportError(true);
    } finally {
      setReportLoading(null);
    }
  };

  const exportCsv = () => {
    // Trigger a direct download (the endpoint sets Content-Disposition) instead
    // of window.open, which left a stray blank tab behind.
    const a = document.createElement("a");
    a.href = `${API_BASE}/reports/export.csv?uid=${encodeURIComponent(uid)}`;
    a.download = `pulseguard_${uid}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const usingLive = live.history.length > 0;

  // Single source of truth: charts use the SAME live history as the dashboard
  // cards. Only valid BPM is plotted; no in-browser-simulator fallback (which
  // would disagree with the dashboard/backend).
  const allData: Point[] = useMemo(() => {
    return live.history
      .filter(h => Number.isFinite(h.heart_rate) && h.heart_rate >= 20 && h.heart_rate <= 250)
      .map((h, i) => ({
        time: i,
        heartRate: h.heart_rate,
        temperature: h.temperature_c,
        spO2: h.spo2,
        steps: h.steps,
        calories: h.calories,
        activity: h.activity_level ?? 0,
      }));
  }, [live.history]);

  const chartData = range === 0 ? allData : allData.slice(-range);

  const avg = (key: keyof Point) =>
    chartData.length ? chartData.reduce((s, p) => s + (p[key] as number), 0) / chartData.length : 0;
  const min = (key: keyof Point) =>
    chartData.length ? Math.min(...chartData.map(p => p[key] as number)) : 0;
  const max = (key: keyof Point) =>
    chartData.length ? Math.max(...chartData.map(p => p[key] as number)) : 0;

  const summary = [
    { label: "Avg HR",   value: `${Math.round(avg("heartRate"))} bpm` },
    { label: "Min HR",   value: `${Math.round(min("heartRate"))} bpm` },
    { label: "Max HR",   value: `${Math.round(max("heartRate"))} bpm` },
    { label: "Avg Temp", value: `${avg("temperature").toFixed(1)} °C` },
    { label: "Avg SpO₂", value: `${Math.round(avg("spO2"))} %` },
  ];

  const tooltipStyle = {
    background: "hsl(var(--card))",
    border: "1px solid hsl(var(--border))",
    borderRadius: 10,
    fontSize: 12,
    boxShadow: "var(--shadow-card-hover)",
  };

  const rangeButtons: { value: Range; label: string }[] = [
    { value: 15,  label: "Recent" },
    { value: 60,  label: "Hour" },
    { value: 240, label: "Today" },
    { value: 0,   label: "All" },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Analytics</h1>
          <p className="text-sm text-muted-foreground">
            {usingLive ? "Trends from your live Firebase readings" : "Waiting for live Firebase history…"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <TelemetrySourceBadge source={live.source} stale={live.stale} lastUpdate={live.lastUpdate} deviceStatus={live.deviceStatus} lastSeenSeconds={live.lastSeenSeconds} />
          <Badge variant="outline" className="text-[11px]">{chartData.length} points</Badge>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        {rangeButtons.map(r => (
          <Button
            key={r.value}
            size="sm"
            variant={range === r.value ? "default" : "outline"}
            onClick={() => setRange(r.value)}
            className="h-8 px-3 text-xs"
          >
            {r.label}
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {summary.map(s => (
          <Card key={s.label} className="border-border/60">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className="mt-1 text-xl font-bold tabular-nums text-foreground">{s.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Reports & export */}
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
          <CardTitle className="text-base">Reports &amp; export</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => loadReport("daily")} disabled={reportLoading !== null}>
              {reportLoading === "daily" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />} Daily
            </Button>
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => loadReport("weekly")} disabled={reportLoading !== null}>
              {reportLoading === "weekly" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />} Weekly
            </Button>
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={exportCsv}>
              <Download className="h-3.5 w-3.5" /> CSV
            </Button>
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => window.print()}>
              <FileText className="h-3.5 w-3.5" /> PDF
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {reportError ? (
            <p className="text-sm text-muted-foreground">
              Couldn't reach the backend for reports. Start it with <code>python -m backend.app</code> (reports read from stored history).
            </p>
          ) : report && report.available === false ? (
            <p className="text-sm text-muted-foreground">{report.summary}</p>
          ) : report ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary" className="capitalize">{report.period}</Badge>
                <Badge variant="outline">{report.count} readings</Badge>
                {report.source && <Badge variant="outline" className="capitalize">{report.source} data</Badge>}
                {report.heart_rate && <Badge variant="outline">Avg HR {report.heart_rate.avg} bpm</Badge>}
                {report.spo2 && <Badge variant="outline">Avg SpO₂ {report.spo2.avg}%</Badge>}
                {report.temperature_c && <Badge variant="outline">Avg Temp {report.temperature_c.avg}°C</Badge>}
                {report.blood_pressure?.systolic && report.blood_pressure?.diastolic && (
                  <Badge variant="outline">BP {report.blood_pressure.systolic.avg}/{report.blood_pressure.diastolic.avg}</Badge>
                )}
                {typeof report.wellness_avg === "number" && <Badge variant="outline">Wellness {report.wellness_avg}/100</Badge>}
                {typeof report.steps_total === "number" && <Badge variant="outline">{report.steps_total.toLocaleString()} steps</Badge>}
                {typeof report.steps_taken === "number" && <Badge variant="outline">{report.steps_taken} steps</Badge>}
                {typeof report.sleep_hours === "number" && <Badge variant="outline">{report.sleep_hours}h sleep</Badge>}
                {typeof report.fall_events === "number" && report.fall_events > 0 && (
                  <Badge className="bg-health-danger text-white">{report.fall_events} fall event{report.fall_events === 1 ? "" : "s"}</Badge>
                )}
                {typeof report.alerts_high === "number" && report.alerts_high > 0 && (
                  <Badge className="bg-health-danger text-white">{report.alerts_high} high alert{report.alerts_high === 1 ? "" : "s"}</Badge>
                )}
              </div>
              <p className="text-sm leading-relaxed text-foreground/80">{report.summary}</p>
              {report.disclaimer && <p className="text-xs text-muted-foreground">{report.disclaimer}</p>}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Generate a <strong>Daily</strong> or <strong>Weekly</strong> summary, download your readings as <strong>CSV</strong>, or save this page as a <strong>PDF</strong>.
            </p>
          )}
        </CardContent>
      </Card>

      <Tabs defaultValue="heart_rate" className="space-y-3">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="heart_rate">Heart Rate</TabsTrigger>
          <TabsTrigger value="temperature">Temperature</TabsTrigger>
          <TabsTrigger value="spo2">SpO₂</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="heart_rate">
          <Card>
            <CardHeader><CardTitle className="text-base">Heart Rate</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="hr" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="hsl(var(--health-danger))" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="hsl(var(--health-danger))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${Math.round(v)} bpm`, "Heart rate"]} />
                  <Area type="monotone" dataKey="heartRate" stroke="hsl(var(--health-danger))" fill="url(#hr)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="temperature">
          <Card>
            <CardHeader><CardTitle className="text-base">Temperature</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis domain={[35, 40]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${v.toFixed(1)} °C`, "Temp"]} />
                  <Line type="monotone" dataKey="temperature" stroke="hsl(var(--health-warning))" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="spo2">
          <Card>
            <CardHeader><CardTitle className="text-base">SpO₂</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="spo" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"  stopColor="hsl(var(--health-info))" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="hsl(var(--health-info))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis domain={[85, 100]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${Math.round(v)}%`, "SpO₂"]} />
                  <Area type="monotone" dataKey="spO2" stroke="hsl(var(--health-info))" fill="url(#spo)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="activity">
          <Card>
            <CardHeader><CardTitle className="text-base">Activity</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="activity" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Analytics;
