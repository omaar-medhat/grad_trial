"""Token-based auth: verified ID-token uid is authoritative; demo fallback."""

from __future__ import annotations

import time

from backend.firebase_service import FirebaseService


def _reading(**over):
    base = {
        "heart_rate": 72, "spo2": 98, "temperature_c": 37.0,
        "timestamp": int(time.time() * 1000),
    }
    base.update(over)
    return base


def test_verify_id_token_none_without_admin_sdk():
    # Memory mode → no Admin SDK → cannot verify tokens.
    svc = FirebaseService(credentials_path=None, database_url=None)
    assert svc.verify_id_token("anything") is None


def test_valid_token_uid_is_authoritative(app, client, monkeypatch):
    fb = app.config["FIREBASE"]
    # Stand in for Admin SDK verification.
    monkeypatch.setattr(fb, "verify_id_token",
                        lambda t: "tokenUser" if t == "good-token" else None)
    fb.write_latest("tokenUser", _reading(heart_rate=81))
    fb.write_latest("someoneElse", _reading(heart_rate=55))

    # A different ?uid is supplied, but the verified token uid must win.
    d = client.get(
        "/api/vitals/latest?uid=someoneElse",
        headers={"Authorization": "Bearer good-token"},
    ).get_json()["data"]
    assert d["uid"] == "tokenUser"
    assert d["heart_rate"] == 81


def test_invalid_token_returns_401(app, client, monkeypatch):
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(fb, "verify_id_token", lambda t: None)
    r = client.get(
        "/api/vitals/latest", headers={"Authorization": "Bearer bad-token"},
    )
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_no_token_demo_fallback_uses_active_uid(app, client, monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", "demoX")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app.config["FIREBASE"].write_latest("demoX", _reading(heart_rate=66))
    d = client.get("/api/vitals/latest").get_json()["data"]
    assert d["uid"] == "demoX" and d["heart_rate"] == 66


def test_require_auth_blocks_missing_token(app, client, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "1")
    r = client.get("/api/vitals/latest")
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_require_auth_allows_valid_token(app, client, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "1")
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(fb, "verify_id_token",
                        lambda t: "authUser" if t == "ok" else None)
    fb.write_latest("authUser", _reading(heart_rate=77))
    d = client.get(
        "/api/vitals/latest", headers={"Authorization": "Bearer ok"},
    ).get_json()["data"]
    assert d["uid"] == "authUser" and d["heart_rate"] == 77


def test_bootstrap_creates_profile_and_goals(app, client, monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", "newUser")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    d = client.post("/api/auth/bootstrap", json={"name": "Asmaa"}).get_json()["data"]
    assert d["uid"] == "newUser"
    assert d["created_profile"] is True and d["created_goals"] is True
    assert d["profile"]["name"] == "Asmaa"
    assert d["profile"]["activity"] == "unknown"
    assert d["goals"] == {"steps": 5000, "calories": 500, "sleep": 8}
    # Reports which backend actually wrote + that it succeeded.
    assert d["write_backend"] == "memory" and d["write_ok"] is True
    # No fake telemetry/history is created.
    fb = app.config["FIREBASE"]
    assert fb.read_latest("newUser") is None
    assert fb.read_history("newUser") == []


def test_bootstrap_500_when_write_does_not_persist(app, client, monkeypatch):
    # Simulate a real-Firebase backend that cannot write (e.g. REST read-only):
    # bootstrap must FAIL loudly, not pretend the user was created.
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", "wf")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(fb, "_mode", "rest")
    monkeypatch.setattr(fb, "read_profile", lambda u: None)
    monkeypatch.setattr(fb, "read_goals", lambda u: None)
    monkeypatch.setattr(fb, "write_profile", lambda u, d: False)
    monkeypatch.setattr(fb, "write_goals", lambda u, d: False)
    r = client.post("/api/auth/bootstrap", json={})
    assert r.status_code == 500
    body = r.get_json()
    assert body["error"]["code"] == "FIREBASE_WRITE_FAILED"
    assert body["error"]["details"]["write_backend"] == "rest"
    assert body["error"]["details"]["write_ok"] is False


def test_bootstrap_check_reports_existence(app, client, monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", "chk")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app.config["FIREBASE"].write_profile("chk", {"name": "x"})
    d = client.get("/api/auth/bootstrap/check").get_json()["data"]
    assert d["uid"] == "chk"
    assert d["profile_exists"] is True
    assert d["goals_exists"] is False
    assert d["latest_telemetry_exists"] is False
    assert d["write_backend"] == "memory"


def test_bootstrap_is_idempotent_and_preserves_data(app, client, monkeypatch):
    monkeypatch.setenv("FIREBASE_ACTIVE_UID", "u2")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    fb = app.config["FIREBASE"]
    fb.write_profile("u2", {"name": "Existing", "age": 30})
    fb.write_goals("u2", {"steps": 12345, "calories": 700, "sleep": 7})

    d = client.post("/api/auth/bootstrap", json={"name": "Override?"}).get_json()["data"]
    assert d["created_profile"] is False and d["created_goals"] is False
    # Existing data preserved, not overwritten.
    assert d["profile"]["name"] == "Existing"
    assert d["goals"]["steps"] == 12345


def test_bootstrap_uses_token_uid_not_body(app, client, monkeypatch):
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(fb, "verify_id_token",
                        lambda t: "tokU" if t == "ok" else None)
    monkeypatch.setattr(fb, "verify_id_token_claims",
                        lambda t: {"uid": "tokU", "email": "a@b.com"} if t == "ok" else None)
    d = client.post(
        "/api/auth/bootstrap",
        json={"uid": "attacker", "name": "X"},
        headers={"Authorization": "Bearer ok"},
    ).get_json()["data"]
    assert d["uid"] == "tokU"           # verified token uid, NOT body uid
    assert d["profile"]["email"] == "a@b.com"


def test_bootstrap_invalid_token_401(app, client, monkeypatch):
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(fb, "verify_id_token", lambda t: None)
    r = client.post("/api/auth/bootstrap", json={},
                    headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401


def test_chat_uses_token_uid(app, client, monkeypatch):
    fb = app.config["FIREBASE"]
    monkeypatch.setattr(fb, "verify_id_token",
                        lambda t: "chatUser" if t == "tok" else None)
    fb.write_latest("chatUser", _reading(heart_rate=72))
    d = client.post(
        "/api/chat",
        json={"message": "what is my heart rate right now"},
        headers={"Authorization": "Bearer tok"},
    ).get_json()["data"]
    assert "72" in d["response"]
