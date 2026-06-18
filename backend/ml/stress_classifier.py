"""
StressClassifier — serves the fine-tuned WESAD stress model artifact.

Loads `backend/models/wesad_stress_artifact.pkl` (the author's trained model:
a sklearn Pipeline of imputer -> robust scaler -> classifier, selected from a
15-model bake-off on the WESAD dataset, with a leave-subjects-out split). The
artifact bundles the model, the 252 feature names (wrist BVP/EDA/TEMP/ACC +
chest ECG/EMG/EDA/ACC window features), the label mapping, and the full
comparison metrics.

Cross-version note: the artifact was trained on scikit-learn 1.6.1. To predict
under a newer scikit-learn, the imputer/scaler steps are re-fitted on a dummy
frame (so their private attributes exist for this version) and the TRAINED
parameters (statistics_/center_/scale_) are copied back — the model weights are
untouched. NOT a medical diagnosis.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

logger = logging.getLogger("pulseguard.ml.stress")

ARTIFACT_NAME = "wesad_stress_artifact.pkl"


@dataclass
class StressPrediction:
    label: str
    confidence: float
    probabilities: Dict[str, float]
    model_name: str
    latency_ms: int


def _repair_pipeline(pipe):
    """Re-fit imputer/scaler under the running sklearn, keep trained params."""
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import RobustScaler
        from sklearn.preprocessing import StandardScaler

        n = getattr(pipe, "n_features_in_", None)
        steps = getattr(pipe, "steps", [])
        if n is None and steps:
            n = getattr(steps[0][1], "n_features_in_", None)
        if not n:
            return pipe
        dummy = np.zeros((3, n))
        new_steps = []
        for name, est in steps:
            if isinstance(est, SimpleImputer):
                fresh = SimpleImputer(
                    strategy=getattr(est, "strategy", "median"),
                    missing_values=getattr(est, "missing_values", np.nan),
                ).fit(dummy)
                fresh.statistics_ = est.statistics_
                est = fresh
            elif isinstance(est, RobustScaler):
                fresh = RobustScaler(
                    with_centering=getattr(est, "with_centering", True),
                    with_scaling=getattr(est, "with_scaling", True),
                ).fit(dummy)
                fresh.center_ = getattr(est, "center_", None)
                fresh.scale_ = getattr(est, "scale_", None)
                est = fresh
            elif isinstance(est, StandardScaler):
                fresh = StandardScaler().fit(dummy)
                for attr in ("mean_", "scale_", "var_"):
                    if hasattr(est, attr):
                        setattr(fresh, attr, getattr(est, attr))
                est = fresh
            new_steps.append((name, est))
        pipe.steps = new_steps
        if hasattr(pipe, "named_steps"):
            for name, est in new_steps:
                pipe.named_steps[name] = est
    except Exception as exc:  # noqa: BLE001
        logger.warning("StressClassifier: pipeline repair skipped (%s)", exc)
    return pipe


class StressClassifier:
    """Inference wrapper around the WESAD stress artifact. Thread-safe."""

    def __init__(
        self,
        model: Optional[Any] = None,
        feature_names: Optional[List[str]] = None,
        label_mapping: Optional[Dict[str, str]] = None,
        model_name: str = "unknown",
        metrics: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        self._model = model
        self.feature_names: List[str] = feature_names or []
        self.label_mapping: Dict[int, str] = {
            int(k): v for k, v in (label_mapping or {}).items()
        }
        self.model_name = model_name
        self.metrics: Dict[str, Any] = metrics or {}
        self.error = error
        self.status = "trained" if model is not None else "stub"

    @classmethod
    def load_or_stub(cls) -> "StressClassifier":
        from .registry import MODELS_DIR
        path = os.path.join(MODELS_DIR, ARTIFACT_NAME)
        if not os.path.exists(path):
            msg = (
                f"Stress model artifact not found at {path}. Place "
                f"'{ARTIFACT_NAME}' in backend/models/."
            )
            logger.warning("StressClassifier: %s", msg)
            return cls(error=msg)
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                art = joblib.load(path)
            model = _repair_pipeline(art["model"])
            best = art.get("best_model_name", "unknown")
            clf = cls(
                model=model,
                feature_names=art.get("feature_names", []),
                label_mapping=art.get("label_mapping", {}),
                model_name=best,
                metrics={
                    "dataset": art.get("dataset"),
                    "task": art.get("task"),
                    "feature_mode": art.get("feature_mode"),
                    "split_mode": art.get("split_mode"),
                    "best_model_name": best,
                    "n_features": len(art.get("feature_names", [])),
                    "window_sec": art.get("window_sec"),
                    "step_sec": art.get("step_sec"),
                    "sampling_rates_wrist": art.get("sampling_rates_wrist"),
                    "sampling_rates_chest": art.get("sampling_rates_chest"),
                    "comparison": art.get("metrics", []),
                    "train_subjects": art.get("train_subjects"),
                    "test_subjects": art.get("test_subjects"),
                },
            )
            logger.info(
                "StressClassifier: loaded WESAD artifact (best=%s, %d features)",
                best, len(clf.feature_names),
            )
            return clf
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to load stress artifact: {exc}"
            logger.warning("StressClassifier: %s", msg)
            return cls(error=msg)

    # ------------------------------------------------------------------
    def _vectorize(self, payload: Dict[str, Any]) -> Optional[np.ndarray]:
        """Build the model input row from a features dict or a raw vector."""
        if isinstance(payload.get("vector"), list):
            vec = payload["vector"]
            if len(vec) != len(self.feature_names):
                return None
            return np.asarray([vec], dtype=np.float64)
        feats = payload.get("features", payload)
        if not isinstance(feats, dict):
            return None
        row = [
            float(feats[name]) if name in feats and feats[name] is not None
            else np.nan
            for name in self.feature_names
        ]
        # Need at least one real feature, otherwise it's not a WESAD window.
        if all(np.isnan(v) for v in row):
            return None
        return np.asarray([row], dtype=np.float64)

    def predict(self, payload: Dict[str, Any]) -> Optional[StressPrediction]:
        if self._model is None:
            return None
        row = self._vectorize(payload or {})
        if row is None:
            return None
        start = time.time()
        try:
            probs = self._model.predict_proba(row)[0]
            classes = list(self._model.classes_)
        except Exception as exc:  # noqa: BLE001
            logger.warning("StressClassifier: predict failed (%s)", exc)
            return None
        latency_ms = int((time.time() - start) * 1000)
        prob_map = {
            self.label_mapping.get(int(c), str(c)): float(p)
            for c, p in zip(classes, probs)
        }
        top = max(prob_map, key=prob_map.get)
        return StressPrediction(
            label=top,
            confidence=prob_map[top],
            probabilities=prob_map,
            model_name=self.model_name,
            latency_ms=latency_ms,
        )

    def info(self) -> Dict[str, Any]:
        return {
            "name": "stress_classifier",
            "kind": f"WESAD artifact ({self.model_name})",
            "status": self.status,
            "loaded": self._model is not None,
            "artifact": ARTIFACT_NAME,
            "model_name": self.model_name,
            "error": self.error,
            "classes": [self.label_mapping[k] for k in sorted(self.label_mapping)],
            "n_features": len(self.feature_names),
            "metrics": self.metrics,
        }
