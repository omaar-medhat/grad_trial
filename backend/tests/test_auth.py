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
    d = client.post("/api/auth/bootstrap", json={}).get_json()["data"]
    assert d["uid"] == "newUser"
    assert d["created_profile"] is True and d["created_goals"] is True
    # Bootstrap creates a MINIMAL profile that is intentionally incomplete —
    # required fields are filled later during onboarding (PUT /api/profile/me).
    assert d["profile_complete"] is False
    assert d["needs_onboarding"] is True
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


def test_signup_flow_creates_rtdb_profile_and_goals(app, client, monkeypatch):
    """End-to-end: signup → verified token → bootstrap creates /users/{uid}/profile + goals.
    
    This is the core flow:
    1. Mobile creates user in Firebase Auth (not simulated here, done by Firebase)
    2. Mobile calls bootstrap with a valid token
    3. Backend verifies token and creates profile/goals in RTDB
    4. Profile and goals are readable from RTDB, not fake telemetry
    """
    fb = app.config["FIREBASE"]
    new_uid = "user-signup-test-001"
    
    # Simulate: mobile calls bootstrap with a valid ID token for a new user.
    # In real flow, the token comes from Firebase Auth (not mocked here).
    monkeypatch.setattr(
        fb, "verify_id_token",
        lambda t: new_uid if t == "valid-token" else None
    )
    monkeypatch.setattr(
        fb, "verify_id_token_claims",
        lambda t: {
            "uid": new_uid,
            "email": "newuser@example.com",
            "email_verified": True,
        } if t == "valid-token" else None
    )
    
    # Before bootstrap: no profile or goals exist.
    assert fb.read_profile(new_uid) is None
    assert fb.read_goals(new_uid) is None
    assert fb.read_latest(new_uid) is None
    assert fb.read_history(new_uid) == []
    
    # Mobile sends bootstrap request with valid token.
    r = client.post(
        "/api/auth/bootstrap",
        json={},  # no body needed, uid comes from token
        headers={"Authorization": f"Bearer valid-token"},
    )
    assert r.status_code == 200
    
    data = r.get_json()["data"]
    
    # Verify response structure.
    assert data["uid"] == new_uid
    assert data["created_profile"] is True
    assert data["created_goals"] is True
    assert data["profile_complete"] is False  # bootstrap creates incomplete profile
    assert data["needs_onboarding"] is True   # so onboarding is needed
    assert data["write_backend"] == "memory"  # test uses in-memory mode
    assert data["write_ok"] is True
    assert len(data["missing_fields"]) == 6  # all 6 required fields missing
    
    # Verify profile structure.
    assert data["profile"]["uid"] == new_uid
    assert data["profile"]["email"] == "newuser@example.com"
    assert data["profile"]["name"] == ""  # empty, waiting for onboarding
    assert data["profile"]["profile_complete"] is False
    assert data["profile"]["onboarding_completed"] is False
    assert "created_at" in data["profile"]
    assert "updated_at" in data["profile"]
    
    # Verify goals structure.
    assert data["goals"] == {"steps": 5000, "calories": 500, "sleep": 8}
    
    # Verify RTDB has been updated: profile and goals exist.
    profile_in_db = fb.read_profile(new_uid)
    assert profile_in_db is not None
    assert profile_in_db["uid"] == new_uid
    assert profile_in_db["email"] == "newuser@example.com"
    
    goals_in_db = fb.read_goals(new_uid)
    assert goals_in_db is not None
    assert goals_in_db["steps"] == 5000
    
    # Verify bootstrap does NOT create fake telemetry/history.
    # These should only exist when the real bracelet writes data.
    assert fb.read_latest(new_uid) is None, "bootstrap should not create latest_telemetry"
    assert fb.read_history(new_uid) == [], "bootstrap should not create history"


def test_signup_bootstrap_with_invalid_token_returns_401(app, client, monkeypatch):
    """Invalid token → 401 UNAUTHORIZED, no profile created."""
    fb = app.config["FIREBASE"]
    
    monkeypatch.setattr(fb, "verify_id_token", lambda t: None)
    
    r = client.post(
        "/api/auth/bootstrap",
        json={},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_bootstrap_idempotent_on_second_call(app, client, monkeypatch):
    """Calling bootstrap twice with same token should be idempotent.
    
    Second call: profile/goals already exist, so created_profile/goals are False,
    but existing data is preserved.
    """
    fb = app.config["FIREBASE"]
    uid = "user-idempotent-test"
    
    monkeypatch.setattr(fb, "verify_id_token", lambda t: uid if t == "tok" else None)
    monkeypatch.setattr(
        fb, "verify_id_token_claims",
        lambda t: {"uid": uid, "email": "test@example.com"} if t == "tok" else None
    )
    
    # First bootstrap call.
    r1 = client.post("/api/auth/bootstrap", json={}, headers={"Authorization": "Bearer tok"})
    d1 = r1.get_json()["data"]
    assert d1["created_profile"] is True
    assert d1["created_goals"] is True
    
    # Update profile (user completes onboarding).
    fb.write_profile(uid, {
        **d1["profile"],
        "name": "Test User",
        "age": 25,
        "gender": "other",
        "height_cm": 170,
        "weight_kg": 75,
        "activity": "moderate",
    })
    
    # Second bootstrap call.
    r2 = client.post("/api/auth/bootstrap", json={}, headers={"Authorization": "Bearer tok"})
    d2 = r2.get_json()["data"]
    assert d2["uid"] == uid
    assert d2["created_profile"] is False  # already existed
    assert d2["created_goals"] is False    # already existed
    assert d2["profile_complete"] is True  # now complete
    assert d2["needs_onboarding"] is False # no onboarding needed
    # Existing profile data preserved.
    assert d2["profile"]["name"] == "Test User"
    assert d2["profile"]["age"] == 25
