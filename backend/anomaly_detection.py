"""
PulseGuard AI - Rule-Based Health Anomaly Detection
====================================================

Pure-Python, dependency-free rule engine that classifies a single telemetry
reading into one of three risk levels: "normal" | "warning" | "high".

Why rules (not ML) for the primary engine?
  * Explainable: every alert names the exact rule that fired.
  * Deterministic: identical inputs → identical outputs (testable, auditable).
  * Safe-by-design: a model failure can never silently produce a wrong reading;
    the worst case is the rule engine still fires.
  * Healthcare appropriate: the ranges below follow WHO / AHA reference
    values, so a graduation panel can verify them against medical literature.

The frontend separately runs an ML-style ensemble (Z-Score / IQR / Moving Avg
/ simplified Isolation Forest) for *trend* anomalies. The two are
complementary: rules catch absolute-value danger, ML catches drift.

Public API
----------
    analyze(telemetry: dict) -> dict

Returns
-------
    {
      "risk_level": "normal" | "warning" | "high",
      "alert_message": str,
      "reasons": [str, ...],
      "rule_hits": [{"rule": str, "severity": str, "metric": str}, ...]
    }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Reference ranges (sourced from AHA / WHO adult resting guidelines).
# Edit here in ONE place — tests in tests/test_anomaly_detection.py pin them.
# ---------------------------------------------------------------------------
HR_CRIT_LOW = 40       # bpm — below this, severe bradycardia
HR_LOW = 60
HR_HIGH = 100
HR_CRIT_HIGH = 140

SPO2_CRIT = 92         # below this is medically urgent
SPO2_WARN = 95

TEMP_LOW_WARN = 35.5   # °C — hypothermia warning
TEMP_NORMAL_LOW = 36.0
TEMP_NORMAL_HIGH = 37.5
TEMP_WARN_HIGH = 38.4
TEMP_CRIT_HIGH = 38.5  # ≥ this is fever requiring attention

# Physically possible ranges — anything outside is rejected as invalid input.
HR_VALID = (20, 250)
SPO2_VALID = (50, 100)
TEMP_VALID = (25.0, 45.0)
STEPS_VALID = (0, 200_000)
CALORIES_VALID = (0, 20_000)
SLEEP_VALID = (0, 24 * 3600)
BATTERY_VALID = (0, 100)        # bracelet battery, percent
ACTIVITY_VALID = (0, 100)       # instantaneous activity/motion index

# Battery thresholds for a *device* alert (kept separate from vitals risk).
BATTERY_LOW = 20               # warn — charge soon
BATTERY_CRIT = 5              # critical — monitoring will stop soon

# Where a reading came from. "firebase" is the normalized live-sensor source
# (read from the Firebase Realtime Database root by the data-source resolver);
# the others let the same pipeline serve the simulator and uploaded datasets.
VALID_SOURCES = (
    "firebase", "simulator", "real_bracelet", "uploaded_dataset",
)


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------
class TelemetryValidationError(ValueError):
    """Raised when telemetry values are missing or impossible."""


def _require(d: Dict[str, Any], key: str) -> Any:
    if key not in d or d[key] is None:
        raise TelemetryValidationError(f"Missing required field: {key}")
    return d[key]


def _in_range(value: float, lo: float, hi: float, name: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise TelemetryValidationError(f"{name} must be numeric") from exc
    if v < lo or v > hi:
        raise TelemetryValidationError(
            f"{name} value {v} is outside physically valid range [{lo}, {hi}]"
        )
    return v


def normalize_temperature(raw: Any) -> Optional[float]:
    """Coerce a temperature reading to canonical Celsius.

    Handles three real-world cases seen in the data:
      * already Celsius (30–45)              → kept
      * Fahrenheit body range (86–113)       → converted to Celsius
      * accidentally scaled ×10 (300–450)    → divided by 10
    Anything that can't be made physiologically plausible returns None
    (so callers can mark it 'unavailable' instead of corrupting downstream).
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if 30.0 <= v <= 45.0:
        return round(v, 2)
    if 86.0 <= v <= 113.0:
        return round((v - 32.0) * 5.0 / 9.0, 2)
    if 300.0 <= v <= 450.0:
        c = v / 10.0
        if 30.0 <= c <= 45.0:
            return round(c, 2)
    return None


