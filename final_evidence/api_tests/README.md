# API Tests Evidence

Drop here:
- `pytest-output.txt` — full output of `pytest backend/tests -v` (44 tests passing).
- `curl-health.txt` — `curl -i http://127.0.0.1:5000/health`
- `curl-telemetry-normal.txt` — normal payload + response showing risk_level=normal.
- `curl-telemetry-high.txt` — high-risk payload + alert created.
- `curl-invalid.txt` — out-of-range payload + 400 INVALID_INPUT response.
- `curl-chat.txt` — `/api/chat` reply with safety disclaimer + emergency prefix.

Helper:
```bash
pytest backend/tests -v | tee final_evidence/api_tests/pytest-output.txt
```
