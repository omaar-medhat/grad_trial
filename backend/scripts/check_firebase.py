#!/usr/bin/env python
"""
Validate Firebase Admin SDK read access WITHOUT printing any secret.

Prints only: firebase_mode, firebase_read_ok, firebase_error, active uid,
whether latest_telemetry was found, and a few normalized sample fields. It
never prints private_key, client_email, the service-account JSON, .env
contents, or any token.

Usage (from the project root, with backend/.env configured):
    python backend/scripts/check_firebase.py
"""

from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, "backend", ".env"))
except Exception:  # python-dotenv optional
    pass

from backend.firebase_service import FirebaseService  # noqa: E402
from backend.telemetry_contract import normalize_reading  # noqa: E402


def _resolve_cred_path() -> str:
    cred = os.environ.get("FIREBASE_CREDENTIALS_PATH", "") or ""
    if cred and not os.path.isabs(cred) and not os.path.exists(cred):
        alt = os.path.join(_ROOT, cred)
        if os.path.exists(alt):
            return alt
    return cred


def main() -> int:
    fb = FirebaseService(
        credentials_path=_resolve_cred_path(),
        database_url=os.environ.get("FIREBASE_DATABASE_URL"),
    )
    uid = fb.resolve_active_uid(os.environ.get("FIREBASE_ACTIVE_UID"))
    status = fb.probe()

    print("firebase_mode:    ", status["firebase_mode"])
    print("firebase_read_ok: ", status["firebase_read_ok"])
    print("firebase_error:   ", status["firebase_error"])
    print("active_uid:       ", uid)

    raw = fb.read_latest(uid) if uid else None
    print("latest_telemetry_found:", bool(raw))

    if raw:
        n = normalize_reading(raw, int(time.time() * 1000), uid=uid)
        print("sample normalized fields:")
        for k in (
            "heart_rate", "spo2", "temperature_c", "battery_level",
            "device_status", "timestamp", "source", "is_simulated",
        ):
            print(f"  {k}: {n.get(k)}")

    ok = bool(status["firebase_read_ok"]) and bool(raw)
    print("\nRESULT:", "OK — live Firebase read succeeded" if ok
          else "NOT OK — see firebase_error above (no secrets printed)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
