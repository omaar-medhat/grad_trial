# PulseGuard AI - REST API Reference

Base URL (dev): `http://127.0.0.1:5000`
In the web app, all endpoints are reached via the Vite proxy at `/api/*`
(see [vite.config.ts](../vite.config.ts)).

## Response envelope

Every response — success or error — uses the same shape:

```json
// success
{ "ok": true,  "data": <any>, "message": "Success" }

// error
{ "ok": false, "error": { "code": "INVALID_INPUT", "message": "..." } }
```

Every response includes an `X-Request-ID` header (the same value is in the
access log) so a failing request can be correlated with the server log.

## Common error codes

| code | http | when |
|---|---|---|
| `INVALID_INPUT` | 400 | Missing field or physically impossible value (e.g., HR=500) |
| `NOT_FOUND` | 404 | Route does not exist |
| `METHOD_NOT_ALLOWED` | 405 | Wrong HTTP verb |
| `INTERNAL_ERROR` | 500 | Unhandled exception (also logged with the request ID) |

---

## `GET /health`

Liveness probe — used by Docker, k6, and Kubernetes-style readiness checks.

**Response 200**
```json
{
  "ok": true,
  "data": {
    "status": "ok",
    "version": "1.0.0",
    "uptime_seconds": 42,
    "services": { "firebase": "memory", "chatbot": "rule_based" }
  },
  "message": "Success"
}
```

## `GET /api/metrics`

Lightweight in-process counters (no Prometheus dependency).

**Response 200**
```json
{
  "ok": true,
  "data": {
    "uptime_seconds": 42,
    "requests_total": 123,
    "telemetry_ingested": 50,
    "alerts_raised": 3,
    "chat_replies": 4,
    "requests_by_path": { "/api/telemetry": 50, "/health": 8 },
    "firebase_mode": "memory",
    "chatbot_status": "rule_based"
  }
}
```

## `POST /api/telemetry`

Ingest a wearable / simulator reading. Runs validation → rule engine → persists
to `users/{uid}/latest_telemetry` + `users/{uid}/history/<push_id>`, and pushes
an alert when `risk_level != "normal"`.

**Body**
```json
{
  "user_id": "demo-user-001",
  "heart_rate": 78,
  "spo2": 97,
  "temperature_c": 36.8,
  "steps": 1200,
  "calories": 45.5,
  "sleep_duration_sec": 25200,
  "battery_level": 82,
  "timestamp": 1779716107821
}
```

**Validation rules** (see [backend/anomaly_detection.py](../backend/anomaly_detection.py))

| field | type | required | range |
|---|---|---|---|
| `heart_rate` | number | ✅ | 20–250 bpm |
| `spo2` | number | ✅ | 50–100 % |
| `temperature_c` | number | ✅ | 25–45 °C (Celsius only) |
| `steps` | integer | – | 0–200 000 |
| `calories` | number | – | 0–20 000 |
| `sleep_duration_sec` | integer | – | 0–86 400 |
| `battery_level` | integer | – | 0–100 % (bracelet charge; only stored when sent) |
| `activity_level` | integer | – | 0–100 instantaneous motion index (only stored when sent) |
| `source` | string | – | `simulator` \| `real_bracelet` \| `uploaded_dataset` (defaults to `real_bracelet` on `/api/telemetry`) |
| `timestamp` | integer | ✅ | ms epoch |
| `user_id` | string | – | falls back to `DEFAULT_DEMO_UID` |

The response enriches both the stored `telemetry` and the `analysis` with:
- **`wellness_score`** (0–100) — how far vitals sit from the healthy band.
- **`activity`** (`resting`/`active`/`walking`/`running`/`unknown`) — coarse,
  deterministic label from `activity_level` + heart rate.
- **`stress`** `{label, score}` (`relaxed`/`normal`/`stressed`, 0–100) — an
  elevated heart rate while still is the stress signature; exertion is not
  flagged.

All three are explainable, deterministic indicators — **not** medical
diagnoses or trained-NN outputs. The `source` field lets the dashboard tell
simulated data from a real bracelet, so no schema change is needed when the
hardware arrives.

When `battery_level` is present and ≤20 %, the backend raises a **device-level**
alert (`source: "device"`, `risk_level` `warning` ≤20 % / `high` ≤5 %). This is
kept separate from the clinical `risk_level` so a flat battery never masks or
inflates a vitals assessment. The physical bracelet ([firmware/](../firmware/),
[ble_spec.md](./ble_spec.md)) sends the same field.

**Response 200**
```json
{
  "ok": true,
  "data": {
    "telemetry": { "...": "the validated, persisted reading + risk_level + alert_message" },
    "analysis": {
      "risk_level": "normal",
      "alert_message": "Vitals are within normal range.",
      "reasons": [],
      "rule_hits": []
    }
  },
  "message": "Telemetry stored"
}
```

**Response 400**
```json
{ "ok": false, "error": { "code": "INVALID_INPUT", "message": "heart_rate value 500.0 is outside physically valid range [20, 250]" } }
```

## `GET /api/latest?uid=...`

