"""
PulseGuard AI - health report builder.

Pure functions that turn a list of stored readings (+ alerts) into a
daily/weekly summary and a CSV export. No I/O here — the Flask layer feeds in
data from FirebaseService and serializes the result. Deterministic and
dependency-free so it is trivially testable.

Wellness/health summaries are informational, NOT a medical diagnosis.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional

# Columns exported to CSV (stable order; missing keys render blank).
CSV_COLUMNS = [
    "timestamp", "heart_rate", "spo2", "temperature_c",
    "steps", "calories", "battery_level", "activity_level",
    "activity", "stress_label", "stress_score",
    "wellness_score", "risk_level", "source",
]


def _nums(readings: List[Dict[str, Any]], key: str) -> List[float]:
    out: List[float] = []
    for r in readings:
        v = r.get(key)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def build_summary(
    readings: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    period: str,
) -> Dict[str, Any]:
    """Aggregate readings into a report dict for ``period`` ("daily"/"weekly")."""
    if not readings:
        return {
            "period": period,
            "count": 0,
            "summary": f"No readings recorded for the {period} period yet.",
        }

    hr = _nums(readings, "heart_rate")
    spo2 = _nums(readings, "spo2")
    temp = _nums(readings, "temperature_c")
    wellness = _nums(readings, "wellness_score")
    steps = _nums(readings, "steps")

    # Steps are cumulative; the delta across the window is "steps taken".
    steps_taken = int(max(steps) - min(steps)) if steps else 0

    risk_counts: Dict[str, int] = {}
    for r in readings:
        lvl = r.get("risk_level", "normal")
        risk_counts[lvl] = risk_counts.get(lvl, 0) + 1

    avg_hr = round(_avg(hr))
    avg_wellness = round(_avg(wellness)) if wellness else None
    high_alerts = sum(1 for a in alerts if a.get("risk_level") == "high")

    parts = [
        f"Over this {period} period we logged {len(readings)} readings.",
        f"Average heart rate was {avg_hr} bpm "
        f"(range {round(min(hr))}–{round(max(hr))}).",
        f"Average SpO₂ was {round(_avg(spo2))}% and average temperature "
        f"{_avg(temp):.1f}°C.",
        f"You took about {steps_taken} steps.",
    ]
    if avg_wellness is not None:
        parts.append(f"Average wellness score was {avg_wellness}/100.")
    if high_alerts:
        parts.append(
            f"{high_alerts} high-risk alert(s) were raised — review the Alerts "
            f"tab and consider contacting a healthcare professional if you had "
            f"symptoms."
        )
    else:
        parts.append("No high-risk alerts were raised.")
    parts.append("This is a wellness summary, not a medical diagnosis.")

    return {
        "period": period,
        "count": len(readings),
        "heart_rate": {
            "avg": avg_hr, "min": round(min(hr)), "max": round(max(hr)),
        },
        "spo2": {"avg": round(_avg(spo2)), "min": round(min(spo2))},
        "temperature_c": {
            "avg": round(_avg(temp), 1), "max": round(max(temp), 1),
        },
        "steps_taken": steps_taken,
        "wellness_avg": avg_wellness,
        "risk_breakdown": risk_counts,
        "alerts_total": len(alerts),
        "alerts_high": high_alerts,
        "summary": " ".join(parts),
    }


def _stat(xs: List[float]) -> Optional[Dict[str, float]]:
    if not xs:
        return None
    return {"avg": round(_avg(xs), 1), "min": round(min(xs), 1), "max": round(max(xs), 1)}


def build_daily_report(
    history: List[Dict[str, Any]],
    source: str = "firebase",
    min_readings: int = 3,
) -> Dict[str, Any]:
    """Daily summary from NORMALIZED Firebase history (canonical contract).

    Returns ``available: False`` with a clear message when there is not enough
    live history yet — it never fabricates a summary from simulated data.
    """
    valid = [r for r in history if isinstance(r, dict)]
    count = len(valid)
    if count < min_readings:
        return {
            "available": False,
            "count": count,
            "source": source,
            "summary": (
                "Not enough live Firebase history yet to build a daily report "
                f"(have {count}, need at least {min_readings} readings)."
            ),
            "disclaimer": "This is a wellness summary, not a medical diagnosis.",
        }

    hr = _nums(valid, "heart_rate")
    spo2 = _nums(valid, "spo2")
    temp = _nums(valid, "temperature_c")
    steps = _nums(valid, "steps")
    calories = _nums(valid, "calories")
    sleep = _nums(valid, "sleep_duration_sec")
    battery = _nums(valid, "battery_level")
    systolic = _nums(valid, "systolic")
    diastolic = _nums(valid, "diastolic")

    fall_events = sum(1 for r in valid if r.get("fall_alert") is True)
    steps_total = int(max(steps)) if steps else None
    sleep_hours = round(max(sleep) / 3600, 1) if sleep else None

    bp_summary = None
    if systolic and diastolic:
        bp_summary = {
            "systolic": _stat(systolic),
            "diastolic": _stat(diastolic),
        }

    return {
        "available": True,
        "period": "daily",
        "count": count,
        "source": source,
        "heart_rate": _stat(hr),
        "spo2": _stat(spo2),
        "temperature_c": _stat(temp),
        "steps_total": steps_total,
        "calories": round(max(calories), 1) if calories else None,
        "sleep_hours": sleep_hours,
        "battery": _stat(battery),
        "blood_pressure": bp_summary,
        "fall_events": fall_events,
        "summary": (
            f"Logged {count} live Firebase readings. "
            + (f"Heart rate averaged {round(_avg(hr))} bpm "
               f"({round(min(hr))}–{round(max(hr))}). " if hr else "")
            + (f"SpO₂ averaged {round(_avg(spo2))}%. " if spo2 else "")
            + (f"Temperature averaged {_avg(temp):.1f}°C. " if temp else "")
            + (f"{fall_events} fall event(s) recorded. " if fall_events else "")
        ).strip(),
        "disclaimer": "This is a wellness summary, not a medical diagnosis.",
    }


def to_csv(readings: List[Dict[str, Any]]) -> str:
    """Render readings as CSV text using the stable CSV_COLUMNS order."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for r in readings:
        writer.writerow({k: r.get(k, "") for k in CSV_COLUMNS})
    return buf.getvalue()
