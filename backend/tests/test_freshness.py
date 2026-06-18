"""Device freshness: observed-change vs. sensor-timestamp basis.

These pin the fix for "Firebase is changing but the app says disconnected":
a misaligned device clock must not make a live, changing feed look offline.
"""

from __future__ import annotations

import time

import pytest

from backend.firebase_service import FirebaseService
from backend.telemetry_contract import resolve_device_status

NOW = 1_700_000_000_000
ACTIVE = "u1"


@pytest.fixture(autouse=True)
def _active_uid(monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", ACTIVE)


def _raw(**over):
    base = {
        "battery_level": 82, "calories": 0.48, "diastolic": 80,
        "fall_alert": False, "heart_rate": 72, "risk_level": 1,
        "sleep_duration_sec": 28, "spo2": 98, "steps": 12,
        "stress_label": 1, "systolic": 120, "temperature_f": 98.6,
        "timestamp": NOW,
    }
    base.update(over)
    return base


# ---- pure resolve_device_status -------------------------------------------
def test_recent_sensor_timestamp_is_connected():
    status, secs, basis = resolve_device_status(NOW - 3_000, None, NOW)
    assert status == "connected" and basis == "sensor_timestamp"


def test_misaligned_old_timestamp_but_observed_now_is_connected():
    # Sensor clock is ~1h behind, but the payload changed on the server "now".
    status, secs, basis = resolve_device_status(NOW - 3_700_000, NOW, NOW)
    assert status == "connected"
    assert basis == "observed_change"
    assert secs == 0.0


def test_both_old_is_disconnected():
    status, _secs, _basis = resolve_device_status(
        NOW - 3_700_000, NOW - 120_000, NOW
    )
    assert status == "disconnected"


def test_observed_change_ages_into_stale_then_disconnected():
    assert resolve_device_status(0, NOW - 30_000, NOW)[0] == "stale"
    assert resolve_device_status(0, NOW - 90_000, NOW)[0] == "disconnected"


def test_far_future_sensor_timestamp_is_ignored():
    # A device clock running ahead must not pin us to connected forever.
    status, _secs, basis = resolve_device_status(
        NOW + 3_700_000, NOW - 90_000, NOW
    )
    assert status == "disconnected" and basis == "observed_change"


def test_no_signal_is_unknown():
    assert resolve_device_status(0, None, NOW) == ("unknown", None, "missing")


# ---- observe_latest change detection --------------------------------------
def test_observe_latest_first_sight_does_not_confirm_fresh():
    svc = FirebaseService(credentials_path=None, database_url=None)
    # First sighting of a payload → unconfirmed (None): we can't tell a fresh
    # reading from a stale one left over while the sensor was off.
    assert svc.observe_latest(ACTIVE, _raw()) is None


def test_observe_latest_marks_fresh_on_change():
    svc = FirebaseService(credentials_path=None, database_url=None)
    svc.observe_latest(ACTIVE, _raw(heart_rate=72))          # first sight
    before = int(time.time() * 1000) - 1
    seen = svc.observe_latest(ACTIVE, _raw(heart_rate=73))   # genuine change
    assert seen is not None and seen >= before
    # Identical payload again → no new change, same observed time.
    assert svc.observe_latest(ACTIVE, _raw(heart_rate=73)) == seen
    # A different user is tracked independently.
    assert svc.observe_latest("other", _raw(heart_rate=99)) is None


# ---- end-to-end through the API -------------------------------------------
def _seed(app, latest):
    app.config["FIREBASE"].write_latest(ACTIVE, latest)


def test_live_feed_becomes_connected_after_a_change(app, client):
    old = int(time.time() * 1000) - 3_700_000  # misaligned device clock
    _seed(app, _raw(timestamp=old, heart_rate=72))
    d1 = client.get("/api/vitals/latest").get_json()["data"]
    # First read: change not yet witnessed → sensor basis → disconnected.
    assert d1["device_status"] == "disconnected"
    assert d1["used_freshness_basis"] == "sensor_timestamp"

    # Sensor pushes a new reading (still a bad timestamp) → witnessed change.
    _seed(app, _raw(timestamp=old + 1000, heart_rate=73))
    d2 = client.get("/api/vitals/latest").get_json()["data"]
    assert d2["heart_rate"] == 73
    assert d2["device_status"] == "connected"
    assert d2["used_freshness_basis"] == "observed_change"


def test_vitals_latest_has_no_store_headers(client):
    r = client.get("/api/vitals/latest")
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_device_status_reports_freshness_basis(app, client):
    _seed(app, _raw())
    client.get("/api/vitals/latest")                 # first sight
    app.config["FIREBASE"].write_latest(ACTIVE, _raw(heart_rate=74))
    client.get("/api/vitals/latest")                 # witness change
    d = client.get("/api/device/status").get_json()["data"]
    assert d["used_freshness_basis"] == "observed_change"
    assert d["device_status"] == "connected"
    assert d["latest_heart_rate"] == 74
    assert d["server_observed_last_seen_at"] is not None


def test_firebase_mode_never_uses_simulator(app, client):
    # DATA_SOURCE defaults to firebase; with no data, source stays firebase
    # and is_simulated is false — never a silent simulator fallback.
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["source"] == "firebase"
    assert d["is_simulated"] is False


def test_unavailable_response_is_consistent(app, client):
    # No Firebase data at all → explicit unavailable contract with a basis.
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["available"] is False
    assert d["device_status"] == "disconnected"
    assert d["used_freshness_basis"] == "missing"
