"""
Train the Anomaly Autoencoder.

Architecture (bottleneck autoencoder):
  Input (6 features, scaled) → MLP(4 → 2 → 4) → Output (6 features)

We train the MLPRegressor to reconstruct its own input from a 2-dimensional
bottleneck. Trained on healthy-only data, so the network has never seen
abnormal patterns — its reconstruction error spikes on them.

The detection threshold is set to the 99th percentile of training-set
reconstruction errors (a standard one-sided threshold for anomaly detection).
"""

from __future__ import annotations

import json
import os
import time

import joblib
import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .generate_dataset import (
    generate_healthy_only_dataset,
    generate_telemetry_dataset,
)
from ..registry import MODELS_DIR


def main(n_healthy: int = 20_000, seed: int = 7) -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)

    print(f"[anomaly] Generating {n_healthy} healthy-only samples for training...")
    X_train = generate_healthy_only_dataset(n=n_healthy, seed=seed)

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)

    print("[anomaly] Training bottleneck autoencoder MLP(4→2→4)...")
    model = MLPRegressor(
        hidden_layer_sizes=(4, 2, 4),
        activation="relu",
        solver="adam",
        alpha=1e-4,
        batch_size=256,
        learning_rate_init=1e-3,
        max_iter=300,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=10,
        random_state=seed,
        verbose=False,
    )
    t0 = time.time()
    model.fit(X_train_s, X_train_s)
    train_seconds = time.time() - t0

    # Threshold from training errors (99th percentile).
    train_recon = model.predict(X_train_s)
    if train_recon.ndim == 1:
        train_recon = train_recon.reshape(X_train_s.shape)
    train_err = np.mean((X_train_s - train_recon) ** 2, axis=1)
    threshold = float(np.percentile(train_err, 99))

    # Evaluate on a mixed dataset: rule-engine labels 0=normal, 1=warning, 2=high.
    # AUC: can the autoencoder separate normal vs non-normal?
    print("[anomaly] Evaluating on mixed dataset (normal vs not-normal)...")
    X_mix, y_mix, _, _ = generate_telemetry_dataset(n=10_000, seed=seed + 1)
    X_mix_s = scaler.transform(X_mix)
    mix_recon = model.predict(X_mix_s)
    if mix_recon.ndim == 1:
        mix_recon = mix_recon.reshape(X_mix_s.shape)
    mix_err = np.mean((X_mix_s - mix_recon) ** 2, axis=1)
    y_binary = (y_mix > 0).astype(int)  # 1 = warning/high
    try:
        auc = float(roc_auc_score(y_binary, mix_err))
    except Exception:
        auc = float("nan")
    flagged_rate = float((mix_err > threshold).mean())
    abnormal_caught = float(((mix_err > threshold) & (y_binary == 1)).sum() / max(1, y_binary.sum()))

    # Save bundle (model + scaler + threshold all together).
    bundle = {"model": model, "scaler": scaler, "threshold": threshold}
    model_path = os.path.join(MODELS_DIR, "anomaly_autoencoder.joblib")
    joblib.dump(bundle, model_path)

    metrics = {
        "model": "AnomalyAutoencoder",
        "architecture": "StandardScaler + MLP autoencoder (6→4→2→4→6)",
        "training_samples": int(X_train.shape[0]),
        "threshold_p99": round(threshold, 6),
        "train_seconds": round(train_seconds, 2),
        "n_iterations": int(model.n_iter_),
        "loss_curve_final": float(model.loss_curve_[-1]),
        "test": {
            "auc_normal_vs_abnormal": round(auc, 4),
            "flagged_rate_overall": round(flagged_rate, 4),
            "abnormal_recall_at_threshold": round(abnormal_caught, 4),
        },
    }
    with open(os.path.join(MODELS_DIR, "anomaly_autoencoder_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"[anomaly] ✓ saved -> {model_path}")
    print(f"[anomaly] ✓ AUC normal-vs-abnormal = {auc:.4f}  (trained in {train_seconds:.1f}s, {model.n_iter_} epochs)")
    return metrics


if __name__ == "__main__":
    main()
