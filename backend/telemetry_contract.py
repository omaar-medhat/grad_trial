"""
PulseGuard AI - Canonical telemetry contract + Firebase normalization.

This module is the ONE place that converts a raw Firebase Realtime-Database
reading (root ``/latest_telemetry`` and ``/history/{push_id}``) into the
canonical app contract that the dashboard, analytics, alerts, reports and the
chatbot all consume. There is intentionally a single normalization function so
the project never grows a second source of truth again.

Raw Firebase schema (confirmed live on lab10prototyping-default-rtdb):
    battery_level, calories, date_time, diastolic, fall_alert, heart_rate,
    risk_level (numeric 0/1/2), sleep_duration_sec, spo2, steps,
    stress_label (numeric 0/1/2), systolic, temperature_f (Fahrenheit),
    timestamp (ms epoch)

Canonical contract (see ``normalize_reading``):
    available, heart_rate, spo2, temperature_c, steps, calories,
    sleep_duration_sec, battery_level, systolic, diastolic, fall_alert,
    risk_level, raw_risk_level, stress_label, raw_stress_label, source,
    is_simulated, timestamp, date_time, device_status, last_seen_seconds

Normalization rules (documented + unit-tested in tests/test_contract.py):
  * heart_rate     valid 20-250 bpm        → out-of-range becomes None
  * spo2           valid 50-100 %          → out-of-range becomes None
  * temperature_f  Fahrenheit              → temperature_c (98.6°F == 37.0°C);
                   a legacy Celsius value (25-45) is accepted as-is; an
                   impossible value becomes None (never charted)
  * battery_level  valid 0-100 %
  * steps          non-negative integer
  * systolic       valid 70-260 mmHg
  * diastolic      valid 40-150 mmHg
  * fall_alert     coerced to a strict bool
  * risk_level     numeric 0/1/2 mapped to a string (RISK_LEVEL_MAP);
                   raw integer is always preserved as raw_risk_level
  * stress_label   numeric 0/1/2 mapped to a string (STRESS_LABEL_MAP);
                   raw integer is always preserved as raw_stress_label
  * timestamp      ms epoch → drives device_status / last_seen_seconds
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from .anomaly_detection import (
    BATTERY_VALID,
    HR_VALID,
    SPO2_VALID,
    STEPS_VALID,
    TEMP_VALID,
    normalize_temperature,
)

# Physically plausible blood-pressure ranges (mmHg). Outside → rejected (None),
# so the app never invents or trusts a garbage cuff reading.
SYSTOLIC_VALID = (70, 260)
DIASTOLIC_VALID = (40, 150)

# ---------------------------------------------------------------------------
# Numeric-label → string mappings.
#
# The bracelet firmware emits risk_level and stress_label as small integers.
# The exact semantics are NOT documented by the firmware, so we ALWAYS keep
# the raw integer (raw_risk_level / raw_stress_label) alongside the mapped
# string, and the mapping itself is overridable via env so it can be corrected
# without a code change. For clinical decisions (alerts) the backend prefers
# its own deterministic rule engine over these device labels — see app.py.
#
# Default assumption: a 3-point severity scale, 0 = lowest.
# ---------------------------------------------------------------------------
_DEFAULT_RISK_MAP = {0: "low", 1: "moderate", 2: "high"}
_DEFAULT_STRESS_MAP = {0: "no_stress", 1: "normal", 2: "high"}


def _parse_int_map(env_value: Optional[str], default: Dict[int, str]) -> Dict[int, str]:
    """Parse a ``0:low,1:moderate,2:high`` style env var into an int→str map."""
    if not env_value:
        return dict(default)
    out: Dict[int, str] = {}
    for pair in env_value.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        k, v = pair.split(":", 1)
        try:
            out[int(k.strip())] = v.strip()
        except ValueError:
            continue
    return out or dict(default)


def risk_level_map() -> Dict[int, str]:
    return _parse_int_map(os.environ.get("DATA_RISK_MAP"), _DEFAULT_RISK_MAP)


def stress_label_map() -> Dict[int, str]:
    return _parse_int_map(os.environ.get("DATA_STRESS_MAP"), _DEFAULT_STRESS_MAP)


# ---------------------------------------------------------------------------
# Device connection / staleness thresholds (seconds, configurable via env).
# ---------------------------------------------------------------------------
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def connected_threshold_sec() -> int:
    return _int_env("DEVICE_CONNECTED_MAX_SEC", 15)


def stale_threshold_sec() -> int:
    return _int_env("DEVICE_STALE_MAX_SEC", 60)


def sensor_ts_future_skew_sec() -> int:
    """How far a sensor timestamp may sit in the *future* before it is deemed
    untrustworthy (clock-skew / wrong epoch) and ignored in favour of observed
    freshness."""
    return _int_env("SENSOR_TS_FUTURE_SKEW_SEC", 120)


def _status_from_seconds(last_seen: float) -> str:
    if last_seen <= connected_threshold_sec():
        return "connected"
    if last_seen <= stale_threshold_sec():
        return "stale"
    return "disconnected"


# ---------------------------------------------------------------------------
# Field-level coercion helpers
# ---------------------------------------------------------------------------
def _num_in_range(value: Any, lo: float, hi: float) -> Optional[float]:
    """Return float(value) if finite and within [lo, hi], else None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if v < lo or v > hi:
        return None
    return v


