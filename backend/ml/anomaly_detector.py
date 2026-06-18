"""
AnomalyDetector — bottleneck MLP autoencoder trained only on healthy
telemetry. Inference returns a reconstruction error; high error means the
reading is unusual relative to the training distribution.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import joblib
import numpy as np

logger = logging.getLogger("pulseguard.ml.anomaly")

FEATURES = ["heart_rate", "spo2", "temperature_c", "steps", "calories", "sleep_duration_sec"]


@dataclass
class AnomalyResult:
    score: float          # normalized 0..1 (higher = more anomalous)
    raw_error: float      # raw mean-squared reconstruction error
    is_anomaly: bool      # threshold-based flag
    latency_ms: int


class AnomalyDetector:
    """Inference wrapper. Threshold + scaler are bundled with the model."""

    def __init__(self,
                 model: Optional[Any] = None,
                 scaler: Optional[Any] = None,
                 threshold: Optional[float] = None,
                 metrics: Optional[dict] = None) -> None:
        self._model = model
        self._scaler = scaler
        self.threshold = threshold or 0.0
        self.metrics: Dict[str, Any] = metrics or {}
        self.status = "trained" if model is not None else "stub"

    @classmethod
    def load_or_stub(cls) -> "AnomalyDetector":
        from .registry import MODELS_DIR
        model_path = os.path.join(MODELS_DIR, "anomaly_autoencoder.joblib")
        metrics_path = os.path.join(MODELS_DIR, "anomaly_autoencoder_metrics.json")
        if not os.path.exists(model_path):
            logger.warning(
                "AnomalyDetector: %s not found — running in stub mode. "
                "Train with `python -m backend.ml.training.train_all`.",
                model_path,
            )
            return cls()
        try:
            bundle = joblib.load(model_path)
            metrics = {}
            if os.path.exists(metrics_path):
                with open(metrics_path, "r", encoding="utf-8") as f:
                    metrics = json.load(f)
            return cls(
                model=bundle["model"],
                scaler=bundle["scaler"],
                threshold=bundle["threshold"],
                metrics=metrics,
            )
        except Exception as exc:
            logger.warning("AnomalyDetector: failed to load (%s). Stub mode.", exc)
            return cls()

    # ------------------------------------------------------------------
    def score(self, vitals: Dict[str, Any]) -> Optional[AnomalyResult]:
        import time
        if self._model is None or self._scaler is None:
            return None
        try:
            row = np.asarray([[float(vitals.get(f, 0)) for f in FEATURES]], dtype=np.float32)
        except (TypeError, ValueError):
            return None
        start = time.time()
        scaled = self._scaler.transform(row)
        reconstructed = self._model.predict(scaled)
        if reconstructed.ndim == 1:
            reconstructed = reconstructed.reshape(scaled.shape)
        err = float(np.mean((scaled - reconstructed) ** 2))
        # Normalize against the threshold so the UI gets a 0..1 number.
        denom = max(self.threshold * 3.0, 1e-9)
        normalized = float(min(1.0, err / denom))
        latency_ms = int((time.time() - start) * 1000)
        return AnomalyResult(
            score=normalized,
            raw_error=err,
            is_anomaly=err > self.threshold,
            latency_ms=latency_ms,
        )

    def info(self) -> Dict[str, Any]:
        return {
            "name": "anomaly_autoencoder",
            "kind": "MLPRegressor (autoencoder)",
            "status": self.status,
            "threshold": self.threshold,
            "features": FEATURES,
            "metrics": self.metrics,
        }
