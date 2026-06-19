# Observability

## Logs
- Configured centrally in `backend/logging_config.py` (`configure_logging` +
  `install_request_logging`).
- **Per-request access log** — one line per request with method, path, status,
  latency, request id, and client IP, e.g.:
  ```
  INFO pulseguard.access rid=034fedecc043 method=POST path=/ai/medical-slm status=400 latency_ms=0 ip=127.0.0.1
  ```
- **Component loggers** (namespaced): `pulseguard.app`, `pulseguard.ml.stress`,
  `pulseguard.ml.medical_slm`, `pulseguard.chatbot`, `pulseguard.firebase`.
- Log level via `LOG_LEVEL` env (default `INFO`).

## How errors are traced
- Each request carries a **request id (`rid`)** in the access log; the same rid
  ties the access line to any warning/error logged during that request.
- Handled failures log a `WARNING` with context (e.g.
  `medical-slm: adapter unavailable (...)`) and return a safe error envelope.
- Unexpected failures use `logger.exception(...)` so the **full traceback is in
  the server log**, while the client only gets `{ok:false, error:{code,message}}`.

## What "health" means
`GET /health` returns:
- `status: "ok"` and `version` — process is alive,
- `firebase_mode` + `firebase_read_ok` — storage backend reachable (or
  `memory` fallback),
- `services` — per-model status (`trained` / `stub`) **without loading models**.

A `stub` service means the model file/package is missing — the API is up but
that model endpoint will answer `503`.

## What to check when something fails
1. `GET /health` → which `service` is `stub` or which `firebase_*` is failing.
2. `GET /api/models` → per-model `error` / `missing_files`.
3. Server log → find the request `rid`, read the `WARNING`/`exception` lines.
4. `python scripts/check_environment.py` → missing/mismatched packages.
5. `python scripts/check_wesad_model.py` → WESAD load/predict end-to-end.

## Proposed metrics (production)
Already exposed in-process at `GET /api/metrics` (counters: requests_total,
requests_by_path, telemetry_ingested, alerts_raised, uptime). For production,
export these to Prometheus/Grafana and add:

| Metric | Why |
|--------|-----|
| Request **latency** histogram (per route) | Detect slow endpoints / SLO breaches |
| **Error rate** (4xx/5xx per route) | Catch regressions and bad inputs |
| **Throughput** (req/s) | Capacity planning |
| **Model failures** (load + inference errors, per model) | Distinguish model outages from API issues |
| Model **inference latency** (stress, SLM) | The heavy path; watch separately |
