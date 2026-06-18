/**
 * VitalsChart
 * -----------
 * Single elegant area chart of recent heart-rate history. Plain title, no
 * units in the chart itself (already shown on the axis), no jargon.
 * Falls back to a calm empty state when no history yet.
 */
import { Activity } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

interface Props {
  history: { heart_rate: number; timestamp: number }[];
  title?: string;
  subtitle?: string;
}

export function VitalsChart({ history, title = "Heart rate", subtitle = "Recent trend" }: Props) {
  const data = history.map((h, i) => ({
    i,
    hr: h.heart_rate,
    time: new Date(h.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  }));

  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      <header className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
            <Activity className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">{title}</h3>
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          </div>
        </div>
        <span className="rounded-full bg-secondary px-2.5 py-0.5 text-[10px] font-medium text-secondary-foreground">
          last {data.length} points
        </span>
      </header>

      {data.length < 2 ? (
        <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
          Building your trend — a few more readings and the line will appear here.
        </div>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="hr-gradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"  stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="i" hide />
              <YAxis
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                width={36}
                domain={["dataMin - 5", "dataMax + 5"]}
              />
              <Tooltip
                cursor={{ stroke: "hsl(var(--primary))", strokeOpacity: 0.2 }}
                contentStyle={{
                  background: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 10,
                  fontSize: 12,
                  boxShadow: "var(--shadow-card-hover)",
                }}
                formatter={(value: number) => [`${Math.round(value)} bpm`, "Heart rate"]}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.time ?? ""}
              />
              <Area
                type="monotone"
                dataKey="hr"
                stroke="hsl(var(--primary))"
                strokeWidth={2.5}
                fill="url(#hr-gradient)"
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
