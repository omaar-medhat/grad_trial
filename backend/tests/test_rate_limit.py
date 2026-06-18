"""Rate-limiter integration tests.

The pytest conftest disables the limiter by default for the broader
suite. These tests opt back in via a tightened cap and verify the
limiter trips with a clear 429 envelope.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def limited_client():
    # Re-enable the limiter with a tight cap on /api/chat so we can
    # trip it deterministically without flooding traffic.
    os.environ["RATE_LIMIT_ENABLED"] = "1"
    os.environ["RATE_LIMIT_CHAT"] = "3 per minute"
    os.environ["RATE_LIMIT_DEFAULT"] = "1000 per minute"
    os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"
    os.environ["LOAD_CHATBOT_MODEL"] = "0"
    os.environ.setdefault("FIREBASE_CREDENTIALS_PATH", "")
    os.environ.setdefault("FIREBASE_DATABASE_URL", "")

    # Force a fresh app so the new env values are picked up by Limiter.
    import importlib
    import backend.app as app_module
    importlib.reload(app_module)
    app = app_module.create_app()
    app.config.update({"TESTING": True})
    yield app.test_client()

    # Cleanup: turn the limiter back off for downstream tests.
    os.environ["RATE_LIMIT_ENABLED"] = "0"
    os.environ.pop("RATE_LIMIT_CHAT", None)
    os.environ.pop("RATE_LIMIT_DEFAULT", None)
    importlib.reload(app_module)


def test_chat_route_returns_429_after_cap(limited_client):
    payload = {"message": "Am I okay?", "user_id": "ratelimited-user"}
    statuses = [
        limited_client.post("/api/chat", json=payload).status_code
        for _ in range(5)
    ]
    # First 3 succeed, 4th and 5th should be 429.
    assert statuses[:3] == [200, 200, 200], statuses
    assert 429 in statuses[3:], statuses


def test_429_uses_standard_error_envelope(limited_client):
    payload = {"message": "Hi", "user_id": "envelope-check"}
    last = None
    for _ in range(6):
        last = limited_client.post("/api/chat", json=payload)
    assert last is not None
    assert last.status_code == 429
    body = last.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
