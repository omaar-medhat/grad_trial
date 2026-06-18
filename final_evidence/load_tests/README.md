# Load Tests Evidence

Drop here:
- `k6-10-users.txt` — k6 summary stdout for 10 VUs, 30s.
- `k6-25-users.txt` — same, 25 VUs, 60s.
- `k6-50-users.txt` — same, 50 VUs, 2m.
- `k6-with-ai.txt` — 25 VUs, 60s, `LOAD_CHATBOT_MODEL=1` on the backend.
- `locust-summary.png` — Locust web UI summary page.

Helper:
```bash
k6 run -e USERS=10 -e DURATION=30s load_tests/k6_backend_test.js \
  | tee final_evidence/load_tests/k6-10-users.txt
```

Then copy the headline numbers into [docs/performance.md](../../docs/performance.md).
