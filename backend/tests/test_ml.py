"""Tests for the trained ML models."""

from __future__ import annotations

import os

import pytest

from backend.ml import MODELS_DIR
from backend.ml import stress_classifier as stress_mod
from backend.ml.anomaly_detector import AnomalyDetector
from backend.ml.intent_classifier import IntentClassifier
from backend.ml.risk_classifier import RiskClassifier
from backend.ml.stress_classifier import StressClassifier

MODELS_TRAINED = os.path.exists(
    os.path.join(MODELS_DIR, "risk_classifier.joblib")
)
needs_models = pytest.mark.skipif(
    not MODELS_TRAINED,
    reason="Run `python -m backend.ml.training.train_all` first",
)


# -----------------------------------------------------------------
# WESAD stress model — served by the package at
# backend/models/wesad_vscode_model_package/ (DeepDNN). The legacy
# wesad_stress_artifact.pkl path was removed.
# -----------------------------------------------------------------
WESAD_PACKAGE_OK = (
    stress_mod.WESAD_PACKAGE_DIR.is_dir()
    and not stress_mod.missing_package_files()
)
needs_wesad_pkg = pytest.mark.skipif(
    not WESAD_PACKAGE_OK,
    reason="WESAD model package not present in backend/models/.",
)


def _tensorflow_available() -> bool:
    try:
        import tensorflow  # noqa: F401
    except Exception:
        return False
    return True


def test_stress_classifier_stub_when_package_missing(tmp_path, monkeypatch):
    # Point the package dir at an empty folder -> the model is unavailable.
    monkeypatch.setattr(stress_mod, "WESAD_PACKAGE_DIR", tmp_path)
    clf = StressClassifier.load_or_stub()
    assert clf.status == "stub"
    assert clf.error is not None  # clear message when the package is missing
    assert clf.predict({"vector": [0.0]}) is None


@needs_wesad_pkg
def test_stress_classifier_available_when_package_present():
    clf = StressClassifier.load_or_stub()
    assert clf.status == "trained"
    assert len(clf.feature_names) == 252
    assert set(clf.label_mapping.values()) == {"non_stress", "stress"}
    assert clf.model_name == "DeepDNN"


@needs_wesad_pkg
def test_stress_classifier_rejects_wrong_length_vector():
    # Length check happens before the model loads — no tensorflow needed.
    clf = StressClassifier.load_or_stub()
    assert clf.predict({"vector": [0.0, 1.0, 2.0]}) is None


@pytest.mark.skipif(
    not (WESAD_PACKAGE_OK and _tensorflow_available()),
    reason="WESAD package or its runtime (tensorflow) is not installed.",
)
def test_stress_classifier_predicts_from_vector():
    clf = StressClassifier.load_or_stub()
    pred = clf.predict({"vector": [0.0] * len(clf.feature_names)})
    assert pred is not None
    assert pred.label in clf.label_mapping.values()
    assert 0.0 <= pred.confidence <= 1.0
    assert set(pred.probabilities) == set(clf.label_mapping.values())
    assert pred.model_name == "DeepDNN"


def test_risk_classifier_stub_returns_none_when_unloaded(tmp_path, monkeypatch):
    # Force a model load from a fresh path so it stays a stub.
    from backend.ml import registry
    monkeypatch.setattr(registry, "MODELS_DIR", str(tmp_path))
    clf = RiskClassifier.load_or_stub()
    assert clf.status == "stub"
    assert clf.predict({"heart_rate": 72}) is None


def test_anomaly_detector_stub_returns_none(tmp_path, monkeypatch):
    from backend.ml import registry
    monkeypatch.setattr(registry, "MODELS_DIR", str(tmp_path))
    det = AnomalyDetector.load_or_stub()
    assert det.status == "stub"
    assert det.score({"heart_rate": 72}) is None


