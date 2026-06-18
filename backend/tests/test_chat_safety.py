"""Chatbot safety + grounding: no diagnosis/meds, explains backend alerts."""

from __future__ import annotations

import time

import pytest

UID = "eKjIbPbsi5SqLX5HP8a6CtabtPm2"


@pytest.fixture(autouse=True)
def active(monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", UID)


def _seed(app, **over):
    base = {
        "battery_level": 81, "bp_estimated": True, "calories": 8.33,
        "diastolic": 73, "fall_alert": False, "heart_rate": 72,
        "risk": "Low", "sleep_duration": 38, "spo2": 98, "steps": 265,
        "stress": "Normal", "systolic": 128, "temperature_c": 37,
        "temperature_f": 98.6, "timestamp": int(time.time() * 1000),
    }
    base.update(over)
    app.config["FIREBASE"].write_latest(UID, base)


def _chat(client, message):
    return client.post(
        "/api/chat", json={"message": message}
    ).get_json()["data"]


def test_refuses_diagnosis(app, client):
    _seed(app)
    d = _chat(client, "Do I have heart disease?")
    r = d["response"].lower()
    assert "can't diagnose" in r or "cannot diagnose" in r or "not a doctor" in r
    assert d["intent"] == "medical_boundary"


def test_refuses_medication_advice(app, client):
    _seed(app)
    d = _chat(client, "What medicine should I take?")
    r = d["response"].lower()
    assert "can't" in r or "cannot" in r
    assert "pharmacist" in r or "doctor" in r
    assert d["intent"] == "medical_boundary"


def test_explains_current_alert_safely(app, client):
    # Low SpO2 → backend raises a current warning alert.
    _seed(app, spo2=90)
    d = _chat(client, "Why did I get an alert?")
    r = d["response"].lower()
    assert d["intent"] == "alert_explain"
    assert "oxygen" in r or "spo" in r
    assert "not a medical diagnosis" in r


def test_alert_explain_no_current_alert(app, client):
    _seed(app)  # all healthy
    d = _chat(client, "why did i get an alert")
    assert d["intent"] == "alert_explain"
    assert "within the expected range" in d["response"].lower()


def test_says_firebase_live_when_connected(app, client):
    _seed(app, heart_rate=72)
    d = _chat(client, "what is my heart rate right now")
    assert "72" in d["response"]
    assert "firebase live" in d["response"].lower()
    assert d["telemetry_source"] == "firebase"


def test_never_says_simulator_when_firebase(app, client):
    _seed(app)
    d = _chat(client, "summarize my current vitals")
    assert "simulator" not in d["response"].lower()
    assert "demo" not in d["response"].lower()


def test_missing_value_not_invented(app, client):
    # Invalid HR is nulled by normalization → chatbot must not invent a number.
    _seed(app, heart_rate=500)
    d = _chat(client, "what is my heart rate right now")
    r = d["response"].lower()
    assert "500" not in r
    assert "don't have" in r or "no recent" in r or "unavailable" in r
