"""
PulseGuard AI - Deterministic alert engine (whole-project, multi-signal).

Alerts are computed from the canonical contract (see ``telemetry_contract``)
by transparent, auditable rules — NEVER by an LLM and NEVER from the device's
own opaque risk label. Two scopes are produced and kept separate:

  * current  — from the latest reading + recent window + device status.
  * history  — from past readings; clearly labelled historical.

Severity scale: normal < watch < warning < critical (``normal`` = no alert).

Every alert carries safe, conservative guidance. The engine never diagnoses a
disease, never predicts a medical event, and never prescribes medication — it
only flags that a reading is outside an expected range and what to do safely.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional

from .anomaly_detection import (
    BATTERY_CRIT,
    BATTERY_LOW,
    HR_CRIT_HIGH,
    HR_CRIT_LOW,
    HR_HIGH,
    HR_LOW,
    SPO2_CRIT,
    SPO2_WARN,
    TEMP_CRIT_HIGH,
    TEMP_LOW_WARN,
    TEMP_NORMAL_HIGH,
)

# Blood-pressure thresholds (mmHg), AHA categories (simplified, configurable).
BP_SYS_CRISIS = int(os.environ.get("BP_SYS_CRISIS", 180))
BP_DIA_CRISIS = int(os.environ.get("BP_DIA_CRISIS", 120))
BP_SYS_HIGH = int(os.environ.get("BP_SYS_HIGH", 140))
BP_DIA_HIGH = int(os.environ.get("BP_DIA_HIGH", 90))
BP_SYS_LOW = int(os.environ.get("BP_SYS_LOW", 90))
BP_DIA_LOW = int(os.environ.get("BP_DIA_LOW", 60))

# Rapid HR rise over the recent window that is worth a "watch".
HR_RAPID_RISE = int(os.environ.get("HR_RAPID_RISE", 35))

SEVERITY_ORDER = {"normal": 0, "watch": 1, "warning": 2, "critical": 3}

# Conservative, non-diagnostic guidance per severity.
SAFE_GUIDANCE = {
    "watch": "Your reading is slightly outside the expected range. Rest and "
             "keep monitoring.",
    "warning": "This reading needs attention. If it continues or you feel "
               "unwell, contact a healthcare professional.",
    "critical": "This may be serious. Please check how you feel and seek help "
                "if needed.",
}
EMERGENCY_GUIDANCE = (
    "If you have chest pain, severe dizziness, fainting, shortness of breath, "
    "confusion, injury after a fall, or other severe symptoms, seek urgent "
    "medical help now."
)

_ACTIVE_WORDS = ("running", "run", "walking", "active", "exercise", "moderate")


def _is_active(activity: Optional[str]) -> bool:
    return bool(activity) and any(w in str(activity).lower() for w in _ACTIVE_WORDS)


def _mk(
    kind: str,
    severity: str,
    title: str,
    message: str,
    *,
    metric: str,
    value: Any = None,
    threshold: Any = None,
    timestamp: Any = None,
    scope: str = "current",
) -> Dict[str, Any]:
    crit = severity == "critical"
    # Stable id: a given alert kind for a given reading timestamp is one alert
    # (lets the UI dedupe proactive cards across polls).
    raw_id = f"{scope}:{kind}:{severity}:{timestamp}"
    alert_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:12]
    return {
        "id": alert_id,
        "type": kind,            # legacy alias / stable kind
        "severity": severity,
        "title": title,
        "message": message,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "is_current": scope == "current",
        "scope": scope,
        "source": "firebase",
        "timestamp": timestamp,
        "safe_guidance": SAFE_GUIDANCE.get(severity, ""),
        "emergency_guidance": EMERGENCY_GUIDANCE if crit else None,
        "requires_medical_attention": crit,
    }


def _hr_alerts(hr: float, active: bool, ts: Any, scope: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if hr < HR_CRIT_LOW:
        out.append(_mk("low_heart_rate", "critical", "Very low heart rate",
                       f"Heart rate is critically low ({hr:.0f} bpm).",
                       metric="heart_rate", value=hr, threshold=HR_CRIT_LOW,
                       timestamp=ts, scope=scope))
    elif hr < HR_LOW:
        out.append(_mk("low_heart_rate", "watch", "Low heart rate",
                       f"Heart rate is below the resting range ({hr:.0f} bpm).",
                       metric="heart_rate", value=hr, threshold=HR_LOW,
                       timestamp=ts, scope=scope))
    elif hr > HR_CRIT_HIGH:
        # Context-aware: very high HR is less alarming during exercise.
        sev = "warning" if active else "critical"
        out.append(_mk("high_heart_rate", sev, "Very high heart rate",
                       f"Heart rate is very high ({hr:.0f} bpm)"
                       + (" during activity." if active else " at rest."),
                       metric="heart_rate", value=hr, threshold=HR_CRIT_HIGH,
                       timestamp=ts, scope=scope))
    elif hr > HR_HIGH:
        sev = "watch" if active else "warning"
        out.append(_mk("high_heart_rate", sev, "Elevated heart rate",
                       f"Heart rate is elevated ({hr:.0f} bpm)"
                       + (" during activity." if active else " while resting."),
                       metric="heart_rate", value=hr, threshold=HR_HIGH,
                       timestamp=ts, scope=scope))
    return out


def _vital_alerts(
    t: Dict[str, Any], scope: str, activity: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Alerts from a single normalized reading (HR/SpO₂/temp/BP/fall/battery)."""
    out: List[Dict[str, Any]] = []
    ts = t.get("timestamp")
    active = _is_active(activity or t.get("activity"))

    hr = t.get("heart_rate")
    if isinstance(hr, (int, float)):
        out.extend(_hr_alerts(float(hr), active, ts, scope))

    spo2 = t.get("spo2")
    if isinstance(spo2, (int, float)):
        if spo2 < SPO2_CRIT:
            out.append(_mk("low_spo2", "critical", "Low blood oxygen",
                           f"Blood oxygen is critically low (SpO₂ {spo2:.0f}%).",
                           metric="spo2", value=spo2, threshold=SPO2_CRIT,
                           timestamp=ts, scope=scope))
        elif spo2 < SPO2_WARN:
            out.append(_mk("low_spo2", "warning", "Low blood oxygen",
                           f"Blood oxygen is below the normal range "
                           f"(SpO₂ {spo2:.0f}%).",
                           metric="spo2", value=spo2, threshold=SPO2_WARN,
                           timestamp=ts, scope=scope))

    temp = t.get("temperature_c")
    if isinstance(temp, (int, float)):
        if temp >= TEMP_CRIT_HIGH:
            out.append(_mk("fever", "warning", "High temperature",
                           f"Temperature indicates a fever ({temp:.1f}°C).",
                           metric="temperature_c", value=temp,
                           threshold=TEMP_CRIT_HIGH, timestamp=ts, scope=scope))
        elif temp > TEMP_NORMAL_HIGH:
            out.append(_mk("fever", "watch", "Slightly high temperature",
                           f"Temperature is slightly elevated ({temp:.1f}°C).",
                           metric="temperature_c", value=temp,
                           threshold=TEMP_NORMAL_HIGH, timestamp=ts, scope=scope))
        elif temp < TEMP_LOW_WARN:
            out.append(_mk("low_temperature", "watch", "Low temperature",
                           f"Body temperature is below normal ({temp:.1f}°C).",
                           metric="temperature_c", value=temp,
                           threshold=TEMP_LOW_WARN, timestamp=ts, scope=scope))

    sys_bp = t.get("systolic")
    dia_bp = t.get("diastolic")
    if isinstance(sys_bp, (int, float)) and isinstance(dia_bp, (int, float)):
        if sys_bp >= BP_SYS_CRISIS or dia_bp >= BP_DIA_CRISIS:
            out.append(_mk("blood_pressure", "critical", "Very high blood pressure",
                           f"Blood pressure is very high "
                           f"({sys_bp:.0f}/{dia_bp:.0f} mmHg).",
                           metric="blood_pressure", value=[sys_bp, dia_bp],
                           threshold=[BP_SYS_CRISIS, BP_DIA_CRISIS],
                           timestamp=ts, scope=scope))
        elif sys_bp >= BP_SYS_HIGH or dia_bp >= BP_DIA_HIGH:
            out.append(_mk("blood_pressure", "warning", "High blood pressure",
                           f"Blood pressure is high "
                           f"({sys_bp:.0f}/{dia_bp:.0f} mmHg).",
                           metric="blood_pressure", value=[sys_bp, dia_bp],
                           threshold=[BP_SYS_HIGH, BP_DIA_HIGH],
                           timestamp=ts, scope=scope))
        elif sys_bp < BP_SYS_LOW or dia_bp < BP_DIA_LOW:
            out.append(_mk("blood_pressure", "watch", "Low blood pressure",
                           f"Blood pressure is low "
                           f"({sys_bp:.0f}/{dia_bp:.0f} mmHg).",
                           metric="blood_pressure", value=[sys_bp, dia_bp],
                           threshold=[BP_SYS_LOW, BP_DIA_LOW],
                           timestamp=ts, scope=scope))

    if t.get("fall_alert") is True:
        out.append(_mk("fall", "critical", "Fall detected",
                       "The bracelet detected a fall.",
                       metric="fall_alert", value=True, threshold=True,
                       timestamp=ts, scope=scope))

    battery = t.get("battery_level")
    if isinstance(battery, (int, float)):
        if battery <= BATTERY_CRIT:
            out.append(_mk("low_battery", "critical", "Battery critically low",
                           f"Bracelet battery is critically low ({battery:.0f}%).",
                           metric="battery_level", value=battery,
                           threshold=BATTERY_CRIT, timestamp=ts, scope=scope))
        elif battery <= BATTERY_LOW:
            out.append(_mk("low_battery", "watch", "Low battery",
                           f"Bracelet battery is low ({battery:.0f}%).",
                           metric="battery_level", value=battery,
                           threshold=BATTERY_LOW, timestamp=ts, scope=scope))

    return out


