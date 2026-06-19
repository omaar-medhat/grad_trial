# Final Evidence

This folder is the **proof drawer** for the defense panel. Each subfolder
hosts artefacts that demonstrate one of the maturity-checklist line items
(see [docs/maturity_checklist_mapping.md](../docs/maturity_checklist_mapping.md)).

## Production-readiness write-ups (answer the advisor checklist)

| Document | Covers |
|----------|--------|
| [architecture.md](architecture.md) | Chosen architecture, components, failure handling |
| [setup_and_run.md](setup_and_run.md) | Python 3.11 setup, install, check scripts, run commands |
| [api_endpoints.md](api_endpoints.md) | `/health`, WESAD stress, `/ai/medical-slm`, error structure |
| [testing.md](testing.md) | Test types, commands, scenarios, latest passing summary |
| [load_testing.md](load_testing.md) | Load-test plan + measured baseline (`load_test_backend.py`) |
| [observability.md](observability.md) | Logs, request ids, health, proposed metrics |
| [security.md](security.md) | Input validation, no trace leakage, secrets, auth, abuse handling |
| [ai_components.md](ai_components.md) | WESAD DeepDNN + Medical SLM: type, IO, metrics, limits, fallback |
| [demo_script.md](demo_script.md) | Step-by-step defense demo (incl. failure case) |

## Artefact subfolders (screenshots / exports)

Drop in screenshots, exported log lines, and short clips before the defense.
Each subfolder has its own `README.md` telling you exactly what should live
there and what naming convention to use.

```
final_evidence/
├── firebase/          # screenshots of /users/<uid>/latest_telemetry, history, alerts
├── dashboard/         # screenshots of the web dashboard + risk badge updating
├── mobile/            # screenshots of Expo app on Android/iOS/web
├── api_tests/         # pytest output + curl transcripts
├── load_tests/        # k6 summary + Locust HTML + screenshots
├── logs/              # backend log slices showing request IDs + alerts
├── docs/              # PDF / printout of the docs/ tree
└── team/              # contribution_summary.md + git shortlog screenshot
```

Tip: prefer **PNG + a one-line caption file** per artefact, e.g.
`firebase-latest-telemetry-2026-05-26.png` next to `firebase-latest-telemetry-2026-05-26.txt`
with one sentence of context. Future-you will thank you.
