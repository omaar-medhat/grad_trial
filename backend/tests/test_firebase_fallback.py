"""Verify the in-memory Firebase fallback fulfils the same contract as RTDB."""

from __future__ import annotations

from backend.firebase_service import FirebaseService


def test_fallback_when_no_credentials():
    svc = FirebaseService(credentials_path=None, database_url=None)
    assert svc.mode == "memory"
    assert svc.healthy()


def test_round_trip_latest():
    svc = FirebaseService(credentials_path="", database_url="")
    svc.write_latest("u1", {"heart_rate": 70, "timestamp": 1})
    assert svc.read_latest("u1") == {"heart_rate": 70, "timestamp": 1}
    assert svc.read_latest("never-seen-uid") is None


def test_history_push_and_read():
    svc = FirebaseService(credentials_path="", database_url="")
    for i in range(5):
        svc.push_history("u2", {"heart_rate": 70 + i, "timestamp": i})
    history = svc.read_history("u2", limit=3)
    assert len(history) == 3
    assert history[-1]["heart_rate"] == 74


def test_alerts_push_and_read():
    svc = FirebaseService(credentials_path="", database_url="")
    svc.push_alert("u3", {"risk_level": "high", "message": "x", "timestamp": 1})
    alerts = svc.read_alerts("u3")
    assert len(alerts) == 1
    assert alerts[0]["risk_level"] == "high"


def test_fallback_isolates_users():
    svc = FirebaseService(credentials_path="", database_url="")
    svc.write_latest("a", {"heart_rate": 1, "timestamp": 1})
    svc.write_latest("b", {"heart_rate": 2, "timestamp": 2})
    assert svc.read_latest("a")["heart_rate"] == 1
    assert svc.read_latest("b")["heart_rate"] == 2
