"""
PulseGuard AI - Data-source resolver (single source of truth selection).

Decides WHERE the live telemetry comes from and returns it already normalized
into the canonical contract (see ``telemetry_contract``). This is the only
place that chooses Firebase vs. simulator, so the rule "Firebase is the
real-time source of truth; never silently fall back to the simulator" lives in
exactly one function.

User-scoped paths (the bracelet now publishes per user):
    /users/{uid}/latest_telemetry        current raw reading (source of truth)
    /users/{uid}/history/{push_id}       timestamped raw readings

Config flag (env ``DATA_SOURCE``):
    firebase   use Firebase only for the active uid. If latest_telemetry is
               missing, fall back to the last valid history record. If nothing
               exists, return an explicit unavailable/disconnected state —
               NEVER the simulator. (Optional legacy root fallback only when
               ENABLE_LEGACY_ROOT_PATHS=1.)
    simulator  use the in-process simulator only (explicit demo / testing).
    auto       prefer Firebase; else simulator (clearly labelled).

Default = ``firebase``.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .telemetry_contract import normalize_history, normalize_reading


def data_source_mode() -> str:
    """Return the configured DATA_SOURCE: firebase | simulator | auto."""
    mode = (os.environ.get("DATA_SOURCE") or "firebase").strip().lower()
    if mode not in ("firebase", "simulator", "auto"):
        mode = "firebase"
    return mode


def _legacy_root_enabled() -> bool:
    return (os.environ.get("ENABLE_LEGACY_ROOT_PATHS") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _now_ms() -> int:
    from . import clock
    return clock.now_ms()


def _is_usable(raw: Any) -> bool:
    """A raw reading is usable if it's a dict with a numeric timestamp and at
    least one core vital present and numeric."""
    if not isinstance(raw, dict):
        return False
    try:
        float(raw.get("timestamp"))
    except (TypeError, ValueError):
        return False
    for key in ("heart_rate", "spo2", "temperature_c", "temperature_f"):
        v = raw.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return True
    return False


def _last_usable(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    usable = [r for r in records if _is_usable(r)]
    if not usable:
        return None
    return max(usable, key=lambda r: float(r.get("timestamp", 0)))


def _simulator_reading() -> Dict[str, Any]:
    """One simulator reading, shaped like the raw schema so the same normalizer
    applies. Imported lazily to keep simulator code out of the Firebase path."""
    from .simulator import generate_reading

    r = generate_reading()
    return {
        "heart_rate": r["heart_rate"],
        "spo2": r["spo2"],
        "temperature_c": r["temperature_c"],
        "steps": r["steps"],
        "calories": r["calories"],
        "sleep_duration": r["sleep_duration_sec"],
        "battery_level": r["battery_level"],
        "timestamp": r["timestamp"],
    }


def resolve_latest(
    firebase: Any, uid: Optional[str], now_ms: Optional[int] = None
) -> Dict[str, Any]:
    """Return the current normalized reading for ``uid`` per the configured
    priority. ``uid`` is the already-resolved active user id.

    Priority (DATA_SOURCE=firebase or auto):
        1. /users/{uid}/latest_telemetry if usable
        2. last usable /users/{uid}/history record
        3. (optional) legacy root /latest_telemetry if ENABLE_LEGACY_ROOT_PATHS
        4. (auto only) simulator, clearly labelled
        5. explicit unavailable/disconnected state
    """
    now_ms = now_ms if now_ms is not None else _now_ms()
    mode = data_source_mode()

    if mode == "simulator":
        return normalize_reading(
            _simulator_reading(), now_ms,
            source="simulator", is_simulated=True, uid=uid,
        )

    if not uid:
        return _unavailable(uid)

    latest = firebase.read_latest(uid)
    observed = firebase.observe_latest(uid, latest)
    if _is_usable(latest):
        return normalize_reading(
            latest, now_ms, source="firebase",
            observed_last_seen_ms=observed, uid=uid,
        )

    history = firebase.read_history(uid, limit=200)
    last = _last_usable(history or [])
    if last is not None:
        out = normalize_reading(
            last, now_ms, source="firebase",
            observed_last_seen_ms=observed, uid=uid,
        )
        out["from_history_fallback"] = True
        return out

    if _legacy_root_enabled():
        root = firebase.read_root_latest()
        if _is_usable(root):
            out = normalize_reading(root, now_ms, source="firebase", uid=uid)
            out["legacy_root"] = True
            return out

    if mode == "auto":
        return normalize_reading(
            _simulator_reading(), now_ms,
            source="simulator", is_simulated=True, uid=uid,
        )

    return _unavailable(uid)


def _unavailable(uid: Optional[str]) -> Dict[str, Any]:
    return {
        "available": False,
        "uid": uid,
        "source": "firebase",
        "is_simulated": False,
        "device_status": "disconnected",
        "last_seen_seconds": None,
        "used_freshness_basis": "missing",
        "server_observed_last_seen_at": None,
        "timestamp": None,
    }


def resolve_history(
    firebase: Any, uid: Optional[str], limit: int = 200,
    now_ms: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Return (normalized_history, source_label) for ``uid``."""
    now_ms = now_ms if now_ms is not None else _now_ms()
    mode = data_source_mode()

    if mode == "simulator":
        return (
            normalize_history(
                [_simulator_reading()], now_ms,
                source="simulator", is_simulated=True, uid=uid,
            ),
            "simulator",
        )

    raw = firebase.read_history(uid, limit=limit) if uid else []
    if raw:
        return (
            normalize_history(raw, now_ms, source="firebase", uid=uid),
            "firebase",
        )

    if _legacy_root_enabled():
        root_hist = firebase.read_root_history(limit=limit) or []
        if root_hist:
            return (
                normalize_history(root_hist, now_ms, source="firebase", uid=uid),
                "firebase",
            )

    if mode == "auto":
        return (
            normalize_history(
                [_simulator_reading()], now_ms,
                source="simulator", is_simulated=True, uid=uid,
            ),
            "simulator",
        )

    return [], "firebase"
