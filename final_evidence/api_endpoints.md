# API Endpoints

All responses use one envelope (`backend/responses.py`):

```json
// success
{ "ok": true, "data": { ... }, "message": "Success" }
// error
{ "ok": false, "error": { "code": "STRING_CODE", "message": "human readable" } }
```

Error codes: `INVALID_INPUT` (400), `MODEL_UNAVAILABLE` (503),
`MODEL_ERROR` (500), `RATE_LIMIT_EXCEEDED` (429), `AUTH_REQUIRED` (401).
Internal stack traces are **never** put in responses — they are logged only.

---

## GET `/health` (alias `/api/health`)
Lightweight liveness — **does not load any model**.

Verified response:
```json
{ "ok": true, "message": "Success", "data": {
  "status": "ok", "version": "1.0.0", "uptime_seconds": 60,
  "firebase_mode": "memory", "firebase_read_ok": true,
  "services": { "chatbot": "pulseguard_ai", "firebase": "memory",
    "ml_risk": "trained", "ml_anomaly": "trained",
    "ml_intent": "trained", "ml_stress": "trained" } } }
```

## GET `/api/models` (alias `/api/models/status`)
Read-only metadata for every model (risk, anomaly, intent, activity, WESAD
stress, LLM). The stress entry reports the WESAD package (DeepDNN, 252 features,
threshold 0.88) without loading TensorFlow.

## POST `/api/ml/predict/stress`
Runs the **WESAD DeepDNN** model. Body is the **252 WESAD features**, either as
a `features` object (keyed by feature name) or a `vector` list.

Request:
```json
{ "vector": [/* 252 floats */] }      // or  { "features": { "w_bvp_mean": -0.43, ... } }
```
Success:
```json
{ "ok": true, "data": {
  "prediction": "stress", "prediction_id": "…", "confidence": 0.9969,
  "probabilities": { "non_stress": 0.003, "stress": 0.997 },
  "model_name": "DeepDNN", "model_type": "stress",
  "source": "wesad_vscode_model_package", "latency_ms": 12 } }
```
Invalid input (wrong length / not 252 features) — **verified**:
```json
// HTTP 400
{ "ok": false, "error": { "code": "INVALID_INPUT",
  "message": "Provide the 252 WESAD features as a 'features' object or a 'vector' list." } }
```
If the model package is unavailable → `503 MODEL_UNAVAILABLE`.

## POST `/ai/medical-slm`
Local Medical SLM (default = lightweight TinyLlama adapter; Phi-3 optional via
`MEDICAL_SLM_ADAPTER_PATH`). Model loads **lazily** on first call.

Request:
```json
{ "question": "I have had a sore throat and mild fever for 2 days. What should I do?",
  "context": "age 30, no chronic conditions" }
```
Success:
```json
{ "ok": true, "data": {
  "answer": "…", "model": "tinyllama-1.1b-chat-v1.0-lora-medical" },
  "message": "Success" }
```
> `model` is reported truthfully by `model_label()` — it shows
> `phi-3-mini-4k-instruct-lora-medical` only when the Phi-3 adapter is loaded.

Invalid input (empty question) — **verified**:
```json
// HTTP 400
{ "ok": false, "error": { "code": "INVALID_INPUT", "message": "Provide a non-empty 'question'." } }
```
Adapter missing → `503 MODEL_UNAVAILABLE`; generation error → `500 MODEL_ERROR`
(generic message, no stack trace).

## Other endpoints (existing)
`GET /` (banner), `GET /api/metrics`, `POST /api/telemetry`,
`GET /api/latest`, `GET /api/vitals/latest`, `GET /api/history`,
`GET /api/alerts`, `GET /api/reports/daily|weekly`, `GET /api/reports/export.csv`,
`POST /api/simulate`, `POST /api/chat`.