def validate_telemetry(t: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize + validate a telemetry payload. Returns a clean dict.

    Required: heart_rate, spo2, temperature (c or f), timestamp.
    Optional with sane defaults: steps, calories, sleep_duration_sec.
    Optional (only stored when present): battery_level (bracelet charge %).
    Temperature accepts `temperature_c` or legacy `temperature_f` and is
    normalized to Celsius; an unrecoverable value is rejected (so the clean
    store never holds garbage).
    """
    if not isinstance(t, dict):
        raise TelemetryValidationError("Telemetry payload must be a JSON object")

    hr = _in_range(_require(t, "heart_rate"), *HR_VALID, name="heart_rate")
    spo2 = _in_range(_require(t, "spo2"), *SPO2_VALID, name="spo2")
    raw_temp = t.get("temperature_c")
    if raw_temp is None:
        raw_temp = t.get("temperature_f")  # legacy schema
    temp = normalize_temperature(raw_temp)
    if temp is None:
        raise TelemetryValidationError(
            f"temperature is missing or not a plausible value: {raw_temp!r}"
        )
    ts = _require(t, "timestamp")
    try:
        ts = int(ts)
    except (TypeError, ValueError) as exc:
        raise TelemetryValidationError("timestamp must be an integer (ms epoch)") from exc

    steps = _in_range(t.get("steps", 0), *STEPS_VALID, name="steps")
    calories = _in_range(t.get("calories", 0), *CALORIES_VALID, name="calories")
    sleep = _in_range(
        t.get("sleep_duration_sec", 0), *SLEEP_VALID, name="sleep_duration_sec"
    )

    clean = {
        "heart_rate": round(hr, 1),
        "spo2": round(spo2, 1),
        "temperature_c": round(temp, 2),
        "steps": int(steps),
        "calories": round(calories, 2),
        "sleep_duration_sec": int(sleep),
        "timestamp": ts,
    }

    # Battery is optional: a phone or simulator may not report it. Only
    # include it when present so old payloads keep the exact same shape.
    battery = t.get("battery_level")
    if battery is not None:
        clean["battery_level"] = int(
            round(_in_range(battery, *BATTERY_VALID, name="battery_level"))
        )

    # Source is optional; when present it must be one of VALID_SOURCES so the
    # dashboard can distinguish simulated from real-bracelet data.
    source = t.get("source")
    if source is not None:
        if source not in VALID_SOURCES:
            raise TelemetryValidationError(
                f"source must be one of {VALID_SOURCES}, got '{source}'"
            )
        clean["source"] = source

    # Instantaneous activity/motion index (0–100), optional.
    activity = t.get("activity_level")
    if activity is not None:
        clean["activity_level"] = int(
            round(_in_range(activity, *ACTIVITY_VALID, name="activity_level"))
        )

    return clean


def classify_activity(activity_level: Optional[float], hr: float) -> str:
    """Coarse, explainable activity label from the motion index + heart rate.

    Deterministic (NOT a trained HAR model): running > brisk movement >
    walking > resting. Returns "unknown" when no motion signal is available.
    """
    if activity_level is None:
        return "unknown"
    if activity_level >= 65 or hr >= 130:
        return "running"
    if activity_level >= 30:
        return "walking"
    if activity_level >= 8:
        return "active"
    return "resting"


def stress_level(
    hr: float, activity_level: Optional[float], temp_c: float
) -> Dict[str, Any]:
    """A 0–100 stress indicator + label (relaxed | normal | stressed).

    Heuristic and explainable: an elevated heart rate while the body is
    *still* (low motion) is the classic stress signature. NOT a diagnosis.
    """
    act = 0.0 if activity_level is None else float(activity_level)
    score = 0.0
    # Elevated HR with little movement → likely stress, not exertion.
    if hr > 85 and act < 25:
        score += (hr - 85) * 2.0
    if hr > 110:
        score += 15
    if temp_c > TEMP_NORMAL_HIGH:
        score += 5
    score = max(0, min(100, round(score)))
    if score >= 50:
        label = "stressed"
    elif score >= 20:
        label = "normal"
    else:
        label = "relaxed"
    return {"label": label, "score": int(score)}


def wellness_score(clean: Dict[str, Any]) -> int:
    """A 0–100 wellness indicator derived from how far vitals sit from the
    healthy band. Deterministic and explainable — NOT a medical diagnosis.

    100 = everything in the ideal resting range; points are deducted for HR,
    SpO2 and temperature deviations. Always clamped to [0, 100].
    """
    hr = float(clean["heart_rate"])
    spo2 = float(clean["spo2"])
    temp = float(clean["temperature_c"])

    score = 100.0
    # Heart rate: ideal 60–100; deduct 0.5 per bpm outside the band.
    if hr > HR_HIGH:
        score -= (hr - HR_HIGH) * 0.5
    elif hr < HR_LOW:
        score -= (HR_LOW - hr) * 0.5
    # SpO2: ideal ≥97; deduct 4 per percent below.
    if spo2 < 97:
        score -= (97 - spo2) * 4
    # Temperature: ideal 36.0–37.5; deduct 12 per °C outside.
    if temp > TEMP_NORMAL_HIGH:
        score -= (temp - TEMP_NORMAL_HIGH) * 12
    elif temp < TEMP_NORMAL_LOW:
        score -= (TEMP_NORMAL_LOW - temp) * 12

    return int(max(0, min(100, round(score))))


def battery_status(battery_level: Optional[float]) -> Optional[Dict[str, str]]:
    """Classify the bracelet battery into a *device* alert (not a vital).

    Returns None when battery is unknown or healthy, otherwise a dict with
    ``severity`` ("warning" | "high"), ``rule`` and a human ``message``.
    Kept separate from :func:`analyze` so a low battery never changes the
    patient's clinical ``risk_level``.
    """
    if battery_level is None:
        return None
    if battery_level <= BATTERY_CRIT:
        return {
            "severity": "high",
            "rule": "critical_battery",
            "message": (
                "Bracelet battery critically low — charge now to avoid "
                "losing monitoring."
            ),
        }
    if battery_level <= BATTERY_LOW:
        return {
            "severity": "warning",
            "rule": "low_battery",
            "message": "Bracelet battery is low — please charge soon.",
        }
    return None


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------
def _hr_rule(hr: float) -> Optional[Tuple[str, str, str]]:
    if hr < HR_CRIT_LOW:
        return ("critical_bradycardia", "high", "heart_rate")
    if hr < HR_LOW:
        return ("low_heart_rate", "warning", "heart_rate")
    if hr > HR_CRIT_HIGH:
        return ("critical_tachycardia", "high", "heart_rate")
    if hr > HR_HIGH:
        return ("elevated_heart_rate", "warning", "heart_rate")
    return None


def _spo2_rule(spo2: float) -> Optional[Tuple[str, str, str]]:
    if spo2 < SPO2_CRIT:
        return ("critical_hypoxia", "high", "spo2")
    if spo2 < SPO2_WARN:
        return ("low_spo2", "warning", "spo2")
    return None


def _temp_rule(temp_c: float) -> Optional[Tuple[str, str, str]]:
    if temp_c >= TEMP_CRIT_HIGH:
        return ("high_fever", "high", "temperature_c")
    if temp_c > TEMP_NORMAL_HIGH:
        return ("low_grade_fever", "warning", "temperature_c")
    if temp_c < TEMP_LOW_WARN:
        return ("hypothermia_warning", "warning", "temperature_c")
    return None


RULE_MESSAGES = {
    "critical_bradycardia": "Heart rate is critically low (<40 bpm). Rest and seek medical help.",
    "low_heart_rate": "Heart rate is below the typical resting range.",
    "elevated_heart_rate": "Heart rate is elevated above the typical resting range.",
    "critical_tachycardia": "Heart rate is critically high (>140 bpm). Stop activity and seek help.",
    "critical_hypoxia": "Blood oxygen is critically low (SpO2 < 92%). Seek medical help.",
    "low_spo2": "Blood oxygen is slightly below the normal range (SpO2 < 95%).",
    "high_fever": "Temperature indicates a high fever (≥38.5°C).",
    "low_grade_fever": "Temperature is above the normal range (low-grade fever).",
    "hypothermia_warning": "Body temperature is below the normal range.",
    "overheating_risk": "High heart rate combined with elevated temperature suggests overheating.",
    "oxygen_deficiency_risk": "Low SpO2 with high heart rate suggests oxygen deficiency.",
    "rest_stress_pattern": "High heart rate with very low movement may indicate stress or anxiety.",
}


def _combined_rules(hr: float, spo2: float, temp_c: float, steps: int) -> List[Tuple[str, str, str]]:
    hits: List[Tuple[str, str, str]] = []
    if hr > HR_HIGH and temp_c > TEMP_NORMAL_HIGH:
        hits.append(("overheating_risk", "high", "heart_rate+temperature_c"))
    if spo2 < SPO2_WARN and hr > HR_HIGH:
        hits.append(("oxygen_deficiency_risk", "high", "spo2+heart_rate"))
    if hr > HR_HIGH and steps < 100:
        hits.append(("rest_stress_pattern", "warning", "heart_rate+steps"))
    return hits


def analyze(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full rule engine on a validated telemetry dict.

    Caller may pass either a raw dict (validated here) or a pre-validated dict.
    """
    clean = validate_telemetry(telemetry)
    hr, spo2, temp = clean["heart_rate"], clean["spo2"], clean["temperature_c"]
    steps = clean["steps"]

    rule_hits: List[Tuple[str, str, str]] = []
    for rule_fn, value in (
        (_hr_rule, hr),
        (_spo2_rule, spo2),
        (_temp_rule, temp),
    ):
        hit = rule_fn(value)
        if hit is not None:
            rule_hits.append(hit)
    rule_hits.extend(_combined_rules(hr, spo2, temp, steps))

    # Aggregate severity: any "high" -> high, else any "warning" -> warning, else normal.
    severities = {h[1] for h in rule_hits}
    if "high" in severities:
        risk_level = "high"
    elif "warning" in severities:
        risk_level = "warning"
    else:
        risk_level = "normal"

    reasons = [RULE_MESSAGES.get(name, name) for name, _, _ in rule_hits]
    if risk_level == "normal":
        alert_message = "Vitals are within normal range."
    elif risk_level == "warning":
        alert_message = "One or more vitals are slightly out of range — keep monitoring."
    else:
        alert_message = "Critical vitals detected — please rest and seek medical help."

    activity_level = clean.get("activity_level")
    return {
        "risk_level": risk_level,
        "wellness_score": wellness_score(clean),
        "activity": classify_activity(activity_level, hr),
        "stress": stress_level(hr, activity_level, temp),
        "alert_message": alert_message,
        "reasons": reasons,
        "rule_hits": [
            {"rule": name, "severity": sev, "metric": metric}
            for name, sev, metric in rule_hits
        ],
    }
