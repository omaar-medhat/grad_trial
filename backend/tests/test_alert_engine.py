"""Alert engine: severity scale, context-aware HR, guidance, current vs hist."""

from __future__ import annotations

import time

import pytest

from backend.alerts import (
    current_alerts,
    has_critical,
    historical_alerts,
    top_severity,
)

UID = "eKjIbPbsi5SqLX5HP8a6CtabtPm2"


def _t(**over):
    base = {
        "available": True, "heart_rate": 72, "spo2": 98,
        "temperature_c": 37.0, "systolic": 120, "diastolic": 80,
        "battery_level": 80, "fall_alert": False,
        "device_status": "connected", "timestamp": 1,
    }
    base.update(over)
    return base


def _by_metric(alerts, metric):
    return [a for a in alerts if a.get("metric") == metric]


def test_normal_reading_has_no_current_alerts():
    assert current_alerts(_t()) == []


def test_elevated_hr_resting_is_warning_but_active_is_watch():
    resting = _by_metric(current_alerts(_t(heart_rate=120, activity="sedentary")),
                         "heart_rate")[0]
    active = _by_metric(current_alerts(_t(heart_rate=120, activity="running")),
                        "heart_rate")[0]
    assert resting["severity"] == "warning"
    assert active["severity"] == "watch"


def test_very_high_hr_context_aware():
    resting = _by_metric(current_alerts(_t(heart_rate=160, activity="sedentary")),
                         "heart_rate")[0]
    active = _by_metric(current_alerts(_t(heart_rate=160, activity="running")),
                        "heart_rate")[0]
    assert resting["severity"] == "critical"
    assert resting["requires_medical_attention"] is True
    assert active["severity"] == "warning"


def test_low_spo2_warning_then_critical():
    assert any(a["severity"] == "warning"
               for a in _by_metric(current_alerts(_t(spo2=93)), "spo2"))
    assert any(a["severity"] == "critical"
               for a in _by_metric(current_alerts(_t(spo2=88)), "spo2"))


def test_fever_alert():
    a = _by_metric(current_alerts(_t(temperature_c=39.0)), "temperature_c")[0]
    assert a["severity"] == "warning" and a["title"] == "High temperature"


def test_blood_pressure_alerts():
    crisis = _by_metric(current_alerts(_t(systolic=190, diastolic=125)),
                        "blood_pressure")[0]
    high = _by_metric(current_alerts(_t(systolic=150, diastolic=95)),
                      "blood_pressure")[0]
    assert crisis["severity"] == "critical"
    assert high["severity"] == "warning"


def test_fall_is_critical_with_emergency_guidance():
    a = _by_metric(current_alerts(_t(fall_alert=True)), "fall_alert")[0]
    assert a["severity"] == "critical"
    assert a["requires_medical_attention"] is True
    assert a["emergency_guidance"]
    assert a["safe_guidance"]
    assert a["id"]


def test_low_battery_alert_only_when_low():
    assert _by_metric(current_alerts(_t(battery_level=80)), "battery_level") == []
    assert _by_metric(current_alerts(_t(battery_level=15)), "battery_level")[0][
        "severity"] == "watch"
    assert _by_metric(current_alerts(_t(battery_level=3)), "battery_level")[0][
        "severity"] == "critical"


def test_disconnected_device_creates_alert():
    a = _by_metric(current_alerts(_t(device_status="disconnected")),
                   "device_status")[0]
    assert a["severity"] == "warning"


def test_rapid_hr_rise_window_alert():
    now = int(time.time() * 1000)
    window = [
        _t(heart_rate=70, timestamp=now - 50000),
        _t(heart_rate=72, timestamp=now - 30000),
        _t(heart_rate=110, timestamp=now),
    ]
    alerts = current_alerts(_t(heart_rate=110), window=window)
    assert any(a["type"] == "hr_rapid_rise" for a in alerts)


def test_history_alerts_labelled_not_current():
    h = historical_alerts([_t(heart_rate=160)])
    assert h and all(a["is_current"] is False and a["scope"] == "history"
                     for a in h)


def test_helpers():
    crit = current_alerts(_t(spo2=80))
    assert has_critical(crit) is True
    assert top_severity(crit) == "critical"
    assert top_severity([]) == "normal"


# ---- endpoint ----
@pytest.fixture()
def active(monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", UID)
    return UID


def test_api_alerts_current_shape(app, client, active):
    app.config["FIREBASE"].write_latest(UID, {
        "heart_rate": 72, "spo2": 88, "temperature_c": 37.0,
        "timestamp": int(time.time() * 1000),
    })
    d = client.get("/api/alerts/current").get_json()["data"]
    assert d["uid"] == UID
    assert d["source"] == "firebase"
    assert d["has_current_critical"] is True
    assert d["top_severity"] == "critical"
    assert any(a["metric"] == "spo2" for a in d["current"])
    assert "history" not in d  # /current is current-only
