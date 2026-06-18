# Testing

## Backend (pytest)

```bash
pip install -r backend/requirements-dev.txt
pytest backend/tests -v
```

**110 tests across 7 modules.** All pass with no Firebase or AI dependencies —
the suite exercises the in-memory fallback and rule-based chatbot path. The
trained scikit-learn models (`risk_classifier`, `anomaly_autoencoder`,
`intent_classifier`) are loaded from `backend/models/` and their predictions
are asserted in `test_ml.py`.

The table below is an excerpt; for the full list run
`pytest backend/tests -v`.

### Test catalog

| ID | Module | Scenario | Type | Expected | Status |
|---|---|---|---|---|---|
| T-AD-01 | anomaly | Valid payload accepted | unit | clean dict returned | ✅ |
| T-AD-02 | anomaly | Missing `spo2` rejected | unit | TelemetryValidationError | ✅ |
| T-AD-03 | anomaly | HR=500 rejected | unit | TelemetryValidationError | ✅ |
| T-AD-04 | anomaly | Normal vitals → "normal" | unit | risk_level==normal | ✅ |
| T-AD-05 | anomaly | HR 50 → warning | unit | low_heart_rate rule | ✅ |
| T-AD-06 | anomaly | HR 35 → high | unit | critical_bradycardia | ✅ |
| T-AD-07 | anomaly | HR 160 → high | unit | critical_tachycardia | ✅ |
| T-AD-08 | anomaly | SpO₂ 94 → warning, 88 → high | unit | both rules fire | ✅ |
| T-AD-09 | anomaly | Temp 39.2 → high | unit | high_fever | ✅ |
| T-AD-10 | anomaly | HR 125 + Temp 37.9 → overheating | unit | combined rule | ✅ |
| T-AD-11 | anomaly | HR 120 + SpO₂ 93 → O₂ deficit | unit | combined rule | ✅ |
| T-AD-12 | anomaly | HR 115 + steps 10 → stress pattern | unit | combined rule | ✅ |
| T-AD-13 | anomaly | Temp 35.2 → hypothermia | unit | warning | ✅ |
| T-AD-14 | anomaly | Missing `steps` defaults to 0 | unit | passes validation | ✅ |
| T-EP-01 | endpoints | GET /health 200 | integration | OK envelope | ✅ |
| T-EP-02 | endpoints | GET /api/metrics 200 | integration | counters present | ✅ |
| T-EP-03 | endpoints | POST /api/telemetry valid | integration | risk_level normal | ✅ |
| T-EP-04 | endpoints | POST /api/telemetry HR=500 | integration | 400 INVALID_INPUT | ✅ |
| T-EP-05 | endpoints | POST /api/telemetry missing field | integration | 400 INVALID_INPUT | ✅ |
| T-EP-06 | endpoints | High-risk payload creates alert | integration | /api/alerts returns it | ✅ |
| T-EP-07 | endpoints | History accumulates | integration | length ≥ 3 | ✅ |
| T-EP-08 | endpoints | /api/simulate works | integration | telemetry + analysis | ✅ |
| T-EP-09 | endpoints | Unknown route returns envelope | integration | 404 NOT_FOUND | ✅ |
| T-EP-10 | endpoints | X-Request-ID header present | integration | header echoed | ✅ |
| T-CB-01 | chatbot | Safe reply with no telemetry | integration | disclaimer present | ✅ |
| T-CB-02 | chatbot | Uses latest telemetry | integration | mentions reading | ✅ |
| T-CB-03 | chatbot | High-risk → emergency prefix | integration | "seek/help" in reply | ✅ |
| T-CB-04 | chatbot | Empty message validation | integration | guidance returned | ✅ |
| T-CB-05 | chatbot | Repeated text collapsed | unit | ≤ 2 repeats | ✅ |
| T-CB-06 | chatbot | Disclaimer always appended | unit | "not a doctor" present | ✅ |
| T-CB-07 | chatbot | High-risk gets emergency line | unit | prefix or "seek" present | ✅ |
| T-CB-08 | chatbot | Legacy /chat alias works | integration | 200 OK | ✅ |
| T-FB-01 | firebase | No creds → memory mode | unit | mode == "memory" | ✅ |
| T-FB-02 | firebase | Round-trip latest | unit | identical dict | ✅ |
| T-FB-03 | firebase | History push/read | unit | length matches | ✅ |
| T-FB-04 | firebase | Alerts push/read | unit | alert returned | ✅ |
| T-FB-05 | firebase | Per-user isolation | unit | data separated | ✅ |
| T-ML-01..13 | ml | Risk / anomaly / intent classifier predictions, model metadata, /api/models, telemetry envelope contains `ml.*` block | unit + integration | predictions in valid range, latency reported | ✅ |
| T-AS-01..20 | assistant | NLU intent classification, emergency override, memory store, knowledge-base composer, LLM fallback path | unit | every intent branch covered | ✅ |
| T-RL-01 | rate-limit | `/api/chat` returns 429 after the per-IP cap | integration | first N pass, next is 429 | ✅ |
| T-RL-02 | rate-limit | 429 uses the standard error envelope | integration | `RATE_LIMIT_EXCEEDED` code | ✅ |

