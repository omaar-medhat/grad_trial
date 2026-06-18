# Performance & Load Testing

## How we test

Two equivalent scripts target the four hot endpoints with a realistic
read/write mix (`GET /health` 10% · `POST /api/telemetry` 40% · `GET /api/latest` 30% · `POST /api/chat` 20%):

- [load_tests/k6_backend_test.js](../load_tests/k6_backend_test.js)
- [load_tests/locustfile.py](../load_tests/locustfile.py)

Both run against the same `gunicorn --workers 2 --threads 4` backend used in
the Docker image.

## Run the scenarios

```bash
# Required: backend running on http://127.0.0.1:5000
# Optional: enable the in-memory simulator pumping data
# (the load tests work either way — they POST their own payloads)

k6 run -e USERS=10 -e DURATION=30s load_tests/k6_backend_test.js
k6 run -e USERS=25 -e DURATION=60s load_tests/k6_backend_test.js
k6 run -e USERS=50 -e DURATION=2m  load_tests/k6_backend_test.js
```

## Reference numbers (record yours here after running)

The table below is intentionally blank for the values you should measure on
your own hardware — fill it in and screenshot the k6 / Locust summary into
`final_evidence/load_tests/`.

| Scenario | VUs | RPS | Avg ms | p95 ms | Error rate | Chat p95 ms | Notes |
|---|---|---|---|---|---|---|---|
| Light | 10 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | rule-based chatbot |
| Normal | 25 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | rule-based chatbot |
| Heavy | 50 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | rule-based chatbot |
| Heavy + AI | 50 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | `LOAD_CHATBOT_MODEL=1`, CPU only |

Thresholds we already enforce inside `k6_backend_test.js`:

- `http_req_failed < 2%`
- `/health` p95 < 200 ms
- `/api/latest` p95 < 400 ms
- `/api/telemetry` p95 < 800 ms
- `/api/chat` p95 < 3000 ms (rule-based)

## Known bottlenecks and what we did

| Bottleneck | Impact | Mitigation |
|---|---|---|
| TinyLlama CPU inference (~5–15 s/turn) | Crushes p95 of `/api/chat` | Model is opt-in (`LOAD_CHATBOT_MODEL`); rule-based fallback < 5 ms |
| Loading the model per request | Wastes seconds on every call | Loaded once at startup, guarded by a `threading.Lock` |
| Repeated identical telemetry reads | Network chatter | Frontend uses Firebase live push (no polling) when configured |
| In-memory fallback bound | Memory grows on long runs | `_FALLBACK_HISTORY_CAP=500`, `_FALLBACK_ALERTS_CAP=100` per user |
| CORS preflight on every request | Adds RTT | `OPTIONS` short-circuited by flask-cors |
| Heavy Firebase reads on dashboard | Bandwidth | `limitToLast(120)` on history, `limitToLast(20)` on alerts |
| Render storms from 500ms polling | Old web dashboard had this | New dashboard reads from Firebase listener; demo simulator runs at 1s |

## Future improvements

- Replace in-process counters with Prometheus (`prometheus_flask_exporter`).
- Add HTTP keep-alive + connection pooling to the simulator CLI.
- Push the chatbot behind a small worker queue so `/api/chat` never blocks the
  Flask process (e.g. RQ + Redis, or a separate model-serving sidecar).
- Cache `/api/latest` for ~500 ms when traffic is high.