Latest reading for the given user (or `null` if none yet).

## `GET /api/history?uid=...&limit=100`

Up to `limit` most-recent records, oldest → newest. Max `limit` is 1000.

## `GET /api/alerts?uid=...&limit=50`

Up to `limit` most-recent alerts (oldest → newest). Max `limit` is 500.

## `GET /api/reports/daily?uid=...` · `GET /api/reports/weekly?uid=...`

Aggregates the user's stored history within the period (last 24 h / 7 days)
into a summary: reading count, HR avg/min/max, SpO₂, temperature, steps taken,
average wellness, risk breakdown, alert counts, and a plain-language `summary`
string (always with a "not a medical diagnosis" disclaimer).

```json
{ "ok": true, "data": {
  "period": "daily", "count": 42,
  "heart_rate": { "avg": 78, "min": 58, "max": 132 },
  "spo2": { "avg": 97, "min": 93 },
  "steps_taken": 1840, "wellness_avg": 88,
  "risk_breakdown": { "normal": 39, "warning": 3 },
  "alerts_total": 3, "alerts_high": 0,
  "summary": "Over this daily period we logged 42 readings. …"
} }
```

## `GET /api/reports/export.csv?uid=...&limit=1000`

Downloads the user's history as `text/csv` (Content-Disposition attachment).
Stable column order; one row per reading. Max `limit` is 5000.

## `POST /api/ml/predict/stress`

Runs the **WESAD stress model** loaded from the self-contained package
`backend/models/wesad_vscode_model_package/` (best of a 15-model bake-off on the
WESAD dataset with a group/leave-subjects split; best **DeepDNN**, accuracy
0.93, ROC-AUC 0.98). It is a **binary** classifier: `non_stress` / `stress`.

The model expects the **252 WESAD window features** (wrist BVP/EDA/TEMP/ACC +
chest ECG/EMG/EDA/ACC, 60 s windows). Pass them as a `features` object (keyed by
feature name) or a `vector` list in the canonical order (see
`/api/models` → `stress_classifier`). Missing features are imputed.

> This model is **not** driven by the bracelet's live HR/SpO₂/temp/activity —
> those aren't the WESAD signal set. The dashboard's live stress chip uses the
> deterministic `stress_level` heuristic; this endpoint serves the real model
> for WESAD-format input.

**Body** (either form)
```json
{ "vector": [/* 252 numbers in feature order */] }
{ "features": { "w_eda_mean": 4.2, "c_ecg_mean": 0.1, "w_temp_mean": 33.5 } }
```

**Response 200**
```json
{ "ok": true, "data": {
  "label": "non_stress",
  "confidence": 0.9953,
  "probabilities": { "non_stress": 0.9953, "stress": 0.0047 },
  "model_name": "MLP",
  "latency_ms": 3
} }
```

**Errors**: `503 MODEL_UNAVAILABLE` if the artifact is missing (with a clear
message), `400 INVALID_INPUT` if no/odd-length features are supplied.

## `POST /api/simulate`

Generates one synthetic reading server-side and ingests it. Useful for live
demos when no wearable is connected. Same response shape as `/api/telemetry`.
Readings from this endpoint are tagged `source: "simulator"`.

**Body** *(all optional)*
```json
{ "user_id": "demo-user-001", "mode": "running" }
```

`mode` forces a demo scenario instead of the weighted-random default. Omit it
for random. Invalid modes return `400 INVALID_INPUT`.

## `GET /api/simulate/modes`

Lists the scenarios the simulator can be forced into, e.g.
`["resting","walking","running","sleep","fever","high_fever","stress","anomaly","low_battery"]`.
`low_battery` forces a depleted cell (raising the device battery alert);
`anomaly` randomly picks an abnormal physiology (hypoxia / bradycardia / fever).

## `POST /api/chat`

Healthcare chatbot. Always returns a safe, disclaimer-bearing answer. If the
fine-tuned TinyLlama model is loaded it is used; otherwise the deterministic
rule-based composer fires.

**Body**
```json
{
  "user_id": "demo-user-001",
  "message": "How am I doing?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "..." }
  ]
}
```

**Response 200**
```json
{
  "ok": true,
  "data": {
    "response": "Your current readings look within the normal resting range. ...",
    "source": "rule_based",      // rule_based | model:base | model:adapter
    "latency_ms": 4
  }
}
```

**Safety guarantees applied to every reply:**
- "I am an AI assistant, not a doctor" disclaimer always appended.
- For `high` risk telemetry, an emergency advice line is prepended.
- Repeated-word runs ("help help help help…") are collapsed.
- `max_new_tokens=180`, greedy decoding for safety/determinism.
- Hard wall-clock cap via `CHATBOT_TIMEOUT_SECONDS`.

## `POST /chat` *(legacy)*

Alias of `/api/chat`. Kept for backward compatibility with the original
`chatbot.py` and the existing `Chat.tsx` frontend page.

---

## OpenAPI / Swagger

A minimal [`openapi.yaml`](./openapi.yaml) is provided in this folder. Render
it with [Swagger Editor](https://editor.swagger.io/) for a clickable browser.
