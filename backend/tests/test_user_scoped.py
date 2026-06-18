"""User-scoped Firebase paths + new schema (risk/stress strings, etc.)."""

from __future__ import annotations

import time

import pytest

UID = "eKjIbPbsi5SqLX5HP8a6CtabtPm2"


def _raw(**over):
    base = {
        "battery_level": 81, "bp_estimated": True, "calories": 8.33,
        "diastolic": 73, "fall_alert": False, "heart_rate": 72,
        "risk": "Low", "sleep_duration": 38, "spo2": 98, "steps": 265,
        "stress": "Normal", "systolic": 128, "temperature_c": 37,
        "temperature_f": 98.6, "timestamp": int(time.time() * 1000),
    }
    base.update(over)
    return base


def _seed_user(app, uid, latest=None, history=None, profile=None, goals=None):
    fb = app.config["FIREBASE"]
    if latest is not None:
        fb.write_latest(uid, latest)
    for h in history or []:
        fb.push_history(uid, h)
    if profile is not None:
        fb._memory.set_node(uid, "profile", profile)
    if goals is not None:
        fb._memory.set_node(uid, "goals", goals)


@pytest.fixture()
def active(monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", UID)
    return UID


# ---- active uid resolution ------------------------------------------------
def test_active_uid_from_env(app, client, active):
    _seed_user(app, UID, latest=_raw())
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["uid"] == UID
    assert d["available"] is True
    assert d["source"] == "firebase"


def test_active_uid_query_overrides_env(app, client, active):
    _seed_user(app, "other", latest=_raw(heart_rate=99))
    d = client.get("/api/vitals/latest?uid=other").get_json()["data"]
    assert d["uid"] == "other" and d["heart_rate"] == 99


def test_active_uid_fallback_to_first_user_with_latest(app, client, monkeypatch):
    # No query, no env → first /users child that has latest_telemetry.
    monkeypatch.delenv("FIREBASE_ACTIVE_UID", raising=False)
    _seed_user(app, "userA", latest=_raw(heart_rate=66))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["uid"] == "userA" and d["heart_rate"] == 66


def test_unavailable_when_no_user(app, client, monkeypatch):
    monkeypatch.delenv("FIREBASE_ACTIVE_UID", raising=False)
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["available"] is False
    assert d["source"] == "firebase"
    assert d["is_simulated"] is False


# ---- new-schema normalization --------------------------------------------
def test_new_fields_normalized(app, client, active):
    _seed_user(app, UID, latest=_raw())
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["heart_rate"] == 72 and d["spo2"] == 98
    assert d["temperature_c"] == 37.0           # preferred over F
    assert d["temperature_f"] == 98.6
    assert d["systolic"] == 128 and d["diastolic"] == 73
    assert d["bp_estimated"] is True
    assert d["sleep_duration"] == 38
    assert d["risk_level"] == "Low" and d["raw_risk"] == "Low"
    assert d["stress_label"] == "Normal" and d["raw_stress"] == "Normal"
    assert d["fall_alert"] is False


def test_temperature_f_converted_when_c_missing(app, client, active):
    _seed_user(app, UID, latest=_raw(temperature_c=None, temperature_f=98.6))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["temperature_c"] == 37.0


def test_temperature_c_preferred_over_f(app, client, active):
    # C says 37, F says 50 — the valid Celsius reading wins.
    _seed_user(app, UID, latest=_raw(temperature_c=37, temperature_f=50.0))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["temperature_c"] == 37.0


def test_device_connected_when_timestamp_recent(app, client, active):
    _seed_user(app, UID, latest=_raw(timestamp=int(time.time() * 1000)))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["device_status"] == "connected"


# ---- history / profile / goals -------------------------------------------
def test_history_reads_user_history(app, client, active):
    now = int(time.time() * 1000)
    _seed_user(app, UID, history=[
        _raw(heart_rate=70, timestamp=now - 2000),
        _raw(heart_rate=75, timestamp=now),
    ])
    d = client.get("/api/vitals/history").get_json()["data"]
    assert d["uid"] == UID and d["count"] == 2
    assert d["readings"][-1]["heart_rate"] == 75


def test_profile_and_goals_endpoints(app, client, active):
    _seed_user(app, UID, latest=_raw(),
               profile={"name": "asmaa", "age": 22},
               goals={"steps": 10000, "calories": 500, "sleep": 8})
    prof = client.get("/api/profile").get_json()["data"]
    goals = client.get("/api/goals").get_json()["data"]
    assert prof["profile"]["name"] == "asmaa"
    assert goals["goals"]["steps"] == 10000


def test_root_path_not_used_in_firebase_mode(app, client, active):
    # Seeding the OLD root node must NOT surface — only user-scoped is read.
    app.config["FIREBASE"].write_root_latest(_raw(heart_rate=123))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["available"] is False  # nothing under /users/{uid}


def test_chat_uses_user_scoped_latest(app, client, active):
    _seed_user(app, UID, latest=_raw(heart_rate=72))
    d = client.post(
        "/api/chat", json={"message": "what is my heart rate right now"}
    ).get_json()["data"]
    assert "72" in d["response"]
    assert d["telemetry_origin"] == "firebase_store"
    assert d["telemetry_source"] == "firebase"
