# Observability & Logging

## Logs

Every request emits one line on stdout from `backend.logging_config`:

```
2026-05-26T10:00:00+0000 INFO pulseguard.access [Thread-3] rid=a1b2c3d4e5f6 method=POST path=/api/telemetry status=200 latency_ms=8 ip=127.0.0.1
```

Fields:
- `rid` — `X-Request-ID` header (server-generated if the caller didn't send one)
- `method`, `path`, `status` — standard
- `latency_ms` — wall-clock from `before_request` to `after_request`
- `ip` — `X-Forwarded-For` first, otherwise `remote_addr`

The same `rid` is also echoed back in the response header so a failing
request in the browser can be matched to a line in the backend log.

Service-specific loggers (also stdout):
- `pulseguard.firebase` — once-per-init line telling you whether the real RTDB
  is connected or the in-memory fallback is active
- `pulseguard.chatbot` — model load / fallback / generation timeout

## Endpoints

- `GET /health` — version, uptime, sub-service status (Firebase mode, chatbot
  status). Used by Docker `HEALTHCHECK` and any external uptime probe.
- `GET /api/metrics` — in-process counters. Replace with `prometheus-flask-exporter`
  when you want a real Prometheus / Grafana stack.

## Frontend

- A persistent "stale data" badge (`<TelemetrySourceBadge>`) on the dashboard
  warns the user when the last update is older than 30 s.
- Console logs prefix Firebase init lines with `[firebase]` so it's obvious
  in DevTools when env vars are missing.

## How do we know the system is healthy?

1. `curl http://localhost:5000/health` returns `{"ok": true, ...}`.
2. `docker compose ps` shows `healthy` on the backend service.
3. The dashboard's source badge shows "Live · Firebase" (or "Live · Backend")
   and a recent update timestamp.

## How do we debug a failure?

1. Read the browser DevTools → Network tab. Failed responses include the
   standard error envelope and an `X-Request-ID` header.
2. `grep` the backend log for `rid=<id>` to locate the exact request.
3. If the chatbot reply looks wrong: check the `source` field in the response
   payload — `rule_based` means the model wasn't loaded; `model:base` means
   TinyLlama base; `model:adapter` means PEFT adapter active.
4. If a write didn't reach Firebase: check the once-per-init line from
   `pulseguard.firebase` — `mode=memory` means the in-memory fallback was used.

## How do we know Firebase is updating?

- The dashboard's source badge says "Live · Firebase".
- `/health` reports `services.firebase = "firebase"`.
- Open the Firebase Console → Realtime Database and watch
  `users/<uid>/latest_telemetry` update.

## How do we know the AI failed?

- The chatbot reply's `source` field will be `rule_based`.
- `pulseguard.chatbot` logs a warning with the exception (e.g. CUDA OOM, missing weights).
- `/health` reports `services.chatbot != "adapter"`.

## Suggested production upgrades

- Ship logs to Loki / CloudWatch / Datadog.
- Replace `/api/metrics` with Prometheus + Grafana.
- Add `sentry-sdk[flask]` for exception aggregation.
- Add a Grafana panel showing `alerts_raised` per 5-minute window so the
  team can spot the system going noisy.
