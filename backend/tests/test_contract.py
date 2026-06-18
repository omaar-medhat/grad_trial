"""Unit tests for the canonical telemetry contract / normalization."""

from __future__ import annotations

from backend.telemetry_contract import (
    coerce_bool,
    device_status,
    fahrenheit_to_celsius,
    normalize_history,
    normalize_reading,
)

NOW = 1_700_000_000_000  # fixed "now" in ms for deterministic device_status


def _raw(**over):
    base = {
        "battery_level": 82, "calories": 0.48,
        "date_time": "2026-06-17 01:23:21", "diastolic": 80,
        "fall_alert": False, "heart_rate": 72, "risk_level": 1,
        "sleep_duration_sec": 28, "spo2": 98, "steps": 12,
        "stress_label": 1, "systolic": 120, "temperature_f": 98.6,
        "timestamp": NOW,
    }
    base.update(over)
    return base


def test_fahrenheit_to_celsius_body_temp():
    assert fahrenheit_to_celsius(98.6) == 37.0


def test_fahrenheit_impossible_value_is_none():
    assert fahrenheit_to_celsius(212) is None
    assert fahrenheit_to_celsius("nope") is None


def test_legacy_celsius_accepted():
    assert fahrenheit_to_celsius(37.0) == 37.0


def test_coerce_bool():
    assert coerce_bool(True) is True
    assert coerce_bool(False) is False
    assert coerce_bool(0) is False
    assert coerce_bool(1) is True
    assert coerce_bool("true") is True
    assert coerce_bool("false") is False
    assert coerce_bool(None) is None


def test_normalize_valid_firebase_reading():
    n = normalize_reading(_raw(), NOW)
    assert n["available"] is True
    assert n["source"] == "firebase"
    assert n["is_simulated"] is False
    assert n["heart_rate"] == 72
    assert n["spo2"] == 98
    assert n["temperature_c"] == 37.0       # 98.6°F -> 37.0°C
    assert n["systolic"] == 120 and n["diastolic"] == 80
    assert n["fall_alert"] is False
    assert n["battery_level"] == 82
    assert n["device_status"] == "connected"


def test_numeric_risk_and_stress_mapped_with_raw_kept():
    n = normalize_reading(_raw(risk_level=2, stress_label=0), NOW)
    assert n["risk_level"] == "high" and n["raw_risk_level"] == 2
    assert n["stress_label"] == "no_stress" and n["raw_stress_label"] == 0


def test_unknown_numeric_label_keeps_raw():
    n = normalize_reading(_raw(risk_level=7), NOW)
    assert n["raw_risk_level"] == 7
    assert n["risk_level"] == "7"  # stringified, nothing lost


def test_invalid_hr_spo2_temp_nulled():
    n = normalize_reading(
        _raw(heart_rate=5, spo2=200, temperature_f=999), NOW
    )
    assert n["heart_rate"] is None
    assert n["spo2"] is None
    assert n["temperature_c"] is None


def test_device_status_connected_stale_disconnected():
    assert device_status(NOW, NOW)[0] == "connected"
    assert device_status(NOW - 30_000, NOW)[0] == "stale"
    assert device_status(NOW - 120_000, NOW)[0] == "disconnected"
    assert device_status(None, NOW)[0] == "unknown"


def test_future_timestamp_clamped_to_connected():
    status, secs = device_status(NOW + 5_000, NOW)
    assert status == "connected" and secs == 0.0


def test_missing_reading_is_unavailable():
    n = normalize_reading(None, NOW)
    assert n["available"] is False
    assert n["source"] == "firebase"
    assert n["device_status"] == "disconnected"


def test_normalize_history_sorts_and_keeps_rows():
    recs = [
        _raw(heart_rate=80, timestamp=NOW - 1_000),
        _raw(heart_rate=70, timestamp=NOW - 5_000),
        _raw(heart_rate=500, timestamp=NOW),  # invalid HR -> nulled, row kept
    ]
    out = normalize_history(recs, NOW)
    assert [r["timestamp"] for r in out] == [NOW - 5_000, NOW - 1_000, NOW]
    assert out[-1]["heart_rate"] is None  # invalid value dropped per-field
