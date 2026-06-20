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


# ---------------------------------------------------------------------------
# Profile completion logic (signup / login / onboarding gating).
#
# A profile is COMPLETE only when all required fields are present AND valid.
# "Profile exists" != "profile complete": the bootstrap creates a minimal
# (empty) profile that is intentionally NOT complete until onboarding fills it.
# ---------------------------------------------------------------------------
REQUIRED_PROFILE_FIELDS = (
    "name", "age", "gender", "height_cm", "weight_kg", "activity",
)
OPTIONAL_PROFILE_FIELDS = ("blood_type", "emergency_contact", "photo")
_VALID_GENDERS = {"male", "female", "other"}
_VALID_ACTIVITY = {"sedentary", "light", "moderate", "active", "very_active"}


def _field_is_valid(field: str, value: Any) -> bool:
    """True if a required field is PRESENT with a usable value.

    Completeness is presence-based on purpose: a real saved profile must not be
    bounced back to onboarding just because its gender/activity text doesn't
    match our canonical enum spelling (e.g. "Moderately active"). Only numeric
    fields are range-checked. Strict enum validation still applies to NEW input
    in clean_profile_input(); it does NOT gate completeness of existing data.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return False
    if field == "age":
        try:
            return 1 <= int(float(value)) <= 120
        except (TypeError, ValueError):
            return False
    if field in ("height_cm", "weight_kg"):
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False
    # name, gender, activity → present & non-empty is sufficient.
    return True


def profile_completeness(profile: Optional[Dict[str, Any]]):
    """Return (is_complete, missing_fields) from the REQUIRED fields.

    Tolerates legacy aliases `height`/`weight` for `height_cm`/`weight_kg` so
    older users created before the field rename are still recognised."""
    profile = profile or {}
    missing: list = []
    for field in REQUIRED_PROFILE_FIELDS:
        value = profile.get(field)
        if value in (None, ""):
            if field == "height_cm":
                value = profile.get("height")
            elif field == "weight_kg":
                value = profile.get("weight")
        if not _field_is_valid(field, value):
            missing.append(field)
    return (len(missing) == 0, missing)


def clean_profile_input(body: Dict[str, Any]):
    """Validate + normalise an incoming profile update.

    Returns (cleaned, invalid_fields). `cleaned` holds only the fields that were
    valid (required + any provided optional fields)."""
    body = body or {}
    cleaned: Dict[str, Any] = {}
    invalid: list = []

    name = body.get("name")
    if isinstance(name, str) and name.strip():
        cleaned["name"] = name.strip()
    else:
        invalid.append("name")

    try:
        age = int(body.get("age"))
        if 1 <= age <= 120:
            cleaned["age"] = age
        else:
            invalid.append("age")
    except (TypeError, ValueError):
        invalid.append("age")

    gender = body.get("gender")
    if isinstance(gender, str) and gender.strip().lower() in _VALID_GENDERS:
        cleaned["gender"] = gender.strip().lower()
    else:
        invalid.append("gender")

    height = body.get("height_cm", body.get("height"))
    try:
        h = float(height)
        if 30 <= h <= 300:
            cleaned["height_cm"] = h
        else:
            invalid.append("height_cm")
    except (TypeError, ValueError):
        invalid.append("height_cm")

    weight = body.get("weight_kg", body.get("weight"))
    try:
        w = float(weight)
        if 2 <= w <= 500:
            cleaned["weight_kg"] = w
        else:
            invalid.append("weight_kg")
    except (TypeError, ValueError):
        invalid.append("weight_kg")

    activity = body.get("activity")
    if isinstance(activity, str) and activity.strip().lower() in _VALID_ACTIVITY:
        cleaned["activity"] = activity.strip().lower()
    else:
        invalid.append("activity")

    # Optional fields pass through verbatim when provided.
    for opt in OPTIONAL_PROFILE_FIELDS:
        if opt in body and body[opt] is not None:
            cleaned[opt] = body[opt]

    return cleaned, invalid


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

    # Optional: warm up the Medical SLM in the background so the first
    # /ai/medical-slm request isn't a slow cold start (loading the model can
    # take ~1-2 min on CPU). Off by default; set MEDICAL_SLM_PRELOAD=1 to enable.
    # Skipped in demo mode (no model is ever loaded there).
    if _bool_env("MEDICAL_SLM_PRELOAD", default=False):
        import threading
        from .ml import medical_slm as _slm
        if not _slm.demo_mode_enabled():
            logger.info("medical-slm: preloading model in background…")
            threading.Thread(target=_slm.warmup, daemon=True).start()

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
            "source": "wesad_vscode_model_package",
            "latency_ms": pred.latency_ms,
        })

    @app.post("/ai/medical-slm")
    def medical_slm():
        """Answer a medical question with the local medical LoRA adapter
        (default: lightweight TinyLlama; Phi-3 optional via
        MEDICAL_SLM_ADAPTER_PATH). Body: {"question": "...", "context": "..."}.
        Returns {"answer", "model", "fallback"}.

        Loading the model is heavy and lazy (first call only). Behaviour:
          * empty question            -> 400 INVALID_INPUT
          * adapter files missing     -> 503 MODEL_UNAVAILABLE
          * load/generation failure   -> 200 with a SAFE deterministic fallback
                                         answer (fallback: true), so the demo
                                         stays usable on weak/CPU-only hardware
        Internal errors are logged but never surfaced as stack traces."""
        body = request.get_json(silent=True) or {}
        question = (body.get("question") or "").strip()
        context = body.get("context")
        if not question:
            return err(
                "INVALID_INPUT",
                "Provide a non-empty 'question'.",
                status=400,
            )
        from .ml import medical_slm as slm
        started = time.time()

        def _latency_ms() -> int:
            return int((time.time() - started) * 1000)

        # Demo mode: skip loading the model entirely and answer instantly with
        # the deterministic safe fallback. Real TinyLlama CPU generation is too
        # slow for a live demo; set MEDICAL_SLM_DEMO_MODE=true for reliability.
        if slm.demo_mode_enabled():
            return ok({
                "answer": slm.safe_fallback_answer(),
                "model": "safe-fallback",
                "fallback": True,
                "demo_mode": True,
                "latency_ms": _latency_ms(),
            })
        try:
            answer = slm.generate_medical_answer(question, context)
            return ok({
                "answer": answer,
                "model": slm.model_label(),
                "fallback": False,
                "demo_mode": False,
                "latency_ms": _latency_ms(),
            })
        except FileNotFoundError as exc:
            logger.warning("medical-slm: adapter unavailable (%s)", exc)
            return err(
                "MODEL_UNAVAILABLE",
                "The medical model adapter is not available on this server.",
                status=503,
            )
        except slm.DegenerateGenerationError:
            # The model produced empty/repetitive garbage (e.g. "Rome Rome…").
            # Hide it behind the safe fallback. Expected control flow → warning,
            # not a traceback.
            logger.warning(
                "medical-slm: degenerate_generation — returning safe fallback"
            )
            return ok({
                "answer": slm.safe_fallback_answer(),
                "model": "safe-fallback",
                "fallback": True,
                "demo_mode": False,
                "latency_ms": _latency_ms(),
            })
        except Exception:  # noqa: BLE001
            # Model could not load or generate (e.g. CPU OOM / runtime issue).
            # Keep the endpoint demo-ready with a safe deterministic answer
            # instead of a generic 500. The full traceback is logged only.
            logger.exception(
                "medical-slm: generation failed — returning safe fallback"
            )
            return ok({
                "answer": slm.safe_fallback_answer(),
                "model": "safe-fallback",
                "fallback": True,
                "demo_mode": False,
                "latency_ms": _latency_ms(),
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
        device_id = payload.get("device_id")  # optional device identifier
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
        logger.info(
            "telemetry.post START: uid=%s device_id=%s source=%s firebase_mode=%s "
            "targets=users/%s/{latest_telemetry,history}",
            uid, device_id or "(none)", clean.get("source", "unknown"),
            firebase.firebase_mode, uid
        )
        
        latest_ok = firebase.write_latest(uid, clean)
        history_ok = firebase.push_history(uid, clean)
        
        logger.info(
            "telemetry.post WRITE: uid=%s latest_ok=%s history_ok=%s "
            "paths=users/%s/latest_telemetry,users/%s/history",
            uid, latest_ok, history_ok, uid, uid
        )

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
        logger.info(
            "telemetry.post SUCCESS: uid=%s risk_level=%s timestamp=%s "
            "source=%s",
            uid, analysis["risk_level"], clean.get("timestamp"), 
            clean.get("source", "unknown")
        )
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
        bearer_present = auth_header.startswith("Bearer ")
        if bearer_present:
            claims = firebase.verify_id_token_claims(
                auth_header[len("Bearer "):].strip()
            ) or {}
            email = claims.get("email", "") or ""

        # Safe request log — field/flag names only, never the token or values.
        logger.info(
            "auth.bootstrap START: uid=%s auth_header_present=%s "
            "firebase_mode=%s targets=users/%s/{profile,goals}",
            uid, bearer_present, firebase.firebase_mode, uid,
        )

        now = _now_iso()
        write_backend = firebase.firebase_mode  # admin_sdk | rest | memory | …
        profile = firebase.read_profile(uid)
        goals = firebase.read_goals(uid)
        created_profile = False
        created_goals = False
        write_ok = True

        logger.debug(
            "auth.bootstrap uid=%s existing_profile=%s existing_goals=%s",
            uid, profile is not None, goals is not None,
        )

        # Explicit signup / profile-save path: a `profile` object in the body is
        # the one-screen signup form. Validate and persist it (this is the only
        # case where bootstrap overwrites profile fields). Completeness flags are
        # set from the result so a full signup form → profile_complete=true.
        incoming = body.get("profile")
        incoming = incoming if isinstance(incoming, dict) else None
        saved_submitted = False
        if incoming:
            cleaned, invalid = clean_profile_input(incoming)
            if invalid:
                return err(
                    "INVALID_INPUT",
                    "Invalid or missing required profile fields: "
                    + ", ".join(invalid),
                    status=400,
                    details={"invalid_fields": invalid},
                )
            existing = profile or {}
            created_profile = profile is None
            profile = {**existing, **cleaned}
            profile["uid"] = uid
            if email and not profile.get("email"):
                profile["email"] = email
            profile["created_at"] = existing.get("created_at") or now
            profile["updated_at"] = now
            _c, _ = profile_completeness(profile)
            profile["profile_complete"] = _c
            profile["onboarding_completed"] = _c
            write_ok = firebase.write_profile(uid, profile) and write_ok
            saved_submitted = True
            logger.info(
                "auth.bootstrap uid=%s SAVED submitted profile complete=%s "
                "path=users/%s/profile",
                uid, _c, uid,
            )

        if not profile:
            # Minimal profile — intentionally INCOMPLETE until onboarding fills
            # the required fields. Never fabricate required values here.
            profile = {
                "uid": uid,
                "email": email,
                "name": "",
                "age": None,
                "gender": None,
                "height_cm": None,
                "weight_kg": None,
                "activity": None,
                "blood_type": "",
                "emergency_contact": "",
                "photo": "",
                "profile_complete": False,
                "onboarding_completed": False,
                "created_at": now,
                "updated_at": now,
            }
            write_ok = firebase.write_profile(uid, profile) and write_ok
            created_profile = True
            logger.info(
                "auth.bootstrap uid=%s CREATED profile write_ok=%s path=users/%s/profile",
                uid, write_ok, uid,
            )

        if not goals:
            goals = {"steps": 5000, "calories": 500, "sleep": 8}
            write_ok = firebase.write_goals(uid, goals) and write_ok
            created_goals = True
            logger.info(
                "auth.bootstrap uid=%s CREATED goals write_ok=%s path=users/%s/goals",
                uid, write_ok, uid,
            )

        # Completeness drives onboarding routing, inferred from the REQUIRED
        # fields (not from a flag). A freshly bootstrapped profile is incomplete.
        complete, missing = profile_completeness(profile)
        # Legacy / existing users: required fields present but no explicit flag →
        # infer completion and best-effort backfill the flags + updated_at via
        # the Admin SDK. We write back the full (read) profile, so NO user value
        # is overwritten — only the flags/updated_at are added. Never fail the
        # request over a flag write.
        if complete and not profile.get("profile_complete"):
            profile["profile_complete"] = True
            profile["onboarding_completed"] = True
            profile["updated_at"] = _now_iso()
            try:
                firebase.write_profile(uid, profile)
                logger.debug("auth.bootstrap uid=%s backfilled profile_complete flag", uid)
            except Exception as e:  # noqa: BLE001
                logger.warning("auth.bootstrap uid=%s failed to backfill flags: %s", uid, e)

        # Safe debug log: field names only — never values/tokens/secrets.
        logger.info(
            "auth.bootstrap uid=%s profile_complete=%s needs_onboarding=%s "
            "missing_fields=%s present_fields=%s",
            uid,
            complete,
            not complete,
            missing,
            [f for f in REQUIRED_PROFILE_FIELDS if f not in missing],
        )

        # A write was attempted but did NOT persist (e.g. REST read-only or
        # admin_error in real Firebase mode) → fail loudly instead of pretending
        # the user was created. Never silently swallow a failed RTDB write.
        if (created_profile or created_goals or saved_submitted) and not write_ok:
            logger.error(
                "auth.bootstrap uid=%s FAILED: write_backend=%s write_ok=%s "
                "firebase_error=%s",
                uid, write_backend, write_ok, firebase.last_error,
            )
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

        logger.info(
            "auth.bootstrap uid=%s SUCCESS: write_backend=%s created_profile=%s "
            "created_goals=%s write_ok=%s paths=users/%s/{profile,goals}",
            uid, write_backend, created_profile, created_goals, write_ok, uid,
        )

        return ok({
            "uid": uid,
            "created_profile": created_profile,
            "created_goals": created_goals,
            "profile_complete": complete,
            "needs_onboarding": not complete,
            "missing_fields": missing,
            "firebase_mode": write_backend,
            "write_backend": write_backend,
            "write_ok": write_ok,
            "profile": profile,
            "goals": goals,
        })

    @app.get("/api/me")
    def api_me():
        """The signed-in user's profile + goals + completeness, for routing.
        Auth: `Authorization: Bearer <firebase_id_token>` (token-first; the uid
        comes from the verified token, never the client)."""
        uid = _active_uid()
        if not uid:
            return err("UNAUTHORIZED", "No authenticated user.", 401)
        profile = firebase.read_profile(uid)
        goals = firebase.read_goals(uid)
        complete, missing = profile_completeness(profile)
        logger.info(
            "auth.me uid=%s present=%s missing=%s profile_complete=%s "
            "needs_onboarding=%s",
            uid,
            [f for f in REQUIRED_PROFILE_FIELDS if f not in missing],
            missing, complete, not complete,
        )
        return ok({
            "uid": uid,
            "profile": profile,
            "goals": goals,
            "profile_complete": complete,
            "needs_onboarding": not complete,
            "missing_fields": missing,
        })

    @app.put("/api/profile/me")
    def update_profile_me():
        """Update the signed-in user's profile (onboarding / profile edit).
        Auth: Bearer token (verified uid only). Validates required fields,
        preserves created_at, sets updated_at, and sets profile_complete +
        onboarding_completed when the required fields are valid. Writes ONLY via
        the backend (Admin SDK) — the client never writes Firebase directly."""
        uid = _active_uid()
        if not uid:
            return err("UNAUTHORIZED", "No authenticated user.", 401)
        body = request.get_json(silent=True) or {}
        cleaned, invalid = clean_profile_input(body)
        if invalid:
            return err(
                "INVALID_INPUT",
                "Invalid or missing required fields: " + ", ".join(invalid),
                status=400,
                details={"invalid_fields": invalid},
            )

        existing = firebase.read_profile(uid) or {}
        now = _now_iso()
        merged: Dict[str, Any] = {**existing, **cleaned}
        merged["uid"] = uid
        merged["created_at"] = existing.get("created_at") or now
        merged["updated_at"] = now
        complete, missing = profile_completeness(merged)
        merged["profile_complete"] = complete
        merged["onboarding_completed"] = complete

        if not firebase.write_profile(uid, merged):
            return err(
                "FIREBASE_WRITE_FAILED",
                "Could not save the profile to Firebase. The backend must run "
                "with Admin SDK credentials to write the locked database.",
                status=500,
                details={
                    "uid": uid,
                    "write_backend": firebase.firebase_mode,
                    "write_ok": False,
                    "firebase_error": firebase.last_error,
                },
            )

        logger.info(
            "profile/me uid=%s profile_complete=%s write_backend=%s",
            uid, complete, firebase.firebase_mode,
        )
        return ok({
            "uid": uid,
            "profile": merged,
            "profile_complete": complete,
            "needs_onboarding": not complete,
            "missing_fields": missing,
            "write_backend": firebase.firebase_mode,
            "write_ok": True,
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

        # Resolve which user this bracelet reading belongs to (device pairing),
        # in priority order. The unsafe "last frontend uid" guessing is NOT used.
        #   1. explicit user_id/uid in the payload (paired client / testing)
        #   2. PRODUCTION: device pairing via /devices/{device_id}/assigned_uid
        #   3. DEMO/DEV ONLY: FIREBASE_ACTIVE_UID (clearly not a production path)
        explicit_uid = payload.get("user_id") or payload.get("uid")
        device_id = payload.get("device_id")
        assigned_uid = (
            firebase.read_device_assigned_uid(device_id) if device_id else None
        )
        demo_uid = os.environ.get("FIREBASE_ACTIVE_UID")  # demo/dev fallback only
        uid = explicit_uid or assigned_uid or demo_uid
        if not uid:
            return err(
                "NO_TARGET_USER",
                "No user is paired with this bracelet. Send user_id, pair the "
                "device at /devices/{device_id}/assigned_uid, or set "
                "FIREBASE_ACTIVE_UID for a demo.",
                status=400,
            )

        # Persist under the resolved user. Fail loudly if the write does not
        # land in the real database — never pretend success.
        if not firebase.write_latest(uid, telemetry):
            logger.error(
                "update_telemetry uid=%s write FAILED (write_backend=%s err=%s)",
                uid, firebase.firebase_mode, firebase.last_error,
            )
            return err(
                "FIREBASE_WRITE_FAILED",
                "Could not persist telemetry to Firebase.",
                status=500,
                details={
                    "uid": uid,
                    "write_backend": firebase.firebase_mode,
                    "write_ok": False,
                    "firebase_error": firebase.last_error,
                },
            )
        firebase.push_history(uid, telemetry)
        logger.info(
            "update_telemetry uid=%s device_id=%s source=%s wrote "
            "users/%s/{latest_telemetry,history}",
            uid, device_id, telemetry.get("source"), uid,
        )

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
