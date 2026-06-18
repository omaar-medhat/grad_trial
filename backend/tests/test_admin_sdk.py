"""Firebase Admin SDK mode + REST fallback + read-health reporting.

The real service-account file is never present in CI, so the Admin SDK is
exercised with a faked `firebase_admin` module (same code path) — proving mode
selection, user-scoped reads, and read-health tracking without secrets.
"""

from __future__ import annotations

import os
import subprocess
import sys
import types
import urllib.error
import urllib.request

from backend.firebase_service import FirebaseService

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fake_admin(store, cert_raises=False):
    fa = types.ModuleType("firebase_admin")
    fa._apps = {}
    fa.initialize_app = lambda cred, opts: fa._apps.setdefault("[DEFAULT]", True)

    creds = types.ModuleType("firebase_admin.credentials")

    class _Cert:
        def __init__(self, path):
            if cert_raises:
                raise ValueError("invalid service account")
            self.path = path

    creds.Certificate = _Cert

    db = types.ModuleType("firebase_admin.db")

    class _Ref:
        def __init__(self, path):
            self.path = path

        def get(self, shallow=False):
            return store.get(self.path)

        def order_by_key(self):
            return self

        def limit_to_last(self, n):
            return self

    db.reference = lambda path: _Ref(path)
    fa.credentials = creds
    fa.db = db
    return fa


def _install_fake(monkeypatch, fa):
    monkeypatch.setitem(sys.modules, "firebase_admin", fa)
    monkeypatch.setitem(sys.modules, "firebase_admin.credentials", fa.credentials)
    monkeypatch.setitem(sys.modules, "firebase_admin.db", fa.db)


def test_admin_sdk_mode_initializes_and_reads_user_scoped(monkeypatch, tmp_path):
    store = {
        "users/U1/latest_telemetry": {"heart_rate": 72, "spo2": 98, "timestamp": 1},
        "users/U1/history": {"k1": {"heart_rate": 70, "timestamp": 1}},
        "users/U1/profile": {"name": "asmaa"},
        "users/U1/goals": {"steps": 10000},
    }
    _install_fake(monkeypatch, _fake_admin(store))
    cred = tmp_path / "serviceAccountKey.json"
    cred.write_text("{}")

    svc = FirebaseService(
        credentials_path=str(cred),
        database_url="https://demo-rtdb.firebaseio.com",
    )
    assert svc.mode == "admin_sdk"
    assert svc.read_latest("U1")["heart_rate"] == 72
    assert svc.read_history("U1")[0]["heart_rate"] == 70
    assert svc.read_profile("U1")["name"] == "asmaa"
    assert svc.read_goals("U1")["steps"] == 10000
    st = svc.status()
    assert st["firebase_mode"] == "admin_sdk"
    assert st["firebase_read_ok"] is True
    assert st["firebase_error"] is None


def test_rest_mode_is_fallback_without_credentials():
    svc = FirebaseService(
        credentials_path="", database_url="https://demo-rtdb.firebaseio.com",
    )
    assert svc.mode == "rest"


def test_unauthorized_rest_read_reports_clear_error(monkeypatch):
    svc = FirebaseService(
        credentials_path="", database_url="https://demo-rtdb.firebaseio.com",
    )

    def _denied(req, timeout=8):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _denied)
    assert svc.read_latest("U1") is None
    st = svc.status()
    assert st["firebase_read_ok"] is False
    assert "401" in st["firebase_error"]
    assert "Admin SDK" in st["firebase_error"] or "FIREBASE_CREDENTIALS_PATH" in st["firebase_error"]


def test_admin_error_recorded_on_bad_credentials(monkeypatch, tmp_path):
    _install_fake(monkeypatch, _fake_admin({}, cert_raises=True))
    cred = tmp_path / "bad.json"
    cred.write_text("{}")
    svc = FirebaseService(
        credentials_path=str(cred),
        database_url="https://demo-rtdb.firebaseio.com",
    )
    assert svc.mode == "admin_error"
    st = svc.status()
    assert st["firebase_read_ok"] is False
    assert st["firebase_error"]


def test_admin_mode_never_uses_simulator(monkeypatch, tmp_path):
    # Admin mode + empty store → unavailable, NOT simulator.
    from backend.data_source import resolve_latest
    _install_fake(monkeypatch, _fake_admin({}))
    cred = tmp_path / "serviceAccountKey.json"
    cred.write_text("{}")
    svc = FirebaseService(
        credentials_path=str(cred),
        database_url="https://demo-rtdb.firebaseio.com",
    )
    monkeypatch.setenv("DATA_SOURCE", "firebase")
    out = resolve_latest(svc, "ghost")
    assert out["available"] is False
    assert out["source"] == "firebase"
    assert out["is_simulated"] is False


def test_service_account_files_are_gitignored():
    names = [
        "serviceAccountKey.json",
        "backend/serviceAccountKey.json",
        "my-project-firebase-adminsdk-abc12.json",
        "foo-service-account.json",
        "backend/.env",
    ]
    for name in names:
        r = subprocess.run(
            ["git", "check-ignore", name],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert r.returncode == 0, f"{name} is NOT gitignored"
