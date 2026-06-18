# PulseGuard AI - Load Testing

Two equivalent scripts are provided:
- `k6_backend_test.js` — preferred, very fast Go-based runner
- `locustfile.py` — pure-Python alternative if k6 isn't available

Both target the same hot endpoints with a realistic read/write mix.

## Run with k6

```bash
# install: https://k6.io/docs/getting-started/installation/
k6 run load_tests/k6_backend_test.js                 # 25 VUs, 60s steady
k6 run -e USERS=10 -e DURATION=30s load_tests/k6_backend_test.js
k6 run -e USERS=50 -e DURATION=2m  load_tests/k6_backend_test.js
```

## Run with Locust

```bash
pip install locust
locust -f load_tests/locustfile.py --host http://127.0.0.1:5000 \
    -u 25 -r 5 -t 1m --headless --print-stats
```

## What to capture for the defense

For each scenario (10 / 25 / 50 users) record:
- requests/sec
- p50, p95 latency per endpoint
- error rate
- chatbot latency

Paste the numbers into `docs/performance.md` and screenshot the summary into
`final_evidence/load_tests/`.
