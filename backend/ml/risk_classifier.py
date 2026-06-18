"""
RiskClassifier — MLP that predicts {normal, warning, high} from 6 vitals.

The model is a feed-forward neural network (sklearn `MLPClassifier`) with
three hidden ReLU layers and a softmax output. It is trained on a labeled
synthetic dataset where labels come from the production rule engine — a
classic knowledge-distillation setup that makes the network's behaviour
auditable against the rules.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import joblib
import numpy as np

logger = logging.getLogger("pulseguard.ml.risk")

FEATURES = ["heart_rate", "spo2", "temperature_c", "steps", "calories", "sleep_duration_sec"]
CLASSES = ["normal", "warning", "high"]


@dataclass
class RiskPrediction:
    label: str
    confidence: float
    probabilities: Dict[str, float]
    latency_ms: int


class RiskClassifier:
    """Inference wrapper around the trained MLP. Thread-safe."""

    def __init__(self, pipeline: Optional[Any] = None, metrics: Optional[dict] = None) -> None:
        self._pipeline = pipeline
        self.metrics: Dict[str, Any] = metrics or {}
        self.status = "trained" if pipeline is not None else "stub"

    @classmethod
    def load_or_stub(cls) -> "RiskClassifier":
        from .registry import MODELS_DIR
        model_path = os.path.join(MODELS_DIR, "risk_classifier.joblib")
        metrics_path = os.path.join(MODELS_DIR, "risk_classifier_metrics.json")
        if not os.path.exists(model_path):
            logger.warning(
                "RiskClassifier: %s not found — running in stub mode. "
                "Train with `python -m backend.ml.training.train_all`.",
                model_path,
            )
            return cls()
        try:
            pipeline = joblib.load(model_path)
            metrics = {}
            if os.path.exists(metrics_path):
                with open(metrics_path, "r", encoding="utf-8") as f:
                    metrics = json.load(f)
            return cls(pipeline=pipeline, metrics=metrics)
        except Exception as exc:
            logger.warning("RiskClassifier: failed to load (%s). Stub mode.", exc)
            return cls()

    # ------------------------------------------------------------------
    def predict(self, vitals: Dict[str, Any]) -> Optional[RiskPrediction]:
        import time
        if self._pipeline is None:
            return None
        try:
            row = np.asarray([[float(vitals.get(f, 0)) for f in FEATURES]], dtype=np.float32)
        except (TypeError, ValueError):
            return None
        start = time.time()
        probs = self._pipeline.predict_proba(row)[0]
        latency_ms = int((time.time() - start) * 1000)
        idx = int(np.argmax(probs))
        return RiskPrediction(
            label=CLASSES[idx],
            confidence=float(probs[idx]),
            probabilities={c: float(p) for c, p in zip(CLASSES, probs)},
            latency_ms=latency_ms,
        )

    def info(self) -> Dict[str, Any]:
        return {
            "name": "risk_classifier",
            "kind": "MLPClassifier",
            "status": self.status,
            "features": FEATURES,
            "classes": CLASSES,
            "metrics": self.metrics,
        }
