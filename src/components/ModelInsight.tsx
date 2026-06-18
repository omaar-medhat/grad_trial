/**
 * ModelInsight
 * ------------
 * Shows the output of the *trained neural networks* (RiskClassifier MLP +
 * AnomalyAutoencoder) for the latest reading. Polls `/api/latest` —
 * `ml_risk_label` and `ml_anomaly_score` are persisted alongside each
 * reading by the backend.
 *
 * Plain language for the user; the metadata tags (architecture, accuracy)
 * make the AI pedigree obvious without showing equations.
 */
import { useEffect, useState } from "react";
import { Brain, Activity, Sparkles, AlertTriangle, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModelInfo {
  name: string;
  kind: string;
  status: string;
  metrics: {
    test_accuracy?: number;
    test?: { auc_normal_vs_abnormal?: number };
  };
}

interface ModelsResp {
  ok: boolean;
  data: {
    risk_classifier: ModelInfo;
    anomaly_autoencoder: ModelInfo;
    intent_classifier: ModelInfo;
  };
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

interface Props {
  riskLabel?: "normal" | "warning" | "high";
  anomalyScore?: number;
}

const riskTone = {
  normal:  { bg: "bg-health-normal/10", fg: "text-health-normal", icon: ShieldCheck, label: "Healthy" },
  warning: { bg: "bg-health-warning/10", fg: "text-health-warning", icon: AlertTriangle, label: "Watch" },
  high:    { bg: "bg-health-danger/10", fg: "text-health-danger", icon: AlertTriangle, label: "High Risk" },
} as const;

export function ModelInsight({ riskLabel, anomalyScore }: Props) {
  const [info, setInfo] = useState<ModelsResp["data"] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/models`)
      .then(r => r.json())
      .then((d: ModelsResp) => { if (!cancelled && d?.ok) setInfo(d.data); })
      .catch(() => { /* models endpoint not available — silent */ });
    return () => { cancelled = true; };
  }, []);

  const risk = riskLabel ?? "normal";
  const tone = riskTone[risk];
  const RiskIcon = tone.icon;

  const anomalyPct = anomalyScore !== undefined
    ? Math.min(100, Math.round(anomalyScore * 100))
    : null;
  const anomalyBadge =
    anomalyPct === null ? "—" :
    anomalyPct >= 60 ? "Unusual" :
    anomalyPct >= 30 ? "Borderline" :
    "Typical";

  const riskAcc = info?.risk_classifier?.metrics?.test_accuracy;
  const anomalyAuc = info?.anomaly_autoencoder?.metrics?.test?.auc_normal_vs_abnormal;

  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      <header className="mb-4 flex items-center gap-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent">
          <Brain className="h-4 w-4 text-primary-foreground" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-foreground">Neural network insight</h3>
          <p className="text-xs text-muted-foreground">
            Two trained models analysing your reading in parallel
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {/* Risk Classifier card */}
        <div className={cn("rounded-xl border border-border p-3", tone.bg)}>
          <div className="flex items-center gap-2">
            <Sparkles className={cn("h-4 w-4", tone.fg)} />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Risk Classifier
            </span>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <RiskIcon className={cn("h-5 w-5", tone.fg)} />
            <span className={cn("text-xl font-bold", tone.fg)}>{tone.label}</span>
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            MLP (64→32→16, ReLU)
            {riskAcc !== undefined && (
              <> · trained at {(riskAcc * 100).toFixed(1)}% accuracy</>
            )}
          </p>
        </div>

        {/* Anomaly Autoencoder card */}
        <div className="rounded-xl border border-border p-3 bg-secondary/40">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Anomaly Detector
            </span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-xl font-bold tabular-nums text-foreground">
              {anomalyPct !== null ? `${anomalyPct}%` : "—"}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase",
                anomalyPct === null ? "bg-secondary text-muted-foreground" :
                anomalyPct >= 60 ? "bg-health-danger/15 text-health-danger" :
                anomalyPct >= 30 ? "bg-health-warning/15 text-health-warning" :
                "bg-health-normal/15 text-health-normal"
              )}
            >
              {anomalyBadge}
            </span>
          </div>
          <div className="mt-2 h-1.5 w-full rounded-full bg-secondary">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                anomalyPct === null ? "bg-muted-foreground" :
                anomalyPct >= 60 ? "bg-health-danger" :
                anomalyPct >= 30 ? "bg-health-warning" :
                "bg-health-normal"
              )}
              style={{ width: `${anomalyPct ?? 0}%` }}
            />
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Bottleneck autoencoder (6→4→2→4→6)
            {anomalyAuc !== undefined && (
              <> · AUC {anomalyAuc.toFixed(2)}</>
            )}
          </p>
        </div>
      </div>
    </section>
  );
}