def fahrenheit_to_celsius(raw: Any) -> Optional[float]:
    """Convert the Firebase ``temperature_f`` field to canonical Celsius.

    98.6°F → 37.0°C. A value already in the Celsius body range (25-45) is
    accepted as-is (defensive against a legacy/misconfigured device). Anything
    physiologically impossible returns None (so it is never charted).
    Delegates to the shared :func:`normalize_temperature` so the Fahrenheit
    rule lives in exactly one place.
    """
    return normalize_temperature(raw)


def coerce_bool(value: Any) -> Optional[bool]:
    """Coerce a Firebase fall_alert value to a strict bool (None if unknown)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
    return None


def _map_label(
    value: Any, mapping: Dict[int, str]
) -> Tuple[Optional[str], Any]:
    """Map a numeric label to a string. Returns (mapped_or_raw, raw).

    * numeric & known      → (mapping[n], n)
    * numeric & unknown    → (str(n), n)            keep raw so nothing is lost
    * already a string     → (value, value)
    * missing              → (None, None)
    """
    if value is None:
        return None, None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return str(value), value
    if isinstance(value, (int, float)) and float(value).is_integer():
        n = int(value)
        return mapping.get(n, str(n)), n
    if isinstance(value, str):
        return value, value
    return str(value), value


def device_status(
    timestamp_ms: Any, now_ms: int
) -> Tuple[str, Optional[float]]:
    """Classify bracelet freshness from the latest reading timestamp alone.

    Returns ``(status, last_seen_seconds)``. A timestamp in the (slight) future
    is clamped to 0s. Kept for the simple/unit-test path; the live API uses
    :func:`resolve_device_status` which also considers observed payload change.
    """
    try:
        ts = float(timestamp_ms)
    except (TypeError, ValueError):
        return "unknown", None
    if ts <= 0:
        return "unknown", None
    last_seen = (now_ms - ts) / 1000.0
    if last_seen < 0:
        last_seen = 0.0
    return _status_from_seconds(last_seen), round(last_seen, 1)


def resolve_device_status(
    sensor_ts: Any,
    observed_last_seen_ms: Optional[int],
    now_ms: int,
) -> Tuple[str, Optional[float], str]:
    """Robust freshness using the best available signal.

    Returns ``(status, last_seen_seconds, basis)`` where basis is one of
    ``sensor_timestamp`` / ``observed_change`` / ``missing``.

    Why two signals: some firmware writes a ``timestamp`` whose epoch is not
    aligned with real server time (wrong RTC / timezone), so a device that is
    actively pushing every few seconds would otherwise look "disconnected".
    We therefore also track when the Firebase payload last *changed* on the
    server (observed freshness) and use whichever signal is fresher — so a
    live, changing feed always reads as connected, while a feed that stops
    changing correctly ages into stale/disconnected.
    """
    candidates: List[Tuple[float, str]] = []

    # (1) Sensor timestamp — only trusted if it is a plausible ms epoch and not
    # implausibly far in the future (guards a fast/AHEAD device clock from
    # pinning us to "connected" forever).
    try:
        ts = float(sensor_ts)
    except (TypeError, ValueError):
        ts = 0.0
    if ts > 0:
        delta = (now_ms - ts) / 1000.0
        if delta >= -float(sensor_ts_future_skew_sec()):
            candidates.append((max(0.0, delta), "sensor_timestamp"))

    # (2) Observed payload change on the server (server-time based, immune to
    # device clock skew).
    if observed_last_seen_ms is not None:
        odelta = max(0.0, (now_ms - observed_last_seen_ms) / 1000.0)
        candidates.append((odelta, "observed_change"))

    if not candidates:
        return "unknown", None, "missing"

    last_seen, basis = min(candidates, key=lambda c: c[0])
    return _status_from_seconds(last_seen), round(last_seen, 1), basis


# ---------------------------------------------------------------------------
# The single normalization function
# ---------------------------------------------------------------------------
def _iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    import datetime
    return datetime.datetime.fromtimestamp(
        ms / 1000.0, datetime.timezone.utc
    ).isoformat()


def normalize_reading(
    raw: Optional[Dict[str, Any]],
    now_ms: int,
    source: str = "firebase",
    is_simulated: bool = False,
    observed_last_seen_ms: Optional[int] = None,
    uid: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert ONE raw Firebase reading into the canonical contract.

    ``now_ms`` is the current epoch in milliseconds (injected so the function
    stays pure and unit-testable). ``source`` / ``is_simulated`` describe where
    the reading came from and are echoed verbatim — a Firebase reading is
    never relabelled as simulated, and vice-versa.

    ``observed_last_seen_ms`` (server time of the last payload *change*) makes
    device-status robust to a misaligned device clock — see
    :func:`resolve_device_status`.
    """
    if not raw or not isinstance(raw, dict):
        return {
            "available": False,
            "uid": uid,
            "source": source,
            "is_simulated": is_simulated,
            "device_status": "disconnected" if source == "firebase" else "unknown",
            "last_seen_seconds": None,
            "used_freshness_basis": "missing",
            "server_observed_last_seen_at": _iso(observed_last_seen_ms),
            "timestamp": None,
        }

    hr = _num_in_range(raw.get("heart_rate"), *HR_VALID)
    spo2 = _num_in_range(raw.get("spo2"), *SPO2_VALID)
    # Temperature: PREFER a valid Celsius reading; otherwise convert the
    # Fahrenheit field (98.6°F → 37.0°C). Never trust an impossible value.
    temp_c = _num_in_range(raw.get("temperature_c"), *TEMP_VALID)
    if temp_c is None:
        temp_c = fahrenheit_to_celsius(raw.get("temperature_c"))
    if temp_c is None:
        temp_c = fahrenheit_to_celsius(raw.get("temperature_f"))
    # Echo Fahrenheit too: raw value if present, else derived from Celsius.
    temp_f = _num_in_range(raw.get("temperature_f"), 50, 140)
    if temp_f is None and temp_c is not None:
        temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)

    battery = _num_in_range(raw.get("battery_level"), *BATTERY_VALID)
    steps = _num_in_range(raw.get("steps"), *STEPS_VALID)
    systolic = _num_in_range(raw.get("systolic"), *SYSTOLIC_VALID)
    diastolic = _num_in_range(raw.get("diastolic"), *DIASTOLIC_VALID)
    calories = _num_in_range(raw.get("calories"), 0, 20_000)

    # Sleep: new schema uses `sleep_duration` (seconds); keep legacy
    # `sleep_duration_sec` too. Both are surfaced.
    sleep_new = _num_in_range(raw.get("sleep_duration"), 0, 24 * 3600)
    sleep_legacy = _num_in_range(raw.get("sleep_duration_sec"), 0, 24 * 3600)
    sleep_duration = sleep_new if sleep_new is not None else sleep_legacy
    sleep_sec = sleep_legacy if sleep_legacy is not None else sleep_new

    # Risk / stress: new schema sends STRINGS (risk:"Low", stress:"Normal");
    # legacy sent numeric risk_level/stress_label. Support both, keep raw.
    risk_str, risk_raw = _map_label(
        raw.get("risk", raw.get("risk_level")), risk_level_map()
    )
    stress_str, stress_raw = _map_label(
        raw.get("stress", raw.get("stress_label")), stress_label_map()
    )

    status, last_seen, basis = resolve_device_status(
        raw.get("timestamp"), observed_last_seen_ms, now_ms
    )

    return {
        "available": True,
        "uid": uid,
        "heart_rate": round(hr, 1) if hr is not None else None,
        "spo2": round(spo2) if spo2 is not None else None,
        "temperature_c": round(temp_c, 2) if temp_c is not None else None,
        "temperature_f": temp_f,
        "steps": int(steps) if steps is not None else None,
        "calories": round(calories, 2) if calories is not None else None,
        "sleep_duration": int(sleep_duration) if sleep_duration is not None else None,
        "sleep_duration_sec": int(sleep_sec) if sleep_sec is not None else None,
        "battery_level": int(round(battery)) if battery is not None else None,
        "systolic": int(round(systolic)) if systolic is not None else None,
        "diastolic": int(round(diastolic)) if diastolic is not None else None,
        "bp_estimated": coerce_bool(raw.get("bp_estimated")),
        "fall_alert": coerce_bool(raw.get("fall_alert")),
        "risk_level": risk_str,
        "raw_risk": risk_raw,
        "raw_risk_level": risk_raw,        # legacy alias
        "stress_label": stress_str,
        "raw_stress": stress_raw,
        "raw_stress_label": stress_raw,    # legacy alias
        "source": source,
        "is_simulated": is_simulated,
        "timestamp": raw.get("timestamp"),
        "date_time": raw.get("date_time"),
        "device_status": status,
        "last_seen_seconds": last_seen,
        "used_freshness_basis": basis,
        "server_observed_last_seen_at": _iso(observed_last_seen_ms),
    }


def normalize_history(
    records: List[Dict[str, Any]],
    now_ms: int,
    source: str = "firebase",
    is_simulated: bool = False,
    uid: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Normalize a list of raw Firebase history records (oldest→newest).

    Records are sorted by timestamp when available. Invalid HR/SpO₂/temp within
    a record are nulled (per-field) but the record is kept, so charts can drop
    the bad points without losing the row.
    """
    out = [
        normalize_reading(
            r, now_ms, source=source, is_simulated=is_simulated, uid=uid
        )
        for r in records
        if isinstance(r, dict)
    ]

    def _ts(rec: Dict[str, Any]) -> float:
        v = rec.get("timestamp")
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    out.sort(key=_ts)
    return out
