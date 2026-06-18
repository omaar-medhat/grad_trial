"""
PulseGuard AI - Flask backend (single source of truth for the API).

Endpoints:
    GET  /                 Friendly root banner (links to dashboard + key APIs).
    GET  /health           Backend liveness + version (alias: /api/health).
    GET  /api/metrics      In-process counters (no Prometheus dep).
    GET  /api/models       Loaded ML model info + LLM provider.
    POST /api/telemetry    Ingest a reading, analyze, persist, alert.
    GET  /api/latest       Latest telemetry for the user (raw stored reading).
    GET  /api/vitals/latest  Normalized current state (single source of truth).
    GET  /api/history      Recent history (?limit=, default 100).
    GET  /api/alerts       Recent alerts  (?limit=, default 50).
    GET  /api/reports/daily    Daily health summary for the user.
    GET  /api/reports/weekly   Weekly health summary for the user.
    GET  /api/reports/export.csv  Download history as CSV.
    POST /api/ml/predict/stress  WESAD stress model (non_stress/stress).
    POST /api/simulate     Generate ONE synthetic reading + ingest (?mode=).
    GET  /api/simulate/modes  List the simulator's demo scenarios.
    POST /api/chat         Chatbot reply (with telemetry context).
    POST /chat             Back-compat alias for /api/chat.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, Optional

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

try:
    from dotenv import load_dotenv
    load_dotenv(
        dotenv_path=os.path.join(os.path.dirname(__file__), ".env")
    )
except Exception:  # python-dotenv missing is fine
    pass

from .alerts import (
    current_alerts,
    has_critical,
    historical_alerts,
    top_severity,
)
from .anomaly_detection import (
    TelemetryValidationError,
    analyze,
    battery_status,
)
from .chatbot_service import ChatbotService
from .data_source import data_source_mode, resolve_history, resolve_latest
from .firebase_service import FirebaseService
from .logging_config import configure_logging, install_request_logging
from .ml import get_models
from .reports import build_daily_report, build_summary, to_csv
from .responses import err, ok
from .simulator import AVAILABLE_MODES, generate_reading
from .telemetry_contract import (
    connected_threshold_sec,
    stale_threshold_sec,
)

__version__ = "1.0.0"

logger = logging.getLogger("pulseguard.app")


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class AuthRequired(Exception):
    """Raised when a request needs a valid Firebase ID token and none is
    usable (invalid token, or missing token while REQUIRE_AUTH is on)."""


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------
# In-process counters (exposed via /api/metrics). Replace with
# Prometheus client in production; this keeps the demo dep-free.
# ---------------------------------------------------------------------
_metrics: Dict[str, Any] = {
    "started_at": time.time(),
    "requests_total": 0,
    "requests_by_path": defaultdict(int),
    "telemetry_ingested": 0,
    "alerts_raised": 0,
    "chat_replies": 0,
}


def _resolve_uid(payload: Optional[Dict[str, Any]] = None) -> str:
    """Resolve the active user id: query → body → demo default."""
    uid = request.args.get("uid")
    if not uid and payload:
        uid = payload.get("user_id") or payload.get("uid")
    if not uid:
        uid = os.environ.get("DEFAULT_DEMO_UID", "demo-user-001")
    return str(uid)


def _normalize_state(
    latest: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Single normalized snapshot of current telemetry + model-derived values.

    Canonical field names (snake_case) — the SAME schema the web
    `FirebaseTelemetry` and mobile `MobileTelemetry` types use, so every layer
    reads one contract. Missing values are null (never faked).
    """
    if not latest:
        return {"available": False}
    a = analysis or {}
    ml = a.get("ml", {})
    anomaly = ml.get("anomaly", {})
    src = latest.get("source") or "unknown"
    anomaly_score = latest.get("ml_anomaly_score")
    if anomaly_score is None:
        anomaly_score = anomaly.get("score")
    anomaly_status = None
    if anomaly:
        anomaly_status = "flagged" if anomaly.get("is_anomaly") else "normal"
    return {
        "available": True,
        "heart_rate": latest.get("heart_rate"),
        "spo2": latest.get("spo2"),
        "temperature_c": latest.get("temperature_c"),
        "steps": latest.get("steps"),
        "activity": latest.get("activity") or a.get("activity"),
        "battery_level": latest.get("battery_level"),
        "source": src,
        "is_simulated": src != "real_bracelet",
        "wellness_score": latest.get("wellness_score", a.get("wellness_score")),
        "risk_level": latest.get("risk_level") or a.get("risk_level"),
        "stress_label": (
            latest.get("stress_label") or a.get("stress", {}).get("label")
        ),
        "stress_score": latest.get("stress_score"),
        "anomaly_status": anomaly_status,
        "anomaly_score": anomaly_score,
        "risk_confidence": ml.get("risk", {}).get("confidence"),
        "timestamp": latest.get("timestamp"),
    }


# ---------------------------------------------------------------------
# Rate limiter — module-level so the decorators (@limiter.limit(...))
# keep a stable reference. flask-limiter holds a weakref internally
# which gets GC'd if the Limiter is only stored as a local variable
# inside create_app().
# ---------------------------------------------------------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120 per minute", "2000 per hour"],
    headers_enabled=True,
)