def test_intent_classifier_stub_returns_none(tmp_path, monkeypatch):
    from backend.ml import registry
    monkeypatch.setattr(registry, "MODELS_DIR", str(tmp_path))
    clf = IntentClassifier.load_or_stub()
    assert clf.status == "stub"
    assert clf.predict("hi") is None


# -----------------------------------------------------------------
# Inference tests (require trained models).
# -----------------------------------------------------------------
@needs_models
def test_risk_classifier_normal_reading():
    clf = RiskClassifier.load_or_stub()
    assert clf.status == "trained"
    pred = clf.predict({
        "heart_rate": 72, "spo2": 97, "temperature_c": 36.7,
        "steps": 3500, "calories": 250, "sleep_duration_sec": 25200,
    })
    assert pred is not None
    assert pred.label == "normal"
    assert pred.confidence > 0.5
    probs = pred.probabilities
    assert abs(sum(probs.values()) - 1.0) < 0.01


@needs_models
def test_risk_classifier_high_risk_reading():
    clf = RiskClassifier.load_or_stub()
    pred = clf.predict({
        "heart_rate": 165, "spo2": 86, "temperature_c": 39.5,
        "steps": 0, "calories": 0, "sleep_duration_sec": 10000,
    })
    assert pred.label == "high"
    assert pred.confidence > 0.6


@needs_models
def test_anomaly_detector_low_score_for_healthy():
    det = AnomalyDetector.load_or_stub()
    res = det.score({
        "heart_rate": 72, "spo2": 97, "temperature_c": 36.7,
        "steps": 3500, "calories": 250, "sleep_duration_sec": 25200,
    })
    assert res is not None
    assert res.score < 0.5


@needs_models
def test_anomaly_detector_high_score_for_abnormal():
    det = AnomalyDetector.load_or_stub()
    res = det.score({
        "heart_rate": 180, "spo2": 80, "temperature_c": 40.5,
        "steps": 0, "calories": 0, "sleep_duration_sec": 3600,
    })
    assert res.score > 0.3
    assert res.is_anomaly is True


@needs_models
def test_intent_classifier_status_check():
    clf = IntentClassifier.load_or_stub()
    pred = clf.predict("how am i doing?")
    assert pred is not None
    assert pred.label == "status_check"
    assert pred.confidence > 0.3


@needs_models
def test_intent_classifier_symptom():
    clf = IntentClassifier.load_or_stub()
    pred = clf.predict("i feel dizzy")
    assert pred.label == "symptom_query"


@needs_models
def test_intent_classifier_tip_request():
    clf = IntentClassifier.load_or_stub()
    pred = clf.predict("any tips for better sleep")
    assert pred.label == "tip_request"


@needs_models
def test_intent_classifier_emergency():
    clf = IntentClassifier.load_or_stub()
    pred = clf.predict("i think i'm having a heart attack")
    assert pred.label == "emergency"


@needs_models
def test_models_endpoint_returns_metrics(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "risk_classifier" in body["data"]
    assert "anomaly_autoencoder" in body["data"]
    assert "intent_classifier" in body["data"]
    risk_info = body["data"]["risk_classifier"]
    assert risk_info["status"] == "trained"
    # Metrics are bundled in the JSON next to the model.
    assert "test_accuracy" in risk_info["metrics"]


@needs_models
def test_telemetry_response_includes_ml_section(client):
    r = client.post("/api/telemetry", json={
        "user_id": "ml-test-user",
        "heart_rate": 72, "spo2": 97, "temperature_c": 36.7,
        "steps": 3500, "calories": 250, "sleep_duration_sec": 25200,
        "timestamp": 1779791421000,
    })
    assert r.status_code == 200
    analysis = r.get_json()["data"]["analysis"]
    assert "ml" in analysis
    assert "risk" in analysis["ml"]
    assert "anomaly" in analysis["ml"]
    assert analysis["ml"]["risk"]["label"] in ("normal", "warning", "high")
