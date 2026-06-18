"""Chatbot answers from the Firebase-backed normalized telemetry."""

from __future__ import annotations

import time


def _raw(**over):
    base = {
        "battery_level": 82, "calories": 0.48,
        "date_time": "2026-06-17 01:23:21", "diastolic": 80,
        "fall_alert": False, "heart_rate": 72, "risk_level": 1,
        "sleep_duration_sec": 28, "spo2": 98, "steps": 12,
        "stress_label": 1, "systolic": 120, "temperature_f": 98.6,
        "timestamp": int(time.time() * 1000),
    }
    base.update(over)
    return base


def _seed(app, latest, uid="fb-user"):
    # User-scoped: /users/{uid}/latest_telemetry — the chat resolves the same
    # uid from the request's user_id.
    app.config["FIREBASE"].write_latest(uid, latest)


def _chat(client, message, uid="fb-user"):
    return client.post(
        "/api/chat", json={"message": message, "user_id": uid}
    ).get_json()["data"]


def test_chat_current_hr_from_firebase(app, client):
    _seed(app, _raw(heart_rate=72))
    d = _chat(client, "what is my heart rate right now")
    assert "72" in d["response"]
    assert d["telemetry_origin"] == "firebase_store"
    assert d["telemetry_source"] == "firebase"


def test_chat_temperature_converted_to_celsius(app, client):
    _seed(app, _raw(temperature_f=98.6))
    d = _chat(client, "what is my temperature right now")
    assert "37" in d["response"]


def test_chat_blood_pressure_from_firebase(app, client):
    _seed(app, _raw(systolic=128, diastolic=84))
    d = _chat(client, "what is my blood pressure")
    assert "128/84" in d["response"]


def test_chat_fall_question_uses_fall_alert(app, client):
    _seed(app, _raw(fall_alert=False))
    d = _chat(client, "did i fall")
    assert "no fall" in d["response"].lower()


def test_chat_says_firebase_live_when_connected(app, client):
    _seed(app, _raw())
    d = _chat(client, "what is my heart rate right now")
    assert "firebase live" in d["response"].lower()


def test_chat_discloses_stale_reading(app, client):
    old = int(time.time() * 1000) - 40 * 1000
    _seed(app, _raw(timestamp=old))
    d = _chat(client, "what is my heart rate right now")
    assert "stale" in d["response"].lower()


def test_chat_discloses_disconnected_bracelet(app, client):
    old = int(time.time() * 1000) - 120 * 1000
    _seed(app, _raw(timestamp=old))
    d = _chat(client, "is my bracelet connected")
    assert "disconnect" in d["response"].lower()


def test_chat_battery_from_firebase(app, client):
    _seed(app, _raw(battery_level=42))
    d = _chat(client, "what is my battery right now")
    assert "42" in d["response"]
