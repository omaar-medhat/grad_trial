"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import os
import sys
import pytest

# Make `backend` importable when pytest runs from the repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _deterministic_env(monkeypatch):
    """Keep tests offline + clock-stable regardless of a local backend/.env:
    never run the live clock-skew probe, and keep the corrected clock at 0."""
    monkeypatch.setenv("FIREBASE_FIX_CLOCK_SKEW", "0")
    from backend import clock
    clock.set_offset_ms(0)
    yield
    clock.set_offset_ms(0)


@pytest.fixture()
def app():
    # Ensure model loading stays off during tests (fast, deterministic).
    os.environ["LOAD_CHATBOT_MODEL"] = "0"
    # Rate-limiter is disabled in tests so heavy chat/telemetry suites
    # don't trip on the 120-per-minute default and produce flaky 429s.
    os.environ["RATE_LIMIT_ENABLED"] = "0"
    os.environ.setdefault("FIREBASE_CREDENTIALS_PATH", "")
    os.environ.setdefault("FIREBASE_DATABASE_URL", "")
    from backend.app import create_app
    app = create_app()
    app.config.update({"TESTING": True})
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
