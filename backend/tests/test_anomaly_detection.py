"""Unit tests for the rule-based anomaly engine.

These tests pin the thresholds documented in docs/api.md. If you intentionally
change a threshold, update both the engine and these tests together.
"""

from __future__ import annotations

import pytest

from backend.anomaly_detection import (
    TelemetryValidationError,
    analyze,
    battery_status,
    classify_activity,
    normalize_temperature,
    stress_level,
    validate_telemetry,
    wellness_score,
)


def _payload(**overrides):
    base = {
        "heart_rate": 72,
        "spo2": 97,
        "temperature_c": 36.8,
        "steps": 1200,
        "calories": 45.5,
        "sleep_duration_sec": 25200,
        "timestamp": 1779716107821,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_validate_telemetry_accepts_well_formed_payload():
    clean = validate_telemetry(_payload())
    assert clean["heart_rate"] == 72
    assert clean["spo2"] == 97
    assert clean["temperature_c"] == 36.8
    assert clean["timestamp"] == 1779716107821


def test_validate_telemetry_missing_field_rejected():
    payload = _payload()
    del payload["spo2"]
    with pytest.raises(TelemetryValidationError, match="spo2"):
        validate_telemetry(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("heart_rate", 5),       # impossibly low
        ("heart_rate", 400),     # impossibly high
        ("spo2", 30),
        ("spo2", 150),
        ("temperature_c", 10),
        ("temperature_c", 60),
        ("steps", -1),
    ],
)
def test_validate_telemetry_rejects_impossible_values(field, value):
    with pytest.raises(TelemetryValidationError):
        validate_telemetry(_payload(**{field: value}))


