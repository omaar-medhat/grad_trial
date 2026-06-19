"""
StressClassifier — serves the current WESAD stress model package (DeepDNN).

The deployed model is the self-contained package at
`backend/models/wesad_vscode_model_package/` (DeepDNN + preprocessor, selected
by a 15-model bake-off on the WESAD dataset). This module wraps that package's
`WESADStressPredictor` (in its `inference.py`) behind a small backend-friendly
API:

  * `StressClassifier`               — class: `.load_or_stub()`, `.predict()`,
                                       `.info()`, `.status`, `.feature_names`…
  * `stress_classifier`              — module singleton (a StressClassifier)
  * `predict_stress(features)->dict` — one-call inference

Loading is LAZY and path-robust (`Path(__file__).resolve()`): the heavy deps
(tensorflow/pandas) and the model itself are only loaded on the first
prediction, so importing this module — or booting the Flask app — never pulls
in tensorflow. Lightweight metadata (feature names, label mapping, threshold)
is read straight from the package JSON without loading the model.

NOT a medical diagnosis.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pulseguard.ml.stress")


# ===================================================================
# WESAD VS Code model package resolution + lazy loader.
#
# The package directory is resolved from this file's location across the two
# layouts it may ship in (backend/models/... and backend/ml/models/...),
# preferring whichever exists, with an optional WESAD_PACKAGE_DIR env override.
# ===================================================================
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend
_ML_DIR = Path(__file__).resolve().parent              # .../backend/ml

_WESAD_PACKAGE_CANDIDATES = (
    _BACKEND_DIR / "models" / "wesad_vscode_model_package",
    _ML_DIR / "models" / "wesad_vscode_model_package",
)


def _resolve_wesad_package_dir() -> Path:
    override = os.environ.get("WESAD_PACKAGE_DIR")
    if override:
        return Path(override)
    for candidate in _WESAD_PACKAGE_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return _WESAD_PACKAGE_CANDIDATES[0]


WESAD_PACKAGE_DIR = _resolve_wesad_package_dir()

# Files the package must contain to be usable.
_REQUIRED_PACKAGE_FILES = (
    "inference.py",
    "metadata.json",
    "feature_names.json",
    "sample_input.json",
    "models/model_spec.json",
)

_package_lock = threading.Lock()
_package_predictor: Optional[Any] = None  # cached WESADStressPredictor


def missing_package_files(package_dir: Optional[Any] = None) -> List[str]:
    """Return the list of required files that are missing from the package."""
    pkg = Path(package_dir) if package_dir else WESAD_PACKAGE_DIR
    return [rel for rel in _REQUIRED_PACKAGE_FILES if not (pkg / rel).exists()]


def _load_inference_module(package_dir: Path):
    """Import the package's inference.py by file path.

    The package has no __init__.py and is not on sys.path, so we load it
    directly from disk — this keeps it import-safe regardless of cwd.
    """
    inference_path = package_dir / "inference.py"
    spec = importlib.util.spec_from_file_location(
        "wesad_vscode_model_package.inference", inference_path
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Cannot build import spec for {inference_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_wesad_predictor(package_dir: Optional[Any] = None):
    """Lazily build (and cache) the package's WESADStressPredictor.

    Raises FileNotFoundError with a clear message if the package folder or
    any required file is missing, and RuntimeError if the model fails to load.
    """
    global _package_predictor
    use_cache = package_dir is None
    if use_cache and _package_predictor is not None:
        return _package_predictor

    with _package_lock:
        if use_cache and _package_predictor is not None:
            return _package_predictor

        pkg = Path(package_dir) if package_dir else WESAD_PACKAGE_DIR
        if not pkg.is_dir():
            raise FileNotFoundError(
                f"WESAD model package not found at {pkg}. Expected the "
                f"unzipped 'wesad_vscode_model_package' folder under "
                f"backend/models/."
            )
        missing = missing_package_files(pkg)
        if missing:
            raise FileNotFoundError(
                "WESAD model package is incomplete — missing: "
                + ", ".join(missing)
                + f" (looked under {pkg})."
            )
        try:
            inference = _load_inference_module(pkg)
            predictor = inference.WESADStressPredictor(str(pkg))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Failed to load WESAD model package from {pkg}: {exc}"
            ) from exc

        logger.info(
            "WESAD package loaded (model=%s, %d features, threshold=%.3f)",
            predictor.model_name,
            len(predictor.feature_names),
            predictor.threshold,
        )
        if use_cache:
            _package_predictor = predictor
        return predictor


def predict_stress(features: Dict[str, Any]) -> Dict[str, Any]:
    """Predict binary stress from a WESAD feature dict.

    Backed by the bundled DeepDNN package. Returns a JSON-friendly dict with:
    prediction, prediction_id, stress_probability, non_stress_probability,
    confidence, threshold, model_name. Missing features are filled with 0.0
    by the package, so partial dicts are accepted.
    """
    if not isinstance(features, dict):
        raise TypeError("predict_stress expects a dict of WESAD features.")
    predictor = load_wesad_predictor()
    return predictor.predict_from_features(features)


# ===================================================================
# Backend-friendly classifier facade.
# ===================================================================
@dataclass
class StressPrediction:
    label: str
    confidence: float
    probabilities: Dict[str, float]
    model_name: str
    latency_ms: int


class StressClassifier:
    """Inference wrapper around the WESAD model package. Thread-safe.

    `.status` is "trained" when the package is present (no tensorflow needed to
    determine this) and "stub" otherwise. Lightweight metadata is read from the
    package JSON; the actual model loads lazily on the first `.predict()`.
    """

    def __init__(
        self,
        package_dir: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        self.package_dir = (
            Path(package_dir) if package_dir else WESAD_PACKAGE_DIR
        )
        self.error = error
        self.status = "trained" if error is None else "stub"
        self._meta: Optional[Dict[str, Any]] = None
        self._feature_names: Optional[List[str]] = None

    @classmethod
    def load_or_stub(cls) -> "StressClassifier":
        if not WESAD_PACKAGE_DIR.is_dir() or missing_package_files():
            missing = missing_package_files()
            msg = (
                f"WESAD model package not found or incomplete at "
                f"{WESAD_PACKAGE_DIR}"
                + (f" (missing: {', '.join(missing)})" if missing else "")
                + "."
            )
            logger.warning("StressClassifier: %s", msg)
            return cls(error=msg)
        logger.info(
            "StressClassifier: WESAD package available at %s",
            WESAD_PACKAGE_DIR,
        )
        return cls()

    # -- lightweight metadata (no tensorflow) --------------------------
    def _metadata(self) -> Dict[str, Any]:
        if self._meta is None:
            with open(
                self.package_dir / "metadata.json", encoding="utf-8"
            ) as f:
                self._meta = json.load(f)
        return self._meta

    @property
    def feature_names(self) -> List[str]:
        if self._feature_names is None:
            try:
                with open(
                    self.package_dir / "feature_names.json", encoding="utf-8"
                ) as f:
                    self._feature_names = json.load(f)
            except Exception:  # noqa: BLE001
                self._feature_names = []
        return self._feature_names

    @property
    def label_mapping(self) -> Dict[int, str]:
        try:
            mapping = self._metadata().get("label_mapping", {})
            return {int(k): v for k, v in mapping.items()}
        except Exception:  # noqa: BLE001
            return {}

    @property
    def model_name(self) -> str:
        try:
            return self._metadata().get("best_model_name", "DeepDNN")
        except Exception:  # noqa: BLE001
            return "unknown"

    @property
    def threshold(self) -> Optional[float]:
        try:
            return float(self._metadata().get("best_threshold"))
        except Exception:  # noqa: BLE001
            return None

    # -- inference -----------------------------------------------------
    def _to_features(
        self, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Accept a `{"vector": [...]}` (length-checked against feature_names)
        or a `{"features": {...}}` / raw feature dict, and return a feature
        dict for the package predictor."""
        if not isinstance(payload, dict):
            return None
        if isinstance(payload.get("vector"), list):
            vec = payload["vector"]
            names = self.feature_names
            if not names or len(vec) != len(names):
                return None
            return {names[i]: vec[i] for i in range(len(names))}
        feats = payload.get("features", payload)
        if not isinstance(feats, dict) or not feats:
            return None
        return feats

    def predict(self, payload: Dict[str, Any]) -> Optional[StressPrediction]:
        if self.status != "trained":
            return None
        feats = self._to_features(payload or {})
        if feats is None:
            return None
        start = time.time()
        try:
            res = predict_stress(feats)
        except Exception as exc:  # noqa: BLE001
            logger.warning("StressClassifier: predict failed (%s)", exc)
            return None
        latency_ms = int((time.time() - start) * 1000)
        probs: Dict[str, float] = {}
        if res.get("non_stress_probability") is not None:
            probs["non_stress"] = float(res["non_stress_probability"])
        if res.get("stress_probability") is not None:
            probs["stress"] = float(res["stress_probability"])
        conf = res.get("confidence")
        return StressPrediction(
            label=res.get("prediction", ""),
            confidence=float(conf) if conf is not None else 0.0,
            probabilities=probs,
            model_name=res.get("model_name", self.model_name),
            latency_ms=latency_ms,
        )

    def predict_stress(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Direct dict-in/dict-out inference (mirrors the module function)."""
        return predict_stress(features)

    def info(self) -> Dict[str, Any]:
        missing = missing_package_files(self.package_dir)
        info: Dict[str, Any] = {
            "name": "stress_classifier",
            "kind": "WESAD package (DeepDNN + preprocessor)",
            "status": self.status,
            "package_dir": str(self.package_dir),
            "available": self.status == "trained" and not missing,
            "missing_files": missing,
            "error": self.error,
            "loaded": _package_predictor is not None,
        }
        if self.status == "trained":
            try:
                info.update(
                    model_name=self.model_name,
                    threshold=self.threshold,
                    n_features=len(self.feature_names),
                    classes=[
                        self.label_mapping[k]
                        for k in sorted(self.label_mapping)
                    ],
                )
            except Exception:  # noqa: BLE001
                pass
        return info


# Module-level singleton expected by the backend-friendly API.
stress_classifier = StressClassifier.load_or_stub()
