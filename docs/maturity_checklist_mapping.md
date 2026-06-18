# Maturity Checklist Mapping

Honest scoring against the maturity checklist. **Done** means the repo proves
it. **Partial** means an MVP exists but a clear next step remains. **Missing**
means it's a known gap.

| Requirement | Status | Evidence | Gap / next step | Priority |
|---|---|---|---|---|
| 1. Working mobile application | ✅ Done | [mobile/](../mobile/), [mobile/README.md](../mobile/README.md) | Push notifications and a real chart lib | medium |
| 2. Working web dashboard | ✅ Done | [src/pages/Index.tsx](../src/pages/Index.tsx) | – | – |
| 3. Working backend API | ✅ Done | [backend/app.py](../backend/app.py), [docs/api.md](./api.md) | – | – |
| 4. Working Firebase realtime telemetry | ✅ Done (+ fallback) | [backend/firebase_service.py](../backend/firebase_service.py), [src/integrations/firebase/client.ts](../src/integrations/firebase/client.ts) | Provision a real Firebase Admin service-account for prod | medium |
| 5. Firebase authentication (with demo fallback) | ✅ Done | [src/hooks/useAuth.tsx](../src/hooks/useAuth.tsx), [mobile/src/hooks/useAuth.tsx](../mobile/src/hooks/useAuth.tsx) | Email verification flow | low |
| 6. Working anomaly detection | ✅ Done | [backend/anomaly_detection.py](../backend/anomaly_detection.py), [src/lib/anomaly-detection.ts](../src/lib/anomaly-detection.ts) | Persist trend anomalies in Firebase too | low |
| 7. Working healthcare chatbot with safety guardrails | ✅ Done | [backend/chatbot_service.py](../backend/chatbot_service.py) | Independent clinician review for production | high |
| 8. Working telemetry simulation | ✅ Done | [backend/simulator.py](../backend/simulator.py) | – | – |
| 9. Clean data model | ✅ Done | [docs/firebase.md](./firebase.md), [firebase.rules.json](../firebase.rules.json) | – | – |
| 10. API documentation | ✅ Done | [docs/api.md](./api.md), [docs/openapi.yaml](./openapi.yaml) | – | – |
| 11. README documentation | ✅ Done | [README.md](../README.md) | – | – |
| 12. Docker / one-command setup | ✅ Done | [docker-compose.yml](../docker-compose.yml) | – | – |
| 13. Tests | ✅ 110 backend + 54 frontend | [docs/testing.md](./testing.md) | More mobile coverage (React Native Testing Library) | medium |
| 14. Load/performance test scripts | ✅ Done | [load_tests/k6_backend_test.js](../load_tests/k6_backend_test.js), [load_tests/locustfile.py](../load_tests/locustfile.py) | Record numbers from your hardware into [docs/performance.md](./performance.md) | high |
| 15. Logging / observability | ✅ Done | [docs/observability.md](./observability.md) | Wire Sentry + Prometheus when there's a real prod env | medium |
| 16. Security improvements | ✅ Done | [docs/security.md](./security.md), [backend/app.py](../backend/app.py) | Clinician review of safety guardrails for clinical deployment | medium |
| 17. Demo script | ✅ Done | [docs/demo_script.md](./demo_script.md) | – | – |
| 18. Final defense answers | ✅ Done | [docs/final_defense_answers.md](./final_defense_answers.md) | – | – |
| 19. Evidence folder structure | ✅ Done | [final_evidence/](../final_evidence/) | Fill in screenshots / logs / load test reports | high |
| 20. Clear known limitations | ✅ Done | this file + [docs/security.md](./security.md) | – | – |

## What was removed from the project

For a panel question about scope cleanup, mention these intentional removals:

- **Supabase** — removed entirely (deleted `supabase/`, `src/integrations/supabase/`,
  `@supabase/supabase-js` from `package.json`, plus the Supabase-backed pages
  `MedicalRecords`, `Devices`, `AlertRules`, `ResetPassword`, and the `UserProfileForm`
  component). Auth and per-user data are now 100% Firebase.
- **Cloud Firestore** — never used; explicitly called out in code comments
  and docs so future contributors don't add it by accident.
- **Cloud Storage** — never used; documented similarly. The `storageBucket`
  value in the Firebase config is part of project metadata, not an opt-in.
- The legacy Supabase Edge Function (`supabase/functions/health-chat/`) that
  proxied to OpenAI — superseded by the Flask backend `/api/chat`.

## Honest non-goals (don't claim these are done)

- A **fine-tuned medical LoRA adapter** IS now bundled
  (`backend/models/medical_slm_adapter/`, TinyLlama-1.1B, r=8) and wired into
  `/api/chat` + the UI; enable with `LOAD_CHATBOT_MODEL=1` (4-bit on GPU,
  float32 on CPU ~15-20s/reply). The fast default demo still uses the
  rule-based assistant so it boots instantly and never blocks.
- **Stress detection** serves the **real WESAD model**
  (`backend/models/wesad_stress_artifact.pkl`, best of a 15-model bake-off with
  a leave-subjects-out split, **MLP** acc 0.93 / ROC-AUC 0.95) via
  `POST /api/ml/predict/stress`, returning label/confidence/probabilities/
  model_name. It's a binary `non_stress`/`stress` model over 252 wrist+chest
  features (BVP/EDA/ECG/EMG/ACC, 60 s windows), so it runs on **WESAD-format
  input**, not the bracelet's HR/SpO₂/temp/activity. The dashboard's live stress
  chip uses the deterministic `stress_level` heuristic. Full comparison in
  `backend/models/wesad_stress_comparison.json`. (Cross-version note: the
  artifact's imputer/scaler are re-fitted at load so it predicts under the
  repo's newer scikit-learn without changing the trained weights.)
- **Activity recognition** is trained on the **real UCI HAR** public dataset
  (`backend/ml/training/train_activity_classifier.py`, 5-model comparison, best
  LinearSVM **96.2%** on the official test split). Metrics are exposed read-only
  at `/api/models`; live prediction activates once the bracelet streams raw IMU
  windows (561 features) — until then the dashboard uses the deterministic
  activity label.
- The original `chatbot.py` is kept for backward compatibility and is
  superseded by `backend/app.py`. It's safe to delete once the new backend
  has been running in front of the user-facing app for a sprint.
- No **physical bracelet** has been assembled and flashed for this repo. What
  *is* provided: a documented protocol (POST JSON to `/api/telemetry`), a Python
  simulator that proves it, a **reference firmware** for an ESP32-C3 that reads
  the planned sensors and posts the same schema ([firmware/](../firmware/)), a
  **BLE GATT spec** ([docs/ble_spec.md](./ble_spec.md)), and a **hardware/BOM**
  doc ([docs/hardware.md](./hardware.md)). The firmware is a reference (not
  CI-built or bench-validated against a reference pulse oximeter) — assembling
  and calibrating a board is the remaining hardware step.
