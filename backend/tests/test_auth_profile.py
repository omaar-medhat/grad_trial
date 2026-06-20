"""Tests for signup/login bootstrap, profile completeness, and onboarding gating.

These run in the default test environment (memory Firebase mode, REQUIRE_AUTH
off), so an authenticated user is simulated with `?uid=...` (dev fallback). The
invalid-token case sends a Bearer header, which the backend rejects with 401.
"""

from __future__ import annotations

REQUIRED = {"name", "age", "gender", "height_cm", "weight_kg", "activity"}

COMPLETE = {
    "name": "Sara Ahmed",
    "age": 22,
    "gender": "female",
    "height_cm": 170,
    "weight_kg": 65,
    "activity": "moderate",
}


def test_bootstrap_new_user_creates_minimal_incomplete(client):
    r = client.post("/api/auth/bootstrap?uid=u_new1")
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert d["created_profile"] is True
    assert d["created_goals"] is True
    assert d["profile_complete"] is False
    assert d["needs_onboarding"] is True
    assert REQUIRED <= set(d["missing_fields"])
    # default goals were created
    assert d["goals"]["steps"] == 5000


def test_bootstrap_creates_no_telemetry_or_history(client):
    client.post("/api/auth/bootstrap?uid=u_new2")
    d = client.get("/api/auth/bootstrap/check?uid=u_new2").get_json()["data"]
    assert d["profile_exists"] is True
    assert d["goals_exists"] is True
    assert d["latest_telemetry_exists"] is False


def test_profile_me_completes_profile(client):
    client.post("/api/auth/bootstrap?uid=u3")
    r = client.put("/api/profile/me?uid=u3", json=COMPLETE)
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert d["profile_complete"] is True
    assert d["needs_onboarding"] is False
    assert d["profile"]["onboarding_completed"] is True
    assert d["profile"]["profile_complete"] is True
    # /api/me reflects completion afterwards
    m = client.get("/api/me?uid=u3").get_json()["data"]
    assert m["profile_complete"] is True
    assert m["needs_onboarding"] is False
    assert m["missing_fields"] == []


def test_login_bootstrap_complete_profile_no_onboarding(client):
    client.post("/api/auth/bootstrap?uid=u4")
    client.put("/api/profile/me?uid=u4", json=COMPLETE)
    # Simulate a later login: bootstrap again.
    d = client.post("/api/auth/bootstrap?uid=u4").get_json()["data"]
    assert d["created_profile"] is False  # preserved, not recreated
    assert d["profile_complete"] is True
    assert d["needs_onboarding"] is False


def test_login_bootstrap_incomplete_profile_needs_onboarding(client):
    client.post("/api/auth/bootstrap?uid=u5")  # minimal, incomplete
    d = client.post("/api/auth/bootstrap?uid=u5").get_json()["data"]
    assert d["needs_onboarding"] is True
    assert d["profile_complete"] is False


def test_bootstrap_does_not_overwrite_existing(client):
    client.post("/api/auth/bootstrap?uid=u6")
    client.put("/api/profile/me?uid=u6", json={**COMPLETE, "name": "Original"})
    d = client.post("/api/auth/bootstrap?uid=u6").get_json()["data"]
    assert d["created_profile"] is False
    assert d["created_goals"] is False
    assert d["profile"]["name"] == "Original"


def test_me_reports_missing_fields(client):
    client.post("/api/auth/bootstrap?uid=u7")
    m = client.get("/api/me?uid=u7").get_json()["data"]
    assert m["needs_onboarding"] is True
    assert set(m["missing_fields"]) == REQUIRED


def test_invalid_token_returns_401(client):
    r = client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_profile_me_validation_rejects_bad_fields(client):
    client.post("/api/auth/bootstrap?uid=u8")
    r = client.put("/api/profile/me?uid=u8", json={
        "name": "", "age": -5, "gender": "x",
        "height_cm": 0, "weight_kg": 0, "activity": "nope",
    })
    assert r.status_code == 400
    error = r.get_json()["error"]
    assert error["code"] == "INVALID_INPUT"
    assert REQUIRED <= set(error["details"]["invalid_fields"])


def test_legacy_user_with_required_fields_is_complete(app, client):
    # Seed a legacy profile (required fields present, no profile_complete flag).
    fb = app.config["FIREBASE"]
    fb.write_profile("u_legacy", {
        "name": "Old User", "age": 40, "gender": "male",
        "height_cm": 180, "weight_kg": 80, "activity": "active",
        "created_at": "2020-01-01T00:00:00Z",
    })
    d = client.post("/api/auth/bootstrap?uid=u_legacy").get_json()["data"]
    assert d["profile_complete"] is True
    assert d["needs_onboarding"] is False


def test_legacy_height_weight_aliases_accepted(app, client):
    fb = app.config["FIREBASE"]
    fb.write_profile("u_alias", {
        "name": "Alias", "age": 30, "gender": "female",
        "height": 165, "weight": 60, "activity": "light",
    })
    d = client.get("/api/me?uid=u_alias").get_json()["data"]
    assert d["profile_complete"] is True
    assert d["needs_onboarding"] is False


# --- The real-Firebase shape: existing user must NOT be re-onboarded ---------
# Real /users/{uid}/profile has: activity, age, created_at, email, gender,
# height_cm, name, uid, updated_at, weight_kg — and NO profile_complete flag.
REAL_SHAPE = {
    "uid": "u_real",
    "name": "Medhat",
    "age": 24,
    "gender": "Male",                 # non-canonical spelling on purpose
    "height_cm": 178,
    "weight_kg": 74,
    "activity": "Moderately active",  # NOT in the strict enum on purpose
    "email": "user@example.com",
    "created_at": "2024-05-01T10:00:00Z",
    "updated_at": "2024-05-01T10:00:00Z",
}


def test_real_shape_profile_complete_without_flag(app, client):
    fb = app.config["FIREBASE"]
    fb.write_profile("u_real", dict(REAL_SHAPE))
    d = client.get("/api/me?uid=u_real").get_json()["data"]
    assert d["profile_complete"] is True
    assert d["needs_onboarding"] is False
    assert d["missing_fields"] == []


def test_bootstrap_backfills_completion_flags(app, client):
    fb = app.config["FIREBASE"]
    fb.write_profile("u_backfill", dict(REAL_SHAPE, uid="u_backfill"))
    d = client.post("/api/auth/bootstrap?uid=u_backfill").get_json()["data"]
    assert d["profile_complete"] is True
    assert d["needs_onboarding"] is False
    # Flags were backfilled (without overwriting existing values).
    saved = fb.read_profile("u_backfill")
    assert saved["profile_complete"] is True
    assert saved["onboarding_completed"] is True
    assert "updated_at" in saved
    assert saved["name"] == "Medhat"          # user value preserved
    assert saved["activity"] == "Moderately active"


def test_missing_height_cm_needs_onboarding(app, client):
    fb = app.config["FIREBASE"]
    p = dict(REAL_SHAPE, uid="u_no_h")
    p.pop("height_cm")
    fb.write_profile("u_no_h", p)
    d = client.get("/api/me?uid=u_no_h").get_json()["data"]
    assert d["needs_onboarding"] is True
    assert "height_cm" in d["missing_fields"]


def test_missing_weight_kg_needs_onboarding(app, client):
    fb = app.config["FIREBASE"]
    p = dict(REAL_SHAPE, uid="u_no_w")
    p.pop("weight_kg")
    fb.write_profile("u_no_w", p)
    d = client.get("/api/me?uid=u_no_w").get_json()["data"]
    assert d["needs_onboarding"] is True
    assert "weight_kg" in d["missing_fields"]
