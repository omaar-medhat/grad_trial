"""
PulseGuard AI - Firebase Realtime Database adapter (with safe fallback).

Behavior:
  * If `firebase-admin` is importable AND a valid service-account file is
    present AND FIREBASE_DATABASE_URL is set → write to Firebase RTDB.
  * Otherwise → write to a thread-safe in-memory store. The demo still works,
    the API contract is identical, and a clear warning is logged once.

Standard paths (single source of truth — used by frontend and mobile too):
    users/{uid}/latest_telemetry      legacy per-user store (simulator/back-compat)
    users/{uid}/history/{push_id}
    users/{uid}/alerts/{push_id}

Root sensor paths (the real bracelet writes here — the live source of truth):
    /latest_telemetry                 current raw bracelet reading
    /history/{push_id}                timestamped raw bracelet readings
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pulseguard.firebase")

# History size kept per user in the in-memory fallback (oldest dropped).
_FALLBACK_HISTORY_CAP = 500
_FALLBACK_ALERTS_CAP = 100


class _MemoryStore:
    """Process-local fallback used when Firebase Admin is unavailable."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._users: Dict[str, Dict[str, Any]] = {}
        # Root sensor mirror (so tests / simulator can exercise the
        # Firebase-root code path without a live database).
        self._root_latest: Optional[Dict[str, Any]] = None
        self._root_history: Dict[str, Any] = {}

    # -- Root sensor paths (/latest_telemetry, /history) --------------
    def set_root_latest(self, telemetry: Dict[str, Any]) -> None:
        with self._lock:
            self._root_latest = telemetry

    def get_root_latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._root_latest

    def push_root_history(self, record: Dict[str, Any]) -> str:
        with self._lock:
            rec_id = f"mem-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
            self._root_history[rec_id] = record
            if len(self._root_history) > _FALLBACK_HISTORY_CAP:
                extra = len(self._root_history) - _FALLBACK_HISTORY_CAP
                for k in list(self._root_history.keys())[:extra]:
                    self._root_history.pop(k, None)
            return rec_id

    def get_root_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._root_history.values())[-limit:]

    def _user(self, uid: str) -> Dict[str, Any]:
        if uid not in self._users:
            self._users[uid] = {
                "latest_telemetry": None,
                "history": {},       # ordered insertion: dict preserves order in py3.7+
                "alerts": {},
            }
        return self._users[uid]

    def set_latest(self, uid: str, telemetry: Dict[str, Any]) -> None:
        with self._lock:
            self._user(uid)["latest_telemetry"] = telemetry

    def get_latest(self, uid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._user(uid)["latest_telemetry"]

    def push_history(self, uid: str, record: Dict[str, Any]) -> str:
        with self._lock:
            rec_id = f"mem-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
            history = self._user(uid)["history"]
            history[rec_id] = record
            # Trim oldest entries beyond cap.
            if len(history) > _FALLBACK_HISTORY_CAP:
                oldest = list(history.keys())[: len(history) - _FALLBACK_HISTORY_CAP]
                for k in oldest:
                    history.pop(k, None)
            return rec_id

    def get_history(self, uid: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            history = self._user(uid)["history"]
            return list(history.values())[-limit:]

    def push_alert(self, uid: str, alert: Dict[str, Any]) -> str:
        with self._lock:
            alert_id = f"mem-alert-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
            alerts = self._user(uid)["alerts"]
            alerts[alert_id] = alert
            if len(alerts) > _FALLBACK_ALERTS_CAP:
                oldest = list(alerts.keys())[: len(alerts) - _FALLBACK_ALERTS_CAP]
                for k in oldest:
                    alerts.pop(k, None)
            return alert_id

    def get_alerts(self, uid: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            alerts = self._user(uid)["alerts"]
            return list(alerts.values())[-limit:]

    def set_node(self, uid: str, node: str, value: Any) -> None:
        with self._lock:
            self._user(uid)[node] = value

    def get_node(self, uid: str, node: str) -> Any:
        with self._lock:
            return self._user(uid).get(node)

    def list_uids(self) -> List[str]:
        with self._lock:
            return [
                uid for uid, u in self._users.items()
                if u.get("latest_telemetry")
            ]


def _maybe_fix_clock_skew() -> None:
    """Opt-in correction for a clock-skewed host (env FIREBASE_FIX_CLOCK_SKEW).

    Google rejects the service-account OAuth JWT when the host clock differs
    from real time (``invalid_grant: Invalid JWT … iat/exp``). On hosts whose
    clock can't be synced (sandboxes, RTC-less IoT gateways), this measures the
    offset from an HTTP ``Date`` header and shifts ``google.auth`` JWT time by
    it. No-op when the offset is small or the clock is correct — safe in
    production.
    """
    flag = (os.environ.get("FIREBASE_FIX_CLOCK_SKEW", "") or "").lower()
    if flag not in ("1", "true", "yes", "on"):
        return
    try:
        import datetime
        import email.utils
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(
                "https://www.google.com/", timeout=8
            ) as resp:
                date_hdr = resp.headers.get("Date")
        except urllib.error.HTTPError as he:  # still carries a Date header
            date_hdr = he.headers.get("Date")
        real = email.utils.parsedate_to_datetime(date_hdr).astimezone(
            datetime.timezone.utc
        ).replace(tzinfo=None)
        offset = (datetime.datetime.utcnow() - real).total_seconds()
        if abs(offset) < 30:
            return

        import google.auth._helpers as _gh

        def _corrected_utcnow():
            return datetime.datetime.utcnow() - datetime.timedelta(
                seconds=offset
            )

        _gh.utcnow = _corrected_utcnow
        # Also correct the app's notion of "now" so device-status freshness
        # (server now vs sensor real-time timestamp) stays accurate.
        from . import clock as _clock
        _clock.set_offset_ms(int(offset * 1000))
        logger.warning(
            "Firebase: applied %.0fs clock-skew correction for Admin SDK auth "
            "and device-status freshness (host clock differs from real time).",
            offset,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Firebase: clock-skew fix skipped (%s)", exc)


class FirebaseService:
    """Adapter that prefers real Firebase RTDB and falls back to memory."""

    def __init__(self, credentials_path: Optional[str], database_url: Optional[str]) -> None:
        self._mode = "memory"
        self._memory = _MemoryStore()
        self._db = None
        self._database_url = (database_url or "").rstrip("/")
        # Observed-change freshness, keyed by uid: server time (ms) when that
        # user's latest_telemetry was last seen to CHANGE. Makes device-status
        # robust to a misaligned device clock — a live, changing feed reads as
        # connected even if its own `timestamp` field is wrong.
        self._obs_lock = threading.Lock()
        self._obs: Dict[str, Dict[str, Any]] = {}
        # Live read health (updated by each read + probe()).
        self._read_ok: Optional[bool] = None
        self._last_error: Optional[str] = None

        # No DB URL at all → pure in-memory fallback (tests / offline demo).
        if not database_url:
            logger.warning(
                "Firebase: no database URL provided — using in-memory fallback. "
                "Set FIREBASE_DATABASE_URL (and optionally "
                "FIREBASE_CREDENTIALS_PATH) to read live sensor data."
            )
            return

        # DB URL but no usable Admin credentials → REST read mode. The root
        # sensor node (/latest_telemetry, /history) is read over the RTDB REST
        # API; per-user writes use the in-memory mirror. This lets the backend
        # serve LIVE bracelet data without a service-account file.
        if not credentials_path or not os.path.exists(credentials_path):
            self._mode = "rest"
            logger.info(
                "Firebase: REST read mode (no Admin credentials) — reading live "
                "root sensor data from %s", self._database_url,
            )
            return

        # Credentials provided → Firebase Admin SDK (server-side, bypasses
        # database rules). We deliberately do NOT fall back to anonymous REST
        # here: if the credentials are bad we surface a clear error instead of
        # silently reading nothing.
        _maybe_fix_clock_skew()
        try:
            import firebase_admin
            from firebase_admin import credentials, db

            if not firebase_admin._apps:  # noqa: SLF001
                cred = credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(
                    cred, {"databaseURL": database_url}
                )
            self._db = db
            self._mode = "admin_sdk"
            self._read_ok = None  # confirmed on first read / probe()
            logger.info(
                "Firebase: Admin SDK connected (%s) — reading user-scoped "
                "data, database rules bypassed server-side.", database_url,
            )
        except Exception as exc:  # pragma: no cover - depends on user env
            self._mode = "admin_error"
            self._read_ok = False
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Firebase: Admin SDK init FAILED (%s). Check "
                "FIREBASE_CREDENTIALS_PATH points to a valid service-account "
                "JSON for this project. NOT falling back to anonymous REST.",
                exc,
            )

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        # "admin_sdk" | "rest" | "memory" | "admin_error"
        return self._mode

    @property
    def firebase_mode(self) -> str:
        """Label for /api/health: how live data is being read."""
        return self._mode

    @property
    def read_ok(self) -> Optional[bool]:
        return self._read_ok

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def status(self) -> Dict[str, Any]:
        return {
            "firebase_mode": self._mode,
            "firebase_read_ok": self._read_ok,
            "firebase_error": self._last_error,
        }

    def probe(self) -> Dict[str, Any]:
        """Lightweight live read to report current auth/read health.

        Reads the active user's latest_telemetry (or lists /users) so
        /api/health reflects whether the backend can actually read Firebase.
        """
        try:
            if self._mode == "memory":
                self._read_ok, self._last_error = True, None
            elif self._mode == "admin_error":
                pass  # keep the init error
            else:
                uid = os.environ.get("FIREBASE_ACTIVE_UID")
                if uid:
                    self.read_latest(uid)      # updates _read_ok/_last_error
                else:
                    self.list_user_uids()
                    self._read_ok = True
                    self._last_error = None
        except Exception as exc:  # noqa: BLE001
            self._read_ok = False
            self._last_error = f"{type(exc).__name__}: {exc}"
        return self.status()

    def healthy(self) -> bool:
        return True  # both modes are always functional from API perspective

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------
    def _rest_put(self, path: str, data: Dict[str, Any]) -> bool:
        """Write a node to RTDB via the REST API (PUT = set)."""
        import json as _json
        import urllib.error
        import urllib.request

        secret = (
            os.environ.get("FIREBASE_DB_SECRET")
            or os.environ.get("FIREBASE_DB_AUTH")
        )
        auth_param = f"&auth={secret}" if secret else ""
        url = f"{self._database_url}/{path}.json?_={int(time.time() * 1000)}{auth_param}"
        body = _json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="PUT",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=8):
                pass
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Firebase REST write failed for '%s': %s", path, exc)
            return False

    def write_latest(self, uid: str, telemetry: Dict[str, Any]) -> bool:
        """Persist /users/{uid}/latest_telemetry. Returns True on success so the
        ingest endpoint can fail loudly instead of pretending success."""
        if self._mode == "admin_sdk":
            return self._admin_set(f"users/{uid}/latest_telemetry", telemetry)
        if self._mode == "rest" and self._database_url:
            ok = self._rest_put(f"users/{uid}/latest_telemetry", telemetry)
            self._memory.set_latest(uid, telemetry)
            return ok
        self._memory.set_latest(uid, telemetry)
        return True

    def read_device_assigned_uid(self, device_id: str) -> Optional[str]:
        """Read /devices/{device_id}/assigned_uid — the device→user pairing
        used to route bracelet telemetry to the right user in production."""
        if not device_id:
            return None
        path = f"devices/{device_id}/assigned_uid"
        if self._mode == "admin_sdk":
            val = self._admin_ref(path)
        elif self._mode == "rest":
            val = self._rest_get(path)
        else:
            val = None  # memory mode has no device registry
        return str(val) if val else None

    def _admin_ref(self, path: str):
        """Admin SDK read with live read-health tracking. ``builder`` may shape
        the reference (e.g. ordering); returns the node value or None."""
        try:
            data = self._db.reference(path).get()
            self._read_ok, self._last_error = True, None
            return data
        except Exception as exc:  # noqa: BLE001
            self._read_ok = False
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Firebase Admin read failed (%s): %s", path, exc)
            return None

    def read_latest(self, uid: str) -> Optional[Dict[str, Any]]:
        """Read /users/{uid}/latest_telemetry (the live source of truth)."""
        if self._mode == "admin_sdk":
            return self._admin_ref(f"users/{uid}/latest_telemetry")
        if self._mode == "rest":
            return self._rest_get(f"users/{uid}/latest_telemetry")
        return self._memory.get_latest(uid)

    def push_history(self, uid: str, record: Dict[str, Any]) -> str:
        if self._mode == "admin_sdk":
            ref = self._db.reference(f"users/{uid}/history").push(record)
            return ref.key
        if self._mode == "rest" and self._database_url:
            import json as _json
            import urllib.request
            url = f"{self._database_url}/users/{uid}/history.json"
            body = _json.dumps(record).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    result = _json.loads(resp.read().decode("utf-8"))
                    return result.get("name", "")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Firebase REST push_history failed: %s", exc)
        return self._memory.push_history(uid, record)

    def read_history(self, uid: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Read /users/{uid}/history (newest `limit` records)."""
        if self._mode == "admin_sdk":
            try:
                ref = (
                    self._db.reference(f"users/{uid}/history")
                    .order_by_key()
                    .limit_to_last(limit)
                )
                data = ref.get() or {}
                self._read_ok, self._last_error = True, None
                return list(data.values())
            except Exception as exc:  # noqa: BLE001
                self._read_ok = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Firebase Admin history read failed: %s", exc)
                return []
        if self._mode == "rest":
            data = self._rest_get(
                f"users/{uid}/history",
                params=f'orderBy="$key"&limitToLast={int(limit)}',
            )
            return list(data.values()) if isinstance(data, dict) else []
        return self._memory.get_history(uid, limit=limit)

    def read_profile(self, uid: str) -> Optional[Dict[str, Any]]:
        """Read /users/{uid}/profile (NOT live telemetry)."""
        if self._mode == "admin_sdk":
            return self._admin_ref(f"users/{uid}/profile")
        if self._mode == "rest":
            return self._rest_get(f"users/{uid}/profile")
        return self._memory.get_node(uid, "profile")

    def read_goals(self, uid: str) -> Optional[Dict[str, Any]]:
        """Read /users/{uid}/goals (NOT live telemetry)."""
        if self._mode == "admin_sdk":
            return self._admin_ref(f"users/{uid}/goals")
        if self._mode == "rest":
            return self._rest_get(f"users/{uid}/goals")
        return self._memory.get_node(uid, "goals")

    def verify_id_token_claims(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify a Firebase ID token (Admin SDK) and return its full claims
        (uid, email, …), or None if invalid. Requires Admin SDK mode."""
        if not token or self._mode != "admin_sdk":
            return None
        try:
            from firebase_admin import auth as fb_auth
            # clock_skew_seconds tolerates small host/Google clock differences.
            decoded = fb_auth.verify_id_token(token, clock_skew_seconds=60)
            if decoded.get("uid"):
                self._read_ok, self._last_error = True, None
            return decoded
        except Exception as exc:  # noqa: BLE001
            logger.warning("Firebase ID token verification failed: %s", exc)
            return None

    def verify_id_token(self, token: str) -> Optional[str]:
        """Verify a Firebase ID token and return its uid (source of truth)."""
        claims = self.verify_id_token_claims(token)
        return claims.get("uid") if claims else None

    def _admin_set(self, path: str, value: Dict[str, Any]) -> bool:
        try:
            self._db.reference(path).set(value)
            self._read_ok, self._last_error = True, None
            return True
        except Exception as exc:  # noqa: BLE001
            self._read_ok = False
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Firebase Admin write failed (%s): %s", path, exc)
            return False

    def write_profile(self, uid: str, data: Dict[str, Any]) -> bool:
        if self._mode == "admin_sdk":
            return self._admin_set(f"users/{uid}/profile", data)
        if self._mode == "rest":
            logger.warning("Firebase REST mode is read-only; cannot write profile.")
            return False
        self._memory.set_node(uid, "profile", data)
        return True

    def write_goals(self, uid: str, data: Dict[str, Any]) -> bool:
        if self._mode == "admin_sdk":
            return self._admin_set(f"users/{uid}/goals", data)
        if self._mode == "rest":
            logger.warning("Firebase REST mode is read-only; cannot write goals.")
            return False
        self._memory.set_node(uid, "goals", data)
        return True

    def list_user_uids(self) -> List[str]:
        """List uids under /users (shallow) — for active-uid fallback."""
        if self._mode == "admin_sdk":
            try:
                data = self._db.reference("users").get(shallow=True) or {}
                self._read_ok, self._last_error = True, None
                return list(data.keys())
            except Exception as exc:  # noqa: BLE001
                self._read_ok = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                return []
        if self._mode == "rest":
            data = self._rest_get("users", params="shallow=true")
            return list(data.keys()) if isinstance(data, dict) else []
        return self._memory.list_uids()

    def resolve_active_uid(
        self, requested: Optional[str] = None
    ) -> Optional[str]:
        """Resolve the active uid by priority (see app._resolve_active_uid).

        1. explicit ``requested`` (query/body) → 2. FIREBASE_ACTIVE_UID env →
        3. first user under /users that has latest_telemetry → else None.
        The uid is NEVER hardcoded in code; only env/query supply it.
        """
        if requested:
            return str(requested)
        env_uid = os.environ.get("FIREBASE_ACTIVE_UID")
        if env_uid:
            return env_uid.strip()
        try:
            for uid in self.list_user_uids():
                if self.read_latest(uid):
                    return uid
        except Exception:  # noqa: BLE001
            pass
        return None

    # ------------------------------------------------------------------
    # Root sensor paths — the REAL bracelet writes here. These are the
    # live source of truth for /api/vitals/*. They are deliberately NOT
    # user-scoped: the hardware publishes to a single root node.
    # ------------------------------------------------------------------
    def observe_latest(
        self, uid: str, raw: Optional[Dict[str, Any]]
    ) -> Optional[int]:
        """Record server-time freshness of /users/{uid}/latest_telemetry.

        Computes a signature of the payload; when it changes the change time is
        set to *now*. Returns the server epoch (ms) when the payload was last
        observed to change for this uid, or None until a change is witnessed.
        The signature includes the device timestamp, so every fresh push counts
        as a change even if the vitals are identical.
        """
        with self._obs_lock:
            state = self._obs.setdefault(
                uid, {"sig": None, "last_seen_ms": None}
            )
            if not isinstance(raw, dict) or not raw:
                return state["last_seen_ms"]
            import hashlib
            import json as _json
            sig = hashlib.md5(
                _json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            from . import clock as _clock
            now_ms = _clock.now_ms()
            if state["sig"] is None:
                # First sight: record the signature but do NOT claim it changed
                # "now" — a stale reading left over while the sensor was off
                # must not look connected. Freshness stays on the sensor
                # timestamp until a real change is witnessed.
                state["sig"] = sig
            elif sig != state["sig"]:
                state["sig"] = sig
                state["last_seen_ms"] = now_ms
            return state["last_seen_ms"]

    def observed_last_seen_ms(self, uid: str) -> Optional[int]:
        with self._obs_lock:
            return self._obs.get(uid, {}).get("last_seen_ms")

    def _rest_get(self, path: str, params: str = "") -> Any:
        """Read a node from the RTDB REST API.

        * Cache-busted (unique param + no-cache headers) so a live feed is never
          served from a stale CDN/proxy copy.
        * If ``FIREBASE_DB_SECRET`` / ``FIREBASE_DB_AUTH`` is set, it is sent as
          the ``auth`` token — needed once the database rules stop allowing
          anonymous reads of the sensor root.
        """
        import json
        import urllib.error
        import urllib.request

        parts = [f"_={int(time.time() * 1000)}"]
        if params:
            parts.append(params)
        secret = (
            os.environ.get("FIREBASE_DB_SECRET")
            or os.environ.get("FIREBASE_DB_AUTH")
        )
        if secret:
            parts.append(f"auth={secret}")
        url = f"{self._database_url}/{path}.json?{'&'.join(parts)}"
        req = urllib.request.Request(url, headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        })
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self._read_ok, self._last_error = True, None
            return data
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            self._read_ok = False
            if exc.code in (401, 403):
                self._last_error = (
                    f"HTTP {exc.code} Unauthorized reading /{path}: database "
                    "rules deny anonymous read. Set FIREBASE_CREDENTIALS_PATH "
                    "(Admin SDK) or FIREBASE_DB_SECRET."
                )
                logger.warning(
                    "Firebase REST read DENIED (%s) for '%s': database rules "
                    "deny anonymous read. Set FIREBASE_CREDENTIALS_PATH "
                    "(Admin SDK) or FIREBASE_DB_SECRET.", exc.code, path,
                )
            else:
                self._last_error = f"HTTP {exc.code} reading /{path}"
                logger.warning("Firebase REST read failed (%s): %s", path, exc)
            return None
        except Exception as exc:  # noqa: BLE001
            self._read_ok = False
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Firebase REST read failed (%s): %s", path, exc)
            return None

    def read_root_latest(self) -> Optional[Dict[str, Any]]:
        if self._mode == "admin_sdk":
            return self._db.reference("latest_telemetry").get()
        if self._mode == "rest":
            return self._rest_get("latest_telemetry")
        return self._memory.get_root_latest()

    def read_root_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self._mode == "admin_sdk":
            ref = (
                self._db.reference("history")
                .order_by_key()
                .limit_to_last(limit)
            )
            data = ref.get() or {}
            return list(data.values())
        if self._mode == "rest":
            data = self._rest_get(
                "history", params=f'orderBy="$key"&limitToLast={int(limit)}'
            )
            return list(data.values()) if isinstance(data, dict) else []
        return self._memory.get_root_history(limit=limit)

    def write_root_latest(self, telemetry: Dict[str, Any]) -> None:
        """Used by the simulator/tests to seed the root sensor node."""
        if self._mode == "admin_sdk":
            self._db.reference("latest_telemetry").set(telemetry)
        else:
            self._memory.set_root_latest(telemetry)

    def push_root_history(self, record: Dict[str, Any]) -> str:
        if self._mode == "admin_sdk":
            ref = self._db.reference("history").push(record)
            return ref.key
        return self._memory.push_root_history(record)

    def push_alert(self, uid: str, alert: Dict[str, Any]) -> str:
        if self._mode == "admin_sdk":
            ref = self._db.reference(f"users/{uid}/alerts").push(alert)
            return ref.key
        return self._memory.push_alert(uid, alert)

    def read_alerts(self, uid: str, limit: int = 50) -> List[Dict[str, Any]]:
        if self._mode == "admin_sdk":
            ref = (
                self._db.reference(f"users/{uid}/alerts")
                .order_by_key()
                .limit_to_last(limit)
            )
            data = ref.get() or {}
            return list(data.values())
        return self._memory.get_alerts(uid, limit=limit)