## Frontend (vitest + React Testing Library)

```bash
npm test                    # one-shot, 54 tests
npm run test:watch          # watcher
```

**54 tests across 8 files** exercise the pure helpers and the user-facing
components:

| Suite | What it covers |
|---|---|
| `src/lib/health-data.test.ts` | `classifyHeartRate`, `classifySpO2`, `classifyTemperature`, `fahrenheitToCelsius`, `secondsToTime`, `aiClassify`, `generateHistoricalDataset` |
| `src/components/StatusBadge.test.tsx` | Renders the correct label for every `HealthStatus` |
| `src/components/MetricCard.test.tsx` | Renders label/value/unit/hint/progress, caps progress at 100% |
| `src/components/RiskHeroCard.test.tsx` | Default/warning/high copy, custom alert message, `role=status` for assistive tech |
| `src/components/AlertSummary.test.tsx` | All-clear state, critical/watch counts, deep link to `/alerts` |
| `src/components/TelemetrySourceBadge.test.tsx` | Live / Connected / Demo / Reconnecting labels, "Ns ago" hint |
| `src/components/HealthInsights.test.tsx` | Friendly plain-language messages for every classification branch |

Vite build + ESLint are also enforced on every PR by the GitHub Actions
workflow at [.github/workflows/ci.yml](../.github/workflows/ci.yml).

## Mobile

The Expo app is type-checked with `npm run tsc` inside `mobile/`. A full
Jest suite is a follow-up; manual test plan:

| Step | Expected |
|---|---|
| Launch app | Splash → auth screen |
| Tap "Continue as demo" | Routes to Dashboard tab |
| Wait 5s | Dashboard shows "Demo · updated Ns ago" |
| Tap "Send synthetic reading" | Risk badge + metrics update within ~3s |
| Tab → Alerts | Empty state OR list populated (depending on the simulated risk) |
| Tab → Assistant | Welcome message; typing returns a reply (or graceful error) |
| Tab → Profile | Shows demo email + connection status; Sign out → auth screen |

## End-to-end smoke (one command)

```bash
docker compose --profile demo up --build
# open http://localhost:8080  — dashboard updates as the simulator pumps data
```

## Continuous integration

Every push and PR runs three jobs in
[.github/workflows/ci.yml](../.github/workflows/ci.yml):

1. **backend** — `pytest backend/tests -v` on Python 3.12 (Ubuntu).
2. **frontend** — `npm ci && npm run lint && npm test && npm run build`.
3. **mobile** — `npx tsc --noEmit` against the Expo project.

A red CI badge on a PR blocks merging.
