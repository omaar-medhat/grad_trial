"""Firebase-root-backed vitals/alerts/reports/device API tests.

These seed the RAW bracelet schema (temperature_f, numeric risk/stress,
systolic/diastolic, fall_alert) directly into the Firebase-service root node,
then assert the normalized contract the endpoints return.
"""

from __future__ import annotations

import time

import pytest

ACTIVE = "u1"


@pytest.fixture(autouse=True)
def _active_uid(monkeypatch):
    # All requests in this module resolve to the seeded user-scoped uid.
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", ACTIVE)


def _raw(**over):
    base = {
        "battery_level": 82, "calories": 0.48,
        "date_time": "2026-06-17 01:23:21", "diastolic": 80,
        "fall_alert": False, "heart_rate": 72, "risk_level": 1,
        "sleep_duration_sec": 28, "spo2": 98, "steps": 12,
        "stress_label": 1, "systolic": 120, "temperature_f": 98.6,
        "timestamp": int(time.time() * 1000),
    }
    base.update(over)
    return base


def _seed(app, latest=None, history=None):
    fb = app.config["FIREBASE"]
    if latest is not None:
        fb.write_latest(ACTIVE, latest)
    for h in history or []:
        fb.push_history(ACTIVE, h)


def test_vitals_latest_from_firebase_root(app, client):
    _seed(app, latest=_raw())
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["available"] is True
    assert d["source"] == "firebase" and d["is_simulated"] is False
    assert d["heart_rate"] == 72 and d["spo2"] == 98
    assert d["temperature_c"] == 37.0           # 98.6°F -> 37.0°C
    assert d["systolic"] == 120 and d["diastolic"] == 80
    assert d["fall_alert"] is False
    assert d["risk_level"] == "moderate" and d["raw_risk_level"] == 1
    assert d["stress_label"] == "normal" and d["raw_stress_label"] == 1
    assert d["device_status"] == "connected"


def test_vitals_latest_stale(app, client):
    old = int(time.time() * 1000) - 30 * 1000
    _seed(app, latest=_raw(timestamp=old))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["device_status"] == "stale"
    assert d["heart_rate"] == 72  # last known reading still shown


def test_vitals_latest_disconnected(app, client):
    old = int(time.time() * 1000) - 120 * 1000
    _seed(app, latest=_raw(timestamp=old))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["device_status"] == "disconnected"


def test_latest_missing_falls_back_to_last_history(app, client):
    now = int(time.time() * 1000)
    _seed(app, history=[
        _raw(heart_rate=70, timestamp=now - 4000),
        _raw(heart_rate=75, timestamp=now - 1000),
    ])
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["available"] is True
    assert d["heart_rate"] == 75  # most recent usable history record


def test_invalid_values_nulled(app, client):
    _seed(app, latest=_raw(heart_rate=500, spo2=20))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["heart_rate"] is None and d["spo2"] is None


def test_vitals_history_normalized(app, client):
    now = int(time.time() * 1000)
    _seed(app, history=[
        _raw(heart_rate=70, timestamp=now - 3000),
        _raw(heart_rate=80, timestamp=now - 1000),
    ])
    d = client.get("/api/vitals/history").get_json()["data"]
    assert d["source"] == "firebase" and d["count"] == 2
    assert d["readings"][0]["heart_rate"] == 70
    assert d["readings"][-1]["heart_rate"] == 80


def test_vitals_window_aggregates(app, client):
    now = int(time.time() * 1000)
    _seed(app, latest=_raw(heart_rate=72, timestamp=now), history=[
        _raw(heart_rate=70, timestamp=now - 5000),
        _raw(heart_rate=80, timestamp=now - 2000),
        _raw(heart_rate=72, timestamp=now),
    ])
    d = client.get("/api/vitals/window?seconds=60").get_json()["data"]
    assert d["count"] >= 3
    assert d["heart_rate"]["min"] <= 70 and d["heart_rate"]["max"] >= 80


def test_device_status_endpoint(app, client):
    _seed(app, latest=_raw())
    d = client.get("/api/device/status").get_json()["data"]
    assert d["device_status"] == "connected"
    assert d["source"] == "firebase"
    assert d["thresholds"]["connected_max_seconds"] == 15
    assert d["data_source_mode"] == "firebase"


def test_alerts_fall_is_current_critical(app, client):
    _seed(app, latest=_raw(fall_alert=True))
    body = client.get("/api/alerts").get_json()["data"]
    assert body["has_current_critical"] is True
    assert any(a["type"] == "fall" for a in body["current"])


def test_alerts_current_vs_history_separation(app, client):
    now = int(time.time() * 1000)
    # Current reading is healthy; history holds a past fever.
    _seed(app, latest=_raw(timestamp=now),
          history=[_raw(temperature_f=104.0, timestamp=now - 10_000)])
    body = client.get("/api/alerts").get_json()["data"]
    assert not any(a["type"] == "fever" for a in body["current"])
    assert any(a["type"] == "fever" for a in body["history"])


def test_alerts_abnormal_blood_pressure(app, client):
    _seed(app, latest=_raw(systolic=190, diastolic=125))
    body = client.get("/api/alerts").get_json()["data"]
    assert any(a["type"] == "blood_pressure" for a in body["current"])


def test_reports_daily_firebase_backed(app, client):
    now = int(time.time() * 1000)
    _seed(app, history=[
        _raw(heart_rate=70, timestamp=now),
        _raw(heart_rate=75, timestamp=now),
        _raw(heart_rate=80, timestamp=now),
    ])
    d = client.get("/api/reports/daily").get_json()["data"]
    assert d["available"] is True
    assert d["source"] == "firebase" and d["count"] == 3
    assert d["heart_rate"]["min"] <= 70 <= d["heart_rate"]["max"]
    assert d["blood_pressure"] is not None
    assert "diagnosis" in d["disclaimer"]


def test_reports_daily_insufficient_history(app, client):
    _seed(app, history=[_raw()])
    d = client.get("/api/reports/daily").get_json()["data"]
    assert d["available"] is False
    assert "Not enough" in d["summary"]
