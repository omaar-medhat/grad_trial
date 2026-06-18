"""
Lazy loader for the trained ML models. The backend imports `get_models()`
once and caches it. If a model file is missing the wrapper falls back to a
no-op so the app still boots and tests still pass.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("pulseguard.ml")

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


@dataclass
class LoadedModels:
    risk: "RiskClassifier"
    anomaly: "AnomalyDetector"
    intent: "IntentClassifier"
    stress: "StressClassifier"


_lock = threading.Lock()
_models: Optional[LoadedModels] = None


def get_models() -> LoadedModels:
    global _models
    if _models is not None:
        return _models
    with _lock:
        if _models is not None:
            return _models
        from .risk_classifier import RiskClassifier
        from .anomaly_detector import AnomalyDetector
        from .intent_classifier import IntentClassifier
        from .stress_classifier import StressClassifier

        risk = RiskClassifier.load_or_stub()
        anomaly = AnomalyDetector.load_or_stub()
        intent = IntentClassifier.load_or_stub()
        stress = StressClassifier.load_or_stub()

        logger.info(
            "ML models loaded — risk=%s anomaly=%s intent=%s stress=%s",
            risk.status, anomaly.status, intent.status, stress.status,
        )
        _models = LoadedModels(
            risk=risk, anomaly=anomaly, intent=intent, stress=stress
        )
        return _models


def reset_for_tests():
    """Drop the cached models so tests can reload after retraining."""
    global _models
    with _lock:
        _models = None