def _window_alerts(
    latest: Dict[str, Any], window: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Trend alerts from the recent window (e.g. rapid HR rise)."""
    out: List[Dict[str, Any]] = []
    hrs = [
        r["heart_rate"] for r in window
        if isinstance(r.get("heart_rate"), (int, float))
    ]
    hr_now = latest.get("heart_rate")
    if isinstance(hr_now, (int, float)) and len(hrs) >= 3:
        baseline = min(hrs)
        if hr_now - baseline >= HR_RAPID_RISE:
            out.append(_mk("hr_rapid_rise", "watch", "Rapid heart-rate rise",
                           f"Heart rate rose quickly (+{hr_now - baseline:.0f} bpm) "
                           "over the last minute.",
                           metric="heart_rate", value=hr_now,
                           threshold=HR_RAPID_RISE,
                           timestamp=latest.get("timestamp"), scope="current"))
    return out


def current_alerts(
    latest: Optional[Dict[str, Any]],
    window: Optional[List[Dict[str, Any]]] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Alerts reflecting the live state, including device connectivity."""
    if not latest or not latest.get("available"):
        return [_mk("device", "warning", "Bracelet disconnected",
                    "No live reading from the bracelet.",
                    metric="device_status", value="disconnected",
                    scope="current")]

    activity = (profile or {}).get("activity") or latest.get("activity")
    out = _vital_alerts(latest, scope="current", activity=activity)
    out.extend(_window_alerts(latest, window or []))

    status = latest.get("device_status")
    secs = latest.get("last_seen_seconds")
    age = f" — last reading {secs:.0f}s ago" if isinstance(secs, (int, float)) else ""
    if status == "stale":
        out.append(_mk("device", "watch", "Bracelet data is stale",
                       f"Bracelet data is stale{age}.",
                       metric="device_status", value="stale", scope="current"))
    elif status == "disconnected":
        out.append(_mk("device", "warning", "Bracelet disconnected",
                       f"Bracelet appears disconnected{age}.",
                       metric="device_status", value="disconnected",
                       scope="current"))
    return out


def historical_alerts(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alerts from past readings, each labelled scope='history'."""
    out: List[Dict[str, Any]] = []
    for rec in history:
        out.extend(_vital_alerts(rec, scope="history"))
    return out


def has_critical(alerts: List[Dict[str, Any]]) -> bool:
    return any(a.get("severity") == "critical" for a in alerts)


def top_severity(alerts: List[Dict[str, Any]]) -> str:
    sev = "normal"
    for a in alerts:
        if SEVERITY_ORDER.get(a.get("severity", "normal"), 0) > SEVERITY_ORDER[sev]:
            sev = a["severity"]
    return sev
