"""
IntentClassifier — TF-IDF (char + word n-grams) → MLP. Replaces the
hand-written regex NLU in the chatbot for the production path. The
regex-based fallback in backend/assistant/nlu.py is still used as a
high-confidence override (emergency triggers, exact greetings) and as a
backup when the model isn't loaded.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

logger = logging.getLogger("pulseguard.ml.intent")

# Same intent labels used by the symbolic NLU.
CLASSES = (
    "emergency", "greeting", "thanks", "meta",
    "status_check", "metric_query", "symptom_query",
    "tip_request", "history_query", "compare_query",
    "smalltalk", "general_health", "fallback",
)


@dataclass
class IntentPrediction:
    label: str
    confidence: float
    probabilities: Dict[str, float]
    latency_ms: int


class IntentClassifier:
    def __init__(self, pipeline: Optional[Any] = None, metrics: Optional[dict] = None) -> None:
        self._pipeline = pipeline
        self.metrics: Dict[str, Any] = metrics or {}
        self.status = "trained" if pipeline is not None else "stub"

    @classmethod
    def load_or_stub(cls) -> "IntentClassifier":
        from .registry import MODELS_DIR
        model_path = os.path.join(MODELS_DIR, "intent_classifier.joblib")
        metrics_path = os.path.join(MODELS_DIR, "intent_classifier_metrics.json")
        if not os.path.exists(model_path):
            logger.warning(
                "IntentClassifier: %s not found — running in stub mode. "
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
            logger.warning("IntentClassifier: failed to load (%s). Stub mode.", exc)
            return cls()

    # ------------------------------------------------------------------
    def predict(self, message: str) -> Optional[IntentPrediction]:
        import time
        if self._pipeline is None or not message:
            return None
        start = time.time()
        try:
            probs = self._pipeline.predict_proba([message])[0]
            classes: List[str] = list(self._pipeline.classes_)
        except Exception:
            return None
        latency_ms = int((time.time() - start) * 1000)
        idx = int(np.argmax(probs))
        return IntentPrediction(
            label=classes[idx],
            confidence=float(probs[idx]),
            probabilities={c: float(p) for c, p in zip(classes, probs)},
            latency_ms=latency_ms,
        )

    def info(self) -> Dict[str, Any]:
        return {
            "name": "intent_classifier",
            "kind": "TF-IDF + MLPClassifier",
            "status": self.status,
            "classes": list(CLASSES),
            "metrics": self.metrics,
        }
