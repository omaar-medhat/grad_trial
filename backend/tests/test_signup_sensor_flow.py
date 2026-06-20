"""Signup-with-profile (one-screen) + live sensor (device pairing) flow tests.

Run in the default test env (memory Firebase mode, REQUIRE_AUTH off): an
authenticated user is simulated with ?uid=...; device pairing is simulated by
monkeypatching read_device_assigned_uid.
"""

from __future__ import annotations

COMPLETE_PROFILE = {
    "name": "Sara Ahmed", "age": 22, "gender": "female",
    "height_cm": 170, "weight_kg": 65, "activity": "moderate",
}

ARDUINO = {
    "device_id": "esp32_1", "heart_rate": 75, "spo2": 97,
    "temperature": 98.6, "steps": 1200, "sleep_duration": 3600,
    "battery_level": 85, "fall_alert": False,
}


# ---------------------------------------------------------------- signup -----
def test_signup_with_profile_saves_complete(client):
    r = client.post("/api/auth/bootstrap?uid=su1", json={"profile": COMPLETE_PROFILE})
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert d["created_profile"] is True
    assert d["created_goals"] is True
    assert d["profile_complete"] is True
    assert d["needs_onboarding"] is False
    assert d["missing_fields"] == []
    assert d["profile"]["name"] == "Sara Ahmed"
    assert d["profile"]["onboarding_completed"] is True
    assert d["write_ok"] is True


def test_signup_creates_no_telemetry_or_history(app, client):
    client.post("/api/auth/bootstrap?uid=su2", json={"profile": COMPLETE_PROFILE})
    fb = app.config["FIREBASE"]
    assert fb.read_latest("su2") is None
    assert fb.read_history("su2") == []


def test_bootstrap_invalid_profile_returns_400(client):
    r = client.post("/api/auth/bootstrap?uid=su3", json={"profile": {
        "name": "", "age": -1, "gender": "x",
        "height_cm": 0, "weight_kg": 0, "activity": "nope",
    }})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "INVALID_INPUT"


def test_bootstrap_without_profile_body_preserves_existing(client):
    client.post("/api/auth/bootstrap?uid=su4", json={"profile": COMPLETE_PROFILE})
    d = client.post("/api/auth/bootstrap?uid=su4", json={}).get_json()["data"]
    assert d["created_profile"] is False
    assert d["profile"]["name"] == "Sara Ahmed"
    assert d["needs_onboarding"] is False


# --------------------------------------------------------------- sensor ------
def test_sensor_writes_under_explicit_uid(app, client):
    r = client.post("/update_telemetry", json={**ARDUINO, "user_id": "sensor_u1"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "success"
    fb = app.config["FIREBASE"]
    latest = fb.read_latest("sensor_u1")
    assert latest is not None
    assert latest["heart_rate"] == 75
    assert latest["source"] == "real_bracelet"
    assert latest["temperature_c"] == 37.0  # 98.6F -> 37.0C
    assert fb.read_history("sensor_u1")  # history pushed


def test_sensor_uses_device_pairing(app, client, monkeypatch):
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(
        fb, "read_device_assigned_uid",
        lambda d: "paired_u" if d == "esp32_1" else None,
    )
    r = client.post("/update_telemetry", json=ARDUINO)  # no user_id
    assert r.status_code == 200
    assert fb.read_latest("paired_u") is not None


def test_sensor_no_target_user_returns_400(client, monkeypatch):
    monkeypatch.delenv("FIREBASE_ACTIVE_UID", raising=False)
    r = client.post("/update_telemetry", json={**ARDUINO, "device_id": "unpaired"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "NO_TARGET_USER"


def test_sensor_write_failure_returns_500(app, client, monkeypatch):
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(fb, "write_latest", lambda u, t: False)
    r = client.post("/update_telemetry", json={**ARDUINO, "user_id": "wf_u"})
    assert r.status_code == 500
    assert r.get_json()["error"]["code"] == "FIREBASE_WRITE_FAILED"


# ----------------------------------------------------- device status ---------
def test_fresh_telemetry_device_available(client):
    client.post("/update_telemetry", json={**ARDUINO, "user_id": "fresh_u"})
    d = client.get("/api/device/status?uid=fresh_u").get_json()["data"]
    assert d["available"] is True
    assert d["device_status"] in ("connected", "stale")


def test_complete_profile_no_telemetry_is_not_onboarding(app, client):
    # Profile complete but NO sensor data → dashboard allowed (no onboarding),
    # and device status reflects "no data", NOT "profile incomplete".
    client.post("/api/auth/bootstrap?uid=nd_u", json={"profile": COMPLETE_PROFILE})
    me = client.get("/api/me?uid=nd_u").get_json()["data"]
    assert me["needs_onboarding"] is False
    ds = client.get("/api/device/status?uid=nd_u").get_json()["data"]
    assert ds["available"] is False
    assert ds["device_status"] in ("disconnected", "unknown", "unavailable", None)
