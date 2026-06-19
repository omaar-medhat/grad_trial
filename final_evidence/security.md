# Security

## Input validation
- Every endpoint validates its body and rejects bad input with
  `400 INVALID_INPUT` **before** touching a model:
  - `/ai/medical-slm` → empty/missing `question` → 400 (verified).
  - `/api/ml/predict/stress` → wrong-length / non-252 features → 400 (verified).
  - Telemetry ingest validates ranges/types via `telemetry_contract.py` and
    `anomaly_detection.TelemetryValidationError`.
- JSON is parsed with `request.get_json(silent=True)` so malformed bodies do not
  crash the worker — they become a clean 400.

## No stack-trace leakage
- All responses go through the `responses.py` envelope
  (`{ok:false, error:{code, message}}`). Messages are short and human-readable.
- Unexpected exceptions are caught, logged server-side with
  `logger.exception(...)`, and returned to the client as a **generic**
  `500 MODEL_ERROR` / `503` — the traceback never reaches the client.
- Verified error bodies contain only `code` + `message`, no internals.

## Secrets management
- Secrets are read from the environment / `backend/.env` (loaded via
  `python-dotenv`); `.env.example` documents the variables.
- `.env` is **git-ignored** — do not commit real Firebase keys, API keys, or
  service-account JSON. Only `.env.example` (placeholders) is committed.
- Provider LLM keys (`GROQ_API_KEY`, `OPENAI_API_KEY`, …) are optional and read
  from env only.

## Firebase / auth
- Auth is token-first: a verified **Firebase ID token** (`Authorization:
  Bearer …`) is the authoritative user id; a client-claimed `uid` is ignored
  when a valid token is present (`_active_uid` in `app.py`).
- `REQUIRE_AUTH=1` makes a valid token mandatory; missing/invalid → `401`.
- Data is **user-scoped** (tested in `test_user_scoped.py`) so one user cannot
  read another's telemetry.
- No real credentials → automatic **in-memory** fallback, so the demo never
  requires committing secrets.

## Malicious / abusive input handling
- **Rate limiting** (`flask-limiter`): default `120/min`, `2000/hour` →
  `429 RATE_LIMIT_EXCEEDED` (tested in `test_rate_limit.py`).
- **CORS** restricted via `CORS_ORIGINS` (configurable).
- **No-store** cache headers on API/health responses so live telemetry is never
  served stale from a proxy/browser cache.
- Chatbot/medical replies carry a **medical disclaimer** and emergency-care
  guidance (safety rails in `chatbot_service.py` and the SLM prompt), reducing
  harm from adversarial health prompts.
- Oversized prompts are bounded by `max_new_tokens` and the model's context
  window; generation cannot run unbounded.

## Known gaps / future work
- Add request body size limits (`MAX_CONTENT_LENGTH`).
- Add structured audit logging for auth failures.
- Run a dependency vulnerability scan (`pip-audit`) in CI.
