# Live Demo Report

A record of the end-to-end live verification of PulseGuard AI (backend +
web dashboard + chatbot + analytics + alerts + reports) and the honest
limitations that remain. The mobile app is aligned by contract but was not
run visually in this environment.

## What was verified live

- **Backend** `http://localhost:5000` — `/`, `/api/health`, `/api/models/status`,
  `/api/vitals/latest` all return valid responses; all ML models load.
- **Dashboard** `http://localhost:8080` — live vitals cards, wellness score,
  risk + anomaly cards, activity/stress chips, battery, history chart, alerts.
- **Single source of truth** — dashboard, `/api/vitals/latest`, and the chatbot
  all show identical values (HR, SpO₂, temperature, battery, steps, activity,
  wellness, risk, stress, anomaly, source, is_simulated).
- **Heart-rate chart** — plots real **BPM** on the Y-axis (≈60–120) with a
  `… bpm` tooltip; malformed values are normalized/filtered, never plotted.
- **Chatbot** — current-value questions answer from the live snapshot; stress/
  risk/anomaly from latest predictions; reports from history; typos handled
  (`write now`, `hart rate`, `temprature`, `oxegen`, `spo two`); medical-safety
  prompts handled (no diagnosis, emergency guidance, no medication advice);
  simulator/demo source disclosed.
- **Analytics** — charts + daily/weekly report + CSV/PDF export, consistent with
  history; values labeled as simulated.
- **Alerts** — counts/severity reflect current state; recent alerts labeled as
  history, not current state.
- **Console / backend logs** — no frontend runtime errors, no backend
  exceptions, no failed/CORS/proxy calls during the demo.

## Data source map (current state)

| Field | Source |
|---|---|
| heart_rate, spo2, steps, calories, sleep, battery_level | sensor/simulator → backend store → `/api/vitals/latest` |
| temperature_c | normalized from `temperature_c` or legacy `temperature_f` (F→C, ÷10, else null) |
| wellness_score, activity, risk_level | backend derived rules (+ trained risk classifier) |
| stress_label / stress_score | deterministic heuristic live; WESAD model via `/api/ml/predict/stress` only |
| anomaly_status / anomaly_score | ML autoencoder (`_enrich_with_ml`); null when not computed |
| alerts | backend rule/device alerts (history feed, labeled recent) |
| history chart | backend store history, filtered to valid BPM |

Authoritative source for the demo: the **simulator-fed backend store**; raw
Firebase records are normalized on read.

## Known Limitations / Future Work

### 1. Firebase legacy records
- The real Firebase project still contains older/partial telemetry records
  (e.g. `temperature_f`, missing `spo2`/`battery_level`).
- The app now **normalizes and validates records on read**: `temperature_f` →
  Celsius, accidentally-×10 values rescaled, names mapped to the canonical
  contract.
- **Invalid values are rejected or dropped** before reaching the dashboard,
  chatbot, or ML (e.g. impossible temperature → unavailable; out-of-range
  heart_rate/spo2 → dropped).
- **Future work:** a one-time Firebase migration to the canonical schema, or
  making the **backend the sole writer** so stored records are always clean.

### 2. WESAD live compatibility
- The WESAD stress model **is trained and integrated**
  (`backend/models/wesad_stress_artifact.pkl`, `POST /api/ml/predict/stress`).
- It is **not** used for live stress inference from the current Firebase schema.
- **Reason:** the current Firebase / basic bracelet telemetry does **not**
  contain the required **252 WESAD features** (raw multi-channel wrist + chest
  BVP/EDA/ECG/EMG/ACC window features). Overlap with the 7 available Firebase
  fields is **0**.
- The app **does not fake missing features**.
- **Live stress in the demo uses a deterministic stress heuristic.**
- **Future work:** collect compatible bracelet signals, or train a new stress
  model on the actual bracelet/Firebase fields.

### 3. Mobile status
- The mobile code is **aligned with the shared telemetry contract** (same
  `useLiveTelemetry` hook + snake_case schema; the chat screen sends live
  telemetry to `/api/chat`).
- Mobile was **not visually run** in this environment because no emulator /
  device / runtime setup was available.
- **Future work:** run and validate the Expo app on an emulator/device.

## How to explain this in the defense

- This is a **software-first AI health-monitoring platform** — runs fully
  without hardware, ready for a real bracelet later.
- The current demo uses **simulator-fed backend telemetry as the authoritative
  source**.
- The backend exposes **one normalized contract** via `GET /api/vitals/latest`.
- The **dashboard, chatbot, alerts, analytics, and reports use the same data
  contract** — no invented or stale values.
- **WESAD is integrated** but only runs with compatible feature input; live
  stress uses a transparent deterministic signal.
- The assistant is a **wellness assistant, not a medical diagnostic tool**.