def test_validate_telemetry_rejects_non_dict():
    with pytest.raises(TelemetryValidationError):
        validate_telemetry("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def test_normal_case_returns_normal():
    r = analyze(_payload())
    assert r["risk_level"] == "normal"
    assert r["reasons"] == []
    assert "normal" in r["alert_message"].lower()


def test_low_heart_rate_is_warning():
    r = analyze(_payload(heart_rate=50))
    assert r["risk_level"] == "warning"
    assert any("low_heart_rate" == h["rule"] for h in r["rule_hits"])


def test_critical_bradycardia_is_high():
    r = analyze(_payload(heart_rate=35))
    assert r["risk_level"] == "high"
    assert any(h["rule"] == "critical_bradycardia" for h in r["rule_hits"])


def test_critical_tachycardia_is_high():
    r = analyze(_payload(heart_rate=160))
    assert r["risk_level"] == "high"
    assert any(h["rule"] == "critical_tachycardia" for h in r["rule_hits"])


def test_low_spo2_warning_then_critical():
    warn = analyze(_payload(spo2=94))
    crit = analyze(_payload(spo2=88))
    assert warn["risk_level"] == "warning"
    assert crit["risk_level"] == "high"
    assert any(h["rule"] == "critical_hypoxia" for h in crit["rule_hits"])


def test_high_fever_is_high_risk():
    r = analyze(_payload(temperature_c=39.2))
    assert r["risk_level"] == "high"
    assert any(h["rule"] == "high_fever" for h in r["rule_hits"])


def test_overheating_combined_rule_fires():
    """High HR + elevated temp should fire the overheating combined rule."""
    r = analyze(_payload(heart_rate=125, temperature_c=37.9))
    rules = {h["rule"] for h in r["rule_hits"]}
    assert "overheating_risk" in rules
    assert r["risk_level"] == "high"


def test_oxygen_deficiency_combined_rule_fires():
    r = analyze(_payload(heart_rate=120, spo2=93))
    rules = {h["rule"] for h in r["rule_hits"]}
    assert "oxygen_deficiency_risk" in rules
    assert r["risk_level"] == "high"


def test_rest_stress_pattern_warning():
    r = analyze(_payload(heart_rate=115, steps=10))
    rules = {h["rule"] for h in r["rule_hits"]}
    assert "rest_stress_pattern" in rules
    # Includes "elevated_heart_rate" (warning) too — combined is also warning,
    # so overall remains warning.
    assert r["risk_level"] == "warning"


def test_hypothermia_warning():
    r = analyze(_payload(temperature_c=35.2))
    rules = {h["rule"] for h in r["rule_hits"]}
    assert "hypothermia_warning" in rules
    assert r["risk_level"] == "warning"


def test_missing_optional_steps_uses_default_zero():
    payload = _payload()
    del payload["steps"]
    r = analyze(payload)
    assert r["risk_level"] == "normal"


# ---------------------------------------------------------------------------
# Battery (optional field + device alert, kept out of vitals risk)
# ---------------------------------------------------------------------------
def test_battery_level_is_optional_and_omitted_when_absent():
    clean = validate_telemetry(_payload())
    assert "battery_level" not in clean


def test_battery_level_stored_when_present():
    clean = validate_telemetry(_payload(battery_level=83))
    assert clean["battery_level"] == 83


def test_battery_level_out_of_range_rejected():
    with pytest.raises(TelemetryValidationError):
        validate_telemetry(_payload(battery_level=150))


def test_low_battery_does_not_change_vitals_risk():
    """A flat battery is a device problem, not a clinical one."""
    r = analyze(_payload(battery_level=3))
    assert r["risk_level"] == "normal"


def test_normalize_temperature_handles_units_and_garbage():
    assert normalize_temperature(36.6) == 36.6           # celsius kept
    assert normalize_temperature(98.6) == 37.0           # fahrenheit -> C
    assert normalize_temperature(365) == 36.5            # x10 -> /10
    assert normalize_temperature(23.57) is None          # implausible
    assert normalize_temperature(256) is None            # garbage
    assert normalize_temperature("abc") is None
    assert normalize_temperature(None) is None


def test_validate_accepts_legacy_temperature_f():
    payload = {
        "heart_rate": 72, "spo2": 97, "temperature_f": 98.6,
        "timestamp": 1779716107821,
    }
    clean = validate_telemetry(payload)
    assert clean["temperature_c"] == 37.0


def test_validate_rejects_garbage_temperature():
    with pytest.raises(TelemetryValidationError):
        validate_telemetry({
            "heart_rate": 72, "spo2": 97, "temperature_c": 256,
            "timestamp": 1779716107821,
        })


def test_battery_status_thresholds():
    assert battery_status(None) is None
    assert battery_status(80) is None
    assert battery_status(15)["severity"] == "warning"
    assert battery_status(3)["severity"] == "high"


# ---------------------------------------------------------------------------
# Source (simulator vs real bracelet) + wellness score
# ---------------------------------------------------------------------------
def test_source_optional_and_validated():
    assert "source" not in validate_telemetry(_payload())
    clean = validate_telemetry(_payload(source="real_bracelet"))
    assert clean["source"] == "real_bracelet"


def test_invalid_source_rejected():
    with pytest.raises(TelemetryValidationError):
        validate_telemetry(_payload(source="hacker"))


def test_wellness_score_high_for_healthy_vitals():
    assert wellness_score(validate_telemetry(_payload())) >= 95


def test_wellness_score_drops_for_bad_vitals():
    bad = validate_telemetry(_payload(heart_rate=170, spo2=85, temperature_c=39.5))
    assert wellness_score(bad) < 50


def test_wellness_score_in_analysis_output():
    r = analyze(_payload())
    assert 0 <= r["wellness_score"] <= 100


# ---------------------------------------------------------------------------
# Activity + stress (deterministic, explainable — not trained models)
# ---------------------------------------------------------------------------
def test_activity_level_optional_and_validated():
    assert "activity_level" not in validate_telemetry(_payload())
    clean = validate_telemetry(_payload(activity_level=55))
    assert clean["activity_level"] == 55
    with pytest.raises(TelemetryValidationError):
        validate_telemetry(_payload(activity_level=500))


def test_classify_activity_levels():
    assert classify_activity(None, 70) == "unknown"
    assert classify_activity(2, 60) == "resting"
    assert classify_activity(45, 95) == "walking"
    assert classify_activity(80, 140) == "running"


def test_stress_high_when_hr_elevated_and_still():
    s = stress_level(hr=120, activity_level=5, temp_c=36.8)
    assert s["label"] == "stressed"
    assert s["score"] >= 50


def test_stress_relaxed_when_calm():
    s = stress_level(hr=68, activity_level=10, temp_c=36.6)
    assert s["label"] == "relaxed"


def test_exercise_is_not_flagged_as_stress():
    # High HR but high motion = exertion, not stress.
    s = stress_level(hr=140, activity_level=80, temp_c=37.2)
    assert s["label"] != "stressed"


def test_analyze_includes_activity_and_stress():
    r = analyze(_payload(activity_level=70))
    assert r["activity"] in ("walking", "running", "active", "resting")
    assert "label" in r["stress"] and "score" in r["stress"]
