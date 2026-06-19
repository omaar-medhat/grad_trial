# Architecture

## Chosen architecture
A **modular monolith backend** (Flask) that serves a REST API, with ML kept in
self-contained modules/packages, plus thin frontend/mobile clients and Firebase
for realtime telemetry storage.

```
                 ┌─────────────────────────────────────────────┐
   Web dashboard │  Flask API (backend/app.py)                  │
   Mobile (Expo) │   ├─ telemetry ingest + analysis             │
        Firmware │   ├─ rule engine (anomaly_detection, alerts) │
        Sensors  │   ├─ ML modules (backend/ml/*)               │
       ──────────┤   │    risk / anomaly / intent / stress       │
   HTTP / JSON   │   ├─ Medical SLM (backend/ml/medical_slm.py) │
                 │   └─ chatbot_service + llm_client            │
                 │  Model packages (backend/models/*)           │
                 │  Firebase (realtime DB) — telemetry/alerts   │
                 └─────────────────────────────────────────────┘
```

## Why this architecture
- **Single deployable backend** — simplest to run, demo, and grade; one
  `flask run` brings up the whole API. No microservice orchestration overhead
  for a graduation-scale project.
- **ML isolated behind modules/packages** — each model (`backend/ml/*` and the
  self-contained `backend/models/wesad_vscode_model_package/`) loads **lazily**
  and can fail independently without taking down the API.
- **Stateless API + Firebase for state** — horizontally scalable; the backend
  holds no session state, so it can run behind multiple workers (`gunicorn`).
- **Clients are thin** — dashboard/mobile only render and call the API, so
  business logic lives in one place.

## Components and responsibilities
| Component | File(s) | Responsibility |
|-----------|---------|----------------|
| API + routing | `backend/app.py` | All HTTP endpoints, error envelope, rate limiting, CORS |
| Telemetry analysis | `anomaly_detection.py`, `alerts.py` | Deterministic rule engine (AHA/WHO ranges) |
| Risk / anomaly / intent ML | `backend/ml/*.py` + `backend/models/*.joblib` | Trained NN models, lazy-loaded via `registry.py` |
| WESAD stress | `backend/ml/stress_classifier.py` + `backend/models/wesad_vscode_model_package/` | DeepDNN binary stress classifier |
| Medical SLM | `backend/ml/medical_slm.py` + `backend/models/medical_slm_adapter/` | Local LoRA chatbot (`/ai/medical-slm`) |
| Chatbot | `chatbot_service.py`, `llm_client.py` | Rule-based + optional LLM replies |
| Storage | `firebase_service.py` | Realtime telemetry/alerts (in-memory fallback) |
| Response envelope | `responses.py` | `{ok, data, message}` / `{ok:false, error}` |

## Failure points and handling
| Failure | Handling |
|---------|----------|
| ML model file missing | `load_or_stub()` returns a **stub**; API stays up, endpoint returns `503 MODEL_UNAVAILABLE` |
| TensorFlow/heavy dep missing | Lazy load — base API still boots; only the model endpoint degrades |
| Medical SLM OOM / load error | Caught; `503` with a safe message, **no stack trace** leaked |
| Firebase unreachable | Falls back to **in-memory** store (`firebase_mode: memory`) |
| Bad client input | Validated → `400 INVALID_INPUT` |
| Request floods | `flask-limiter` → `429 RATE_LIMIT_EXCEEDED` |
| scikit-learn version drift | Pinned `scikit-learn==1.6.1` so the saved WESAD preprocessor unpickles |