# ---------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------
def create_app() -> Flask:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

    app = Flask(__name__)
    install_request_logging(app)

    cors_origins = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "*").split(",")
        if o.strip()
    ]
    CORS(
        app,
        resources={r"/*": {"origins": cors_origins or "*"}},
        supports_credentials=False,
    )

    # --- Rate limiting (defense in depth) ----------------------------
    # The Limiter is defined at module scope above (so the decorators
    # keep a live reference). We bind it to this app and refresh the
    # per-app config from env. Set RATE_LIMIT_ENABLED=0 to disable —
    # the pytest conftest does that so the suite is not flaky.
    limiter.enabled = _bool_env("RATE_LIMIT_ENABLED", default=True)
    limiter._default_limits_per_method = False
    limiter._storage_uri = os.environ.get(
        "RATE_LIMIT_STORAGE_URI", "memory://"
    )
    limiter._default_limits = []
    limiter.init_app(app)
    app.config["RATELIMIT_DEFAULT"] = ";".join([
        os.environ.get("RATE_LIMIT_DEFAULT", "120 per minute"),
        os.environ.get("RATE_LIMIT_HOURLY", "2000 per hour"),
    ])

    @app.errorhandler(429)
    def _on_429(_exc):
        return err(
            "RATE_LIMIT_EXCEEDED",
            "Too many requests — please slow down and try again.",
            status=429,
        )

    # --- Singletons --------------------------------------------------
    firebase = FirebaseService(
        credentials_path=os.environ.get("FIREBASE_CREDENTIALS_PATH"),
        database_url=os.environ.get("FIREBASE_DATABASE_URL"),
    )
    # Default to the bundled fine-tuned medical LoRA adapter if present, so
    # LOAD_CHATBOT_MODEL=1 "just works" without setting a path.
    _default_adapter = os.path.join(
        os.path.dirname(__file__), "models", "medical_slm_adapter"
    )
    chatbot = ChatbotService(
        base_model=os.environ.get(
            "TINY_LLAMA_BASE_MODEL",
            "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        ),
        adapter_path=os.environ.get(
            "TINY_LLAMA_ADAPTER_PATH",
            _default_adapter if os.path.isdir(_default_adapter) else "",
        ),
        timeout_seconds=float(
            os.environ.get("CHATBOT_TIMEOUT_SECONDS", "20")
        ),
        load_model=_bool_env("LOAD_CHATBOT_MODEL", default=False),
    )

    # Trained neural-network models (loaded lazily from disk).
    ml_models = get_models()

    app.config["FIREBASE"] = firebase
    app.config["CHATBOT"] = chatbot
    app.config["ML"] = ml_models

    # --- Track the last active frontend user UID ---------------------
    # The sensor (Arduino) doesn't know the Firebase UID. We remember the
    # most recent UID seen from frontend requests (?uid=...) and use it
    # when the sensor sends data without a UID.
    _last_frontend_uid: Dict[str, Any] = {"uid": None}

    # --- Per-request metric ------------------------------------------
    @app.before_request
    def _count_request():
        _metrics["requests_total"] += 1
        _metrics["requests_by_path"][request.path] += 1
        seen_uid = request.args.get("uid")
        if seen_uid and seen_uid != "demo-user-001":
            _last_frontend_uid["uid"] = seen_uid

    # --- No-store on all API/health responses ------------------------
    # Live telemetry must never be served from a browser/proxy cache, or the
    # dashboard would show a frozen reading while Firebase keeps changing.
    @app.after_request
    def _no_store(resp):
        if request.path.startswith("/api") or request.path == "/health":
            resp.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp

    def _active_uid(payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Resolve the active Firebase user id, token-first.

        Priority:
          1. uid from a VERIFIED Firebase ID token (Authorization: Bearer …) —
             the authoritative source. A client-claimed ?uid is ignored when a
             valid token is present.
          2. (demo/dev only, i.e. REQUIRE_AUTH off) explicit ?uid / body uid.
          3. (demo/dev only) FIREBASE_ACTIVE_UID env → first /users child.

        A present-but-invalid token, or a missing token when REQUIRE_AUTH is on,
        raises AuthRequired → 401.
        """
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()
            uid = firebase.verify_id_token(token)
            if uid:
                return uid  # verified token uid wins — never trust client uid
            raise AuthRequired("Invalid or expired Firebase ID token.")

        # No bearer token present.
        if _bool_env("REQUIRE_AUTH", default=False):
            raise AuthRequired(
                "Authentication required: sign in and send a Firebase ID token."
            )

        # Demo / dev mode only: trust the client-supplied uid / env fallback.
        requested = request.args.get("uid")
        if not requested and payload:
            requested = payload.get("user_id") or payload.get("uid")
        return firebase.resolve_active_uid(requested)

    # --- Error handlers (standard envelope) --------------------------
    @app.errorhandler(AuthRequired)
    def _on_auth_required(exc):
        return err("UNAUTHORIZED", str(exc) or "Authentication required.", status=401)

    @app.errorhandler(TelemetryValidationError)
    def _on_validation_error(exc):
        return err("INVALID_INPUT", str(exc), status=400)

    @app.errorhandler(404)
    def _on_404(_exc):
        return err(
            "NOT_FOUND",
            f"No route for {request.method} {request.path}",
            status=404,
        )

    @app.errorhandler(405)
    def _on_405(_exc):
        return err(
            "METHOD_NOT_ALLOWED",
            f"{request.method} not allowed on {request.path}",
            status=405,
        )

    @app.errorhandler(500)
    def _on_500(exc):
        logger.exception("unhandled 500: %s", exc)
        return err(
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
            status=500,
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @app.get("/")
    def root():
        """Friendly landing banner so GET / isn't a 404."""
        return jsonify({
            "ok": True,
            "service": "AI Health Monitoring Bracelet Backend API",
            "status": "running",
            "version": __version__,
            "dashboard": "http://localhost:8080",
            "health": "/api/health",
            "models": "/api/models/status",
            "chat": "/api/chat",
        })

    @app.get("/health")
    @app.get("/api/health")
    def health():
        return ok({
            "status": "ok",
            "version": __version__,
            "uptime_seconds": int(
                time.time() - _metrics["started_at"]
            ),
            "firebase_mode": firebase.firebase_mode,
            "firebase_read_ok": firebase.probe().get("firebase_read_ok"),
            "firebase_error": firebase.last_error,
            "services": {
                "firebase": firebase.mode,
                "chatbot": chatbot.model_status,
                "ml_risk": ml_models.risk.status,
                "ml_anomaly": ml_models.anomaly.status,
                "ml_intent": ml_models.intent.status,
                "ml_stress": ml_models.stress.status,
            },
        })

    @app.get("/api/models")
    @app.get("/api/models/status")
    def models_info():
        # Look up the LLM info from the chatbot service (which holds
        # an assistant instance with the LLMClient).
        try:
            llm_info = chatbot._assistant.llm_info()
        except Exception:
            llm_info = {"available": False, "provider": None}
        # Activity model is trained offline on UCI HAR (561 IMU features), so
        # it can't predict from telemetry yet — expose its metrics read-only.
        activity_info = {"name": "activity_classifier", "status": "stub"}
        _act_metrics = os.path.join(
            os.path.dirname(__file__), "models",
            "activity_classifier_metrics.json",
        )
        if os.path.exists(_act_metrics):
            try:
                with open(_act_metrics, encoding="utf-8") as f:
                    m = json.load(f)
                activity_info = {
                    "name": "activity_classifier",
                    "kind": "sklearn (UCI HAR, offline-trained)",
                    "status": "trained_offline",
                    "classes": m.get("classes"),
                    "metrics": m,
                }
            except Exception:  # noqa: BLE001
                pass
        return ok({
            "risk_classifier":    ml_models.risk.info(),
            "anomaly_autoencoder": ml_models.anomaly.info(),
            "intent_classifier":  ml_models.intent.info(),
            "stress_classifier":  ml_models.stress.info(),
            "activity_classifier": activity_info,
            "llm": llm_info,
        })

    @app.post("/api/ml/predict/stress")
    def predict_stress():
        """Run the WESAD stress model. Body: the 252 WESAD features as a
        `features` object (keyed by feature name) or a `vector` list. Returns
        label, confidence, probabilities and model_name."""
        stress = ml_models.stress
        if stress.status != "trained":
            return err(
                "MODEL_UNAVAILABLE",
                stress.error or "Stress model artifact is not loaded.",
                status=503,
            )
        payload = request.get_json(silent=True) or {}
        pred = stress.predict(payload)
        if pred is None:
            return err(
                "INVALID_INPUT",
                (
                    f"Provide the {len(stress.feature_names)} WESAD features as "
                    f"a 'features' object or a 'vector' list."
                ),
                status=400,
            )
        return ok({
            "prediction": pred.label,
            "prediction_id": uuid.uuid4().hex,
            "label": pred.label,          # alias for backward compatibility
            "confidence": round(pred.confidence, 4),
            "probabilities": {
                k: round(v, 4) for k, v in pred.probabilities.items()
            },
            "model_name": pred.model_name,
            "model_type": "stress",
            "source": "wesad_artifact",
            "latency_ms": pred.latency_ms,
        })

    @app.get("/api/metrics")
    def metrics():
        snapshot = {
            "uptime_seconds": int(
                time.time() - _metrics["started_at"]
            ),
            "requests_total": _metrics["requests_total"],
            "telemetry_ingested": _metrics["telemetry_ingested"],
            "alerts_raised": _metrics["alerts_raised"],
            "chat_replies": _metrics["chat_replies"],
            "requests_by_path": dict(_metrics["requests_by_path"]),
            "firebase_mode": firebase.mode,
            "chatbot_status": chatbot.model_status,
        }
        return ok(snapshot)

    # -------------------- Telemetry --------------------
    def _enrich_with_ml(
        reading: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run trained NN models; add results to the analysis dict."""
        ml_section: Dict[str, Any] = {}
        risk_pred = ml_models.risk.predict(reading)
        if risk_pred is not None:
            ml_section["risk"] = {
                "label": risk_pred.label,
                "confidence": round(risk_pred.confidence, 4),
                "probabilities": {
                    k: round(v, 4)
                    for k, v in risk_pred.probabilities.items()
                },
                "latency_ms": risk_pred.latency_ms,
            }
        anomaly = ml_models.anomaly.score(reading)
        if anomaly is not None:
            ml_section["anomaly"] = {
                "score": round(anomaly.score, 4),
                "raw_error": round(anomaly.raw_error, 6),
                "is_anomaly": anomaly.is_anomaly,
                "latency_ms": anomaly.latency_ms,
            }
        if ml_section:
            analysis = {**analysis, "ml": ml_section}
        return analysis

    def _attach_derived(normalized: Dict[str, Any]) -> Dict[str, Any]:
        """Add rule-engine + ML derived values to a NORMALIZED reading without
        ever overwriting a sensor field. Safe when vitals are partial — if the
        core vitals can't be validated, the derived fields are simply None.

        ``risk_level`` stays the device-reported value; the transparent
        rule-engine verdict is exposed separately as ``derived_risk_level`` so
        the UI/alerts can prefer the auditable one for clinical decisions.
        """
        out = dict(normalized)
        out.setdefault("wellness_score", None)
        out.setdefault("derived_risk_level", None)
        out.setdefault("anomaly_status", None)
        out.setdefault("anomaly_score", None)
        out.setdefault("activity", None)
        if not out.get("available"):
            return out
        probe = {
            "heart_rate": out.get("heart_rate"),
            "spo2": out.get("spo2"),
            "temperature_c": out.get("temperature_c"),
            "steps": out.get("steps") or 0,
            "timestamp": int(out.get("timestamp") or 0),
        }
        try:
            analysis = _enrich_with_ml(probe, analyze(probe))
        except TelemetryValidationError:
            return out
        ml = analysis.get("ml", {})
        anomaly = ml.get("anomaly", {})
        out["wellness_score"] = analysis.get("wellness_score")
        out["derived_risk_level"] = analysis.get("risk_level")
        out["activity"] = analysis.get("activity")
        out["anomaly_score"] = anomaly.get("score")
        out["anomaly_status"] = (
            ("flagged" if anomaly.get("is_anomaly") else "normal")
            if anomaly else None
        )
        out["ml_risk_label"] = ml.get("risk", {}).get("label")
        return out

    def _maybe_alert_battery(uid: str, reading: Dict[str, Any]):
        """Push a device-level alert when the bracelet battery is low.

        Kept separate from the vitals risk so a flat battery never masks or
        inflates the patient's clinical risk_level. Always tagged
        ``source: "device"`` regardless of which ingest path produced it.
        """
        status = battery_status(reading.get("battery_level"))
        if status is None:
            return
        firebase.push_alert(uid, {
            "risk_level": status["severity"],
            "message": status["message"],
            "reasons": [status["message"]],
            "source": "device",
            "timestamp": reading["timestamp"],
        })
        _metrics["alerts_raised"] += 1

    @app.post("/api/telemetry")
    @limiter.limit(os.environ.get("RATE_LIMIT_TELEMETRY", "60 per minute"))
    def post_telemetry():
        payload = request.get_json(silent=True) or {}
        uid = _resolve_uid(payload)
        # raises TelemetryValidationError → 400
        analysis = analyze(payload)

        # Persist the validated reading (local import avoids cycles).
        from .anomaly_detection import validate_telemetry
        clean = validate_telemetry(payload)
        clean["risk_level"] = analysis["risk_level"]
        clean["wellness_score"] = analysis["wellness_score"]
        clean["activity"] = analysis["activity"]
        clean["stress_label"] = analysis["stress"]["label"]
        clean["stress_score"] = analysis["stress"]["score"]
        clean["alert_message"] = analysis["alert_message"]
        clean.setdefault("source", "real_bracelet")

        # Run trained NN models in parallel with the rule engine.
        analysis = _enrich_with_ml(clean, analysis)
        if "ml" in analysis:
            clean["ml_risk_label"] = (
                analysis["ml"].get("risk", {}).get("label")
            )
            clean["ml_anomaly_score"] = (
                analysis["ml"].get("anomaly", {}).get("score")
            )

        # Write to the USER-scoped node — the live source of truth that
        # /api/vitals/* reads back (/users/{uid}/latest_telemetry + history).
        firebase.write_latest(uid, clean)
        firebase.push_history(uid, clean)

        if analysis["risk_level"] != "normal":
            alert = {
                "risk_level": analysis["risk_level"],
                "message": analysis["alert_message"],
                "reasons": analysis["reasons"],
                "source": "rule_engine",
                "timestamp": clean["timestamp"],
            }
            firebase.push_alert(uid, alert)
            _metrics["alerts_raised"] += 1

        _maybe_alert_battery(uid, clean)

        _metrics["telemetry_ingested"] += 1
        return ok(
            {"telemetry": clean, "analysis": analysis},
            "Telemetry stored",
        )

    @app.get("/api/latest")
    def get_latest():
        uid = _resolve_uid()
        latest = firebase.read_latest(uid)
        if latest is None:
            return ok(None, "No telemetry yet for this user")
        return ok(latest)

    @app.get("/api/vitals/latest")
    def vitals_latest():
        """Single Firebase-backed source of truth: the current normalized
        bracelet reading + model-derived values + source / device-status /
        last-seen, in one contract the dashboard, chatbot, reports and
        analytics all read. Source priority and the firebase|simulator|auto
        mode are decided in data_source.resolve_latest (never a silent
        simulator fallback in firebase mode)."""
        uid = _active_uid()
        v = _attach_derived(resolve_latest(firebase, uid))
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "vitals/latest uid=%s req_ms=%d norm_hr=%s ts=%s device=%s "
                "basis=%s last_seen=%s source=%s",
                uid, int(time.time() * 1000), v.get("heart_rate"),
                v.get("timestamp"), v.get("device_status"),
                v.get("used_freshness_basis"), v.get("last_seen_seconds"),
                v.get("source"),
            )
        return ok(v)

    @app.get("/api/vitals/history")
    def vitals_history():
        try:
            limit = max(1, min(int(request.args.get("limit", 200)), 1000))
        except ValueError:
            return err("INVALID_INPUT", "limit must be an integer", 400)
        uid = _active_uid()
        history, source = resolve_history(firebase, uid, limit=limit)
        return ok({
            "uid": uid,
            "source": source,
            "is_simulated": source != "firebase",
            "count": len(history),
            "readings": history,
        })

    @app.get("/api/vitals/window")
    def vitals_window():
        """Aggregate the most recent ``seconds`` of Firebase history."""
        try:
            seconds = max(
                1, min(int(request.args.get("seconds", 60)), 86400)
            )
        except ValueError:
            return err("INVALID_INPUT", "seconds must be an integer", 400)
        uid = _active_uid()
        history, source = resolve_history(firebase, uid, limit=1000)
        latest_ts = next(
            (r["timestamp"] for r in reversed(history)
             if isinstance(r.get("timestamp"), (int, float))),
            int(time.time() * 1000),
        )
        cutoff = latest_ts - seconds * 1000
        window = [
            r for r in history
            if isinstance(r.get("timestamp"), (int, float))
            and r["timestamp"] >= cutoff
        ]

        def _agg(key: str):
            xs = [
                r[key] for r in window
                if isinstance(r.get(key), (int, float))
            ]
            if not xs:
                return None
            return {
                "avg": round(sum(xs) / len(xs), 1),
                "min": round(min(xs), 1),
                "max": round(max(xs), 1),
            }

        latest = _attach_derived(resolve_latest(firebase, uid))
        return ok({
            "uid": uid,
            "seconds": seconds,
            "source": source,
            "is_simulated": source != "firebase",
            "count": len(window),
            "heart_rate": _agg("heart_rate"),
            "spo2": _agg("spo2"),
            "temperature_c": _agg("temperature_c"),
            "device_status": latest.get("device_status"),
            "last_seen_seconds": latest.get("last_seen_seconds"),
        })

    @app.get("/api/device/status")
    def device_status_endpoint():
        """Bracelet connection / data-freshness state (separate from the
        Firebase connection itself)."""
        uid = _active_uid()
        latest = resolve_latest(firebase, uid)
        observed = None
        try:
            observed = firebase.observed_last_seen_ms(uid) if uid else None
        except Exception:  # noqa: BLE001
            observed = None
        from .telemetry_contract import _iso
        return ok({
            "uid": uid,
            "device_status": latest.get("device_status"),
            "last_seen_seconds": latest.get("last_seen_seconds"),
            "used_freshness_basis": latest.get("used_freshness_basis"),
            "server_observed_last_seen_at": _iso(observed),
            "latest_heart_rate": latest.get("heart_rate"),
            "source": latest.get("source"),
            "is_simulated": latest.get("is_simulated"),
            "available": latest.get("available", False),
            "timestamp": latest.get("timestamp"),
            "firebase_mode": firebase.firebase_mode,
            "firebase_read_ok": firebase.read_ok,
            "firebase_error": firebase.last_error,
            "data_source_mode": data_source_mode(),
            "thresholds": {
                "connected_max_seconds": connected_threshold_sec(),
                "stale_max_seconds": stale_threshold_sec(),
            },
        })

    @app.get("/api/history")
    def get_history():
        uid = _resolve_uid()
        try:
            limit = max(
                1, min(int(request.args.get("limit", 100)), 1000)
            )
        except ValueError:
            return err("INVALID_INPUT", "limit must be an integer", 400)
        return ok(firebase.read_history(uid, limit=limit))

    def _recent_window(history, seconds=60):
        """Records from the last `seconds` (anchored on the newest reading)."""
        anchor = next(
            (r["timestamp"] for r in reversed(history)
             if isinstance(r.get("timestamp"), (int, float))),
            int(time.time() * 1000),
        )
        cutoff = anchor - seconds * 1000
        return [
            r for r in history
            if isinstance(r.get("timestamp"), (int, float))
            and r["timestamp"] >= cutoff
        ]

    def _current_alerts_for(uid):
        latest = _attach_derived(resolve_latest(firebase, uid))
        history, source = resolve_history(firebase, uid, limit=500)
        window = _recent_window(history, 60)
        profile = firebase.read_profile(uid) if uid else None
        current = current_alerts(latest, window=window, profile=profile)
        return latest, history, source, current

    @app.get("/api/alerts/current")
    def get_alerts_current():
        """Just the CURRENT alerts (live state) for the active user."""
        uid = _active_uid()
        latest, _history, source, current = _current_alerts_for(uid)
        return ok({
            "uid": uid,
            "source": source,
            "is_simulated": source != "firebase",
            "device_status": latest.get("device_status"),
            "last_seen_seconds": latest.get("last_seen_seconds"),
            "top_severity": top_severity(current),
            "has_current_critical": has_critical(current),
            "current": current,
        })

    @app.get("/api/alerts")
    def get_alerts():
        """Firebase-derived alerts, split into CURRENT (live state) and
        HISTORY. Deterministic rule-based — a healthy current battery never
        shows a current low-battery alert, and a current critical alert is
        never hidden behind 'All Good'."""
        uid = _active_uid()
        latest, history, source, current = _current_alerts_for(uid)
        return ok({
            "uid": uid,
            "source": source,
            "is_simulated": source != "firebase",
            "device_status": latest.get("device_status"),
            "last_seen_seconds": latest.get("last_seen_seconds"),
            "top_severity": top_severity(current),
            "has_current_critical": has_critical(current),
            "current": current,
            "history": historical_alerts(history),
        })

    @app.get("/api/alerts/stored")
    def get_alerts_stored():
        """Back-compat: raw per-user alert log (rule-engine + device alerts
        pushed at ingest time)."""
        uid = _resolve_uid()
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 500))
        except ValueError:
            return err("INVALID_INPUT", "limit must be an integer", 400)
        return ok(firebase.read_alerts(uid, limit=limit))

    # -------------------- Reports / export --------------------
    def _period_report(uid: str, period: str, window_ms: int):
        readings = firebase.read_history(uid, limit=1000)
        alerts = firebase.read_alerts(uid, limit=500)
        cutoff = int(time.time() * 1000) - window_ms
        in_window = [
            r for r in readings
            if isinstance(r.get("timestamp"), (int, float))
            and r["timestamp"] >= cutoff
        ]
        a_window = [
            a for a in alerts
            if isinstance(a.get("timestamp"), (int, float))
            and a["timestamp"] >= cutoff
        ]
        return ok(build_summary(in_window, a_window, period))

    @app.get("/api/reports/daily")
    def report_daily():
        """Daily summary from user-scoped Firebase history (last 24h)."""
        uid = _active_uid()
        history, source = resolve_history(firebase, uid, limit=1000)
        from .clock import now_ms as _now_ms
        cutoff = _now_ms() - 24 * 3600 * 1000
        in_window = [
            r for r in history
            if isinstance(r.get("timestamp"), (int, float))
            and r["timestamp"] >= cutoff
        ]
        report = build_daily_report(in_window, source=source)
        report["uid"] = uid
        if uid:
            report["profile"] = firebase.read_profile(uid)
            report["goals"] = firebase.read_goals(uid)
        return ok(report)

    @app.get("/api/profile")
    def get_profile():
        """User profile from /users/{uid}/profile (NOT live telemetry)."""
        uid = _active_uid()
        return ok({"uid": uid, "profile": firebase.read_profile(uid) if uid else None})

    @app.get("/api/goals")
    def get_goals():
        """User goals from /users/{uid}/goals (NOT live telemetry)."""
        uid = _active_uid()
        return ok({"uid": uid, "goals": firebase.read_goals(uid) if uid else None})

    @app.post("/api/auth/bootstrap")
    def auth_bootstrap():
        """Idempotently ensure /users/{uid}/profile and /users/{uid}/goals
        exist after signup/login. The uid is the VERIFIED token uid (never the
        request body). Never creates fake latest_telemetry/history — those only
        appear when the real bracelet writes for this uid."""
        body = request.get_json(silent=True) or {}
        uid = _active_uid(body)   # token-first; raises 401 on bad/missing token
        if not uid:
            return err("UNAUTHORIZED", "No authenticated user to bootstrap.", 401)

        # Email comes from the verified token (if a Bearer token was sent).
        email = ""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            claims = firebase.verify_id_token_claims(
                auth_header[len("Bearer "):].strip()
            ) or {}
            email = claims.get("email", "") or ""

        now = _now_iso()
        write_backend = firebase.firebase_mode  # admin_sdk | rest | memory | …
        profile = firebase.read_profile(uid)
        goals = firebase.read_goals(uid)
        created_profile = False
        created_goals = False
        write_ok = True

        if not profile:
            profile = {
                "uid": uid,
                "email": email,
                "name": body.get("name") or "",
                "age": body.get("age"),
                "gender": body.get("gender"),
                "height": body.get("height"),
                "weight": body.get("weight"),
                "activity": body.get("activity") or "unknown",
                "created_at": now,
                "updated_at": now,
            }
            write_ok = firebase.write_profile(uid, profile) and write_ok
            created_profile = True

        if not goals:
            goals = {"steps": 5000, "calories": 500, "sleep": 8}
            write_ok = firebase.write_goals(uid, goals) and write_ok
            created_goals = True

        # Safe log (no token/secret): what was written and where.
        logger.info(
            "bootstrap uid=%s write_backend=%s created_profile=%s "
            "created_goals=%s write_ok=%s paths=users/%s/{profile,goals}",
            uid, write_backend, created_profile, created_goals, write_ok, uid,
        )

        # A write was attempted but did NOT persist (e.g. REST read-only or
        # admin_error in real Firebase mode) → fail loudly instead of pretending
        # the user was created. Never silently swallow a failed RTDB write.
        if (created_profile or created_goals) and not write_ok:
            return err(
                "FIREBASE_WRITE_FAILED",
                f"Could not persist the user to Firebase (write_backend="
                f"{write_backend}). The backend must run with Admin SDK "
                f"credentials (FIREBASE_CREDENTIALS_PATH) to create users in "
                f"the locked database.",
                status=500,
                details={
                    "uid": uid,
                    "firebase_mode": write_backend,
                    "write_backend": write_backend,
                    "write_ok": False,
                    "firebase_error": firebase.last_error,
                },
            )

        return ok({
            "uid": uid,
            "created_profile": created_profile,
            "created_goals": created_goals,
            "firebase_mode": write_backend,
            "write_backend": write_backend,
            "write_ok": write_ok,
            "profile": profile,
            "goals": goals,
        })

    @app.get("/api/auth/bootstrap/check")
    def auth_bootstrap_check():
        """Safe debug check: does /users/{uid}/{profile,goals} exist? Reports
        the write backend so you can confirm the app is hitting an Admin-SDK
        backend (not rest/memory). No secrets exposed. uid from token, or ?uid
        in demo/dev mode."""
        uid = _active_uid()
        if not uid:
            return err("UNAUTHORIZED", "No authenticated user.", 401)
        return ok({
            "uid": uid,
            "firebase_mode": firebase.firebase_mode,
            "write_backend": firebase.firebase_mode,
            "can_write_real_db": firebase.firebase_mode == "admin_sdk",
            "profile_exists": bool(firebase.read_profile(uid)),
            "goals_exists": bool(firebase.read_goals(uid)),
            "latest_telemetry_exists": bool(firebase.read_latest(uid)),
        })

    @app.get("/api/reports/weekly")
    def report_weekly():
        return _period_report(_resolve_uid(), "weekly", 7 * 24 * 3600 * 1000)

    @app.get("/api/reports/export.csv")
    def report_export_csv():
        uid = _resolve_uid()
        try:
            limit = max(1, min(int(request.args.get("limit", 1000)), 5000))
        except ValueError:
            return err("INVALID_INPUT", "limit must be an integer", 400)
        csv_text = to_csv(firebase.read_history(uid, limit=limit))
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="pulseguard_{uid}.csv"'
                )
            },
        )

    @app.get("/api/simulate/modes")
    def simulate_modes():
        """List the demo scenarios the simulator can be forced into."""
        return ok({"modes": AVAILABLE_MODES})

    @app.post("/api/simulate")
    @limiter.limit(os.environ.get("RATE_LIMIT_SIMULATE", "30 per minute"))
    def post_simulate():
        body = request.get_json(silent=True) or {}
        uid = _resolve_uid(body)
        mode = body.get("mode")
        try:
            reading = generate_reading(mode)
        except ValueError as exc:
            return err("INVALID_INPUT", str(exc), 400)
        reading.pop("scenario", None)
        analysis = analyze(reading)
        reading["risk_level"] = analysis["risk_level"]
        reading["wellness_score"] = analysis["wellness_score"]
        reading["activity"] = analysis["activity"]
        reading["stress_label"] = analysis["stress"]["label"]
        reading["stress_score"] = analysis["stress"]["score"]
        reading["alert_message"] = analysis["alert_message"]
        analysis = _enrich_with_ml(reading, analysis)
        if "ml" in analysis:
            reading["ml_risk_label"] = (
                analysis["ml"].get("risk", {}).get("label")
            )
            reading["ml_anomaly_score"] = (
                analysis["ml"].get("anomaly", {}).get("score")
            )
        firebase.write_latest(uid, reading)
        firebase.push_history(uid, reading)
        if analysis["risk_level"] != "normal":
            firebase.push_alert(uid, {
                "risk_level": analysis["risk_level"],
                "message": analysis["alert_message"],
                "reasons": analysis["reasons"],
                "source": "simulator",
                "timestamp": reading["timestamp"],
            })
            _metrics["alerts_raised"] += 1
        _maybe_alert_battery(uid, reading)
        _metrics["telemetry_ingested"] += 1
        return ok(
            {"telemetry": reading, "analysis": analysis},
            "Synthetic reading stored",
        )

    # -------------------- Chat --------------------
    def _chat_impl():
        body = request.get_json(silent=True) or {}
        message = body.get("message", "")
        uid = _active_uid(body)

        # Use the SAME vitals the UI is showing: the client sends its current
        # live reading as `telemetry`, so the chatbot's numbers always match
        # the dashboard/header. Fall back to the active-user Firebase reading.
        client_tel = body.get("telemetry")
        if isinstance(client_tel, dict) and client_tel.get("heart_rate") is not None:
            latest = client_tel
            telemetry_origin = "client_live"
        else:
            resolved = _attach_derived(resolve_latest(firebase, uid))
            if resolved.get("available") and resolved.get("heart_rate") is not None:
                latest = resolved
                telemetry_origin = "firebase_store"
            else:
                latest = None
                telemetry_origin = "none"

        analysis = None
        if latest:
            try:
                analysis = analyze(latest)
                # Same enrichment as /api/vitals/latest so the chatbot's
                # model-derived values (anomaly, ml risk) match exactly.
                analysis = _enrich_with_ml(latest, analysis)
            except TelemetryValidationError:
                analysis = None

        # Ground the assistant in BACKEND-derived current alerts (never let the
        # LLM invent danger): the deterministic engine decides what's an alert.
        try:
            _l, _h, _s, current_alerts_list = _current_alerts_for(uid)
        except Exception:  # noqa: BLE001
            current_alerts_list = []

        result = chatbot.reply(
            user_message=message,
            latest=latest,
            analysis=analysis,
            history=body.get("history") or [],
            user_id=uid,
            alerts=current_alerts_list,
        )
        # Debug/traceability: where did the answer's data come from?
        result["telemetry_origin"] = telemetry_origin
        result["telemetry_source"] = (latest or {}).get("source")
        result["telemetry_ts"] = (latest or {}).get("timestamp")
        _metrics["chat_replies"] += 1
        return ok(result)

    @app.post("/api/chat")
    @limiter.limit(os.environ.get("RATE_LIMIT_CHAT", "30 per minute"))
    def post_chat():
        return _chat_impl()

    @app.post("/chat")
    @limiter.limit(os.environ.get("RATE_LIMIT_CHAT", "30 per minute"))
    def post_chat_legacy():
        return _chat_impl()

    # -------------------- Legacy Arduino bridge --------------------
    # The old arduino_api.py received sensor data on POST /update_telemetry
    # and served the latest reading on GET /latest. These two endpoints
    # let the existing ESP32 sketch work without reflashing.

    _arduino_latest: Dict[str, Any] = {"ok": False, "ts": None, "data": None}

    @app.post("/update_telemetry")
    @limiter.limit(os.environ.get("RATE_LIMIT_TELEMETRY", "60 per minute"))
    def update_telemetry_legacy():
        nonlocal _arduino_latest
        payload = request.get_json(silent=True) or {}
        if not payload:
            return jsonify({"status": "error", "message": "No data received"}), 400

        now_ms = int(time.time() * 1000)
        _arduino_latest = {"ok": True, "ts": now_ms, "data": payload}

        # Convert old Arduino format → new telemetry schema
        temp_f = payload.get("temperature", 0)
        temp_c = round((temp_f - 32) * 5 / 9, 1) if temp_f and temp_f > 0 else None

        telemetry = {
            "heart_rate": payload.get("heart_rate"),
            "spo2": payload.get("spo2"),
            "temperature_c": temp_c,
            "steps": payload.get("steps", 0),
            "sleep_duration_sec": payload.get("sleep_duration", 0),
            "battery_level": payload.get("battery_level"),
            "fall_alert": payload.get("fall_alert", False),
            "source": "real_bracelet",
            "timestamp": now_ms,
        }

        # Feed into the existing analysis + storage pipeline
        try:
            analysis = analyze(telemetry)
        except TelemetryValidationError as exc:
            return err("INVALID_INPUT", str(exc), status=400)

        telemetry["risk_level"] = analysis["risk_level"]
        telemetry["wellness_score"] = analysis["wellness_score"]
        telemetry["activity"] = analysis["activity"]
        telemetry["stress_label"] = analysis["stress"]["label"]
        telemetry["stress_score"] = analysis["stress"]["score"]
        telemetry["alert_message"] = analysis["alert_message"]

        analysis = _enrich_with_ml(telemetry, analysis)
        if "ml" in analysis:
            telemetry["ml_risk_label"] = analysis["ml"].get("risk", {}).get("label")
            telemetry["ml_anomaly_score"] = analysis["ml"].get("anomaly", {}).get("score")

        # Arduino doesn't send a uid — use the last UID seen from frontend
        explicit_uid = payload.get("user_id") or payload.get("uid")
        uid = explicit_uid or _last_frontend_uid["uid"] or _resolve_uid(payload)
        firebase.write_latest(uid, telemetry)
        firebase.push_history(uid, telemetry)

        if analysis["risk_level"] != "normal":
            firebase.push_alert(uid, {
                "risk_level": analysis["risk_level"],
                "message": analysis["alert_message"],
                "reasons": analysis["reasons"],
                "source": "rule_engine",
                "timestamp": now_ms,
            })
            _metrics["alerts_raised"] += 1

        _maybe_alert_battery(uid, telemetry)
        _metrics["telemetry_ingested"] += 1

        return jsonify({"status": "success"}), 200

    @app.get("/latest")
    def get_latest_legacy():
        return jsonify(_arduino_latest)

    return app


# Eagerly create the app for `flask run` and gunicorn.
app = create_app()


if __name__ == "__main__":  # pragma: no cover
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = _bool_env("FLASK_DEBUG", default=True)
    app.run(host=host, port=port, debug=debug)
