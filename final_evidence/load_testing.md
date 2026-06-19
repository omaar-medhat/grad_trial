# Load Testing

## Plan
Lightweight, dependency-free load testing using only the Python standard
library. The goal is to show the API sustains concurrent traffic with bounded
latency, not to benchmark the ML models (which are the heavy, separately-scaled
part).

- **Target by default:** `GET /health` — lightweight, loads no model, so it is
  safe to run live during a demo and isolates pure API/serving overhead.
- **Tool:** [`backend/scripts/load_test_backend.py`](../backend/scripts/load_test_backend.py)
  — concurrent requests via `ThreadPoolExecutor`, reports totals, success/
  failure counts, average/median/p95/p99 latency, and requests/sec.
- **No external services** required — only a running backend.

## How to run

```powershell
# terminal 1
flask --app app run --port 8000
# terminal 2
python scripts/load_test_backend.py -n 500 -c 50
```

Other targets:
```powershell
python scripts/load_test_backend.py --endpoint /api/health -n 200 -c 20
python scripts/load_test_backend.py --endpoint /ai/medical-slm \
    --method POST --json '{"question":"hi"}' -n 20 -c 4
```

## Measured baseline (verified)
`GET /health`, 500 requests, concurrency 50, on the local `gp-backend` dev
server (Flask built-in, single process):

| Metric | Value |
|--------|-------|
| Total requests | 500 |
| Successful | 500 |
| Failed | 0 |
| Requests / sec | **507.6** |
| Latency avg | 91.7 ms |
| Latency median | 96.1 ms |
| Latency p95 | **110.7 ms** |
| Latency p99 | 112.4 ms |

> These come from the Flask **development** server (single-threaded WSGI). With
> `gunicorn -w 4` throughput scales roughly with worker count. ML endpoints
> (`/api/ml/predict/stress`, `/ai/medical-slm`) are intentionally **not** part
> of the baseline because they are CPU-heavy and should be load-tested
> separately with low concurrency and realistic think-time.

## Interpreting / next steps
- p95 < ~150 ms on `/health` confirms the serving path and envelope are cheap.
- For production numbers: run behind `gunicorn`, add more workers, and test the
  stress endpoint with pre-warmed model and concurrency ≤ worker count.
