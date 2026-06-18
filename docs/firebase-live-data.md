# Firebase live sensor data — single source of truth

This document describes how PulseGuard AI consumes **live bracelet telemetry
from Firebase** as the primary source for the whole app (dashboard, analytics,
alerts, reports, chatbot, backend APIs, model/rule insights).

Architecture:

```
bracelet → Firebase RTDB /users/{uid}/... → backend Firebase reader
        → canonical telemetry contract → backend alert engine
        → current + historical alerts → backend APIs
        → dashboard / analytics / alerts / reports / chatbot
        → proactive assistant alert cards
```

There is exactly **one** normalization path (`backend/telemetry_contract.py`),
one source resolver (`backend/data_source.py`), and one alert engine
(`backend/alerts.py`). The frontend never invents displayed vitals from an
in-browser simulator, and the chatbot never invents values, alerts, diagnoses,
or medication advice — it is grounded in backend telemetry + backend alerts.

## A. Firebase schema (USER-SCOPED)

The bracelet now publishes per user (NOT root):

```
/users/{uid}/latest_telemetry     # current raw reading (source of truth)
/users/{uid}/history/{push_id}    # timestamped raw readings
/users/{uid}/profile              # name/age/gender/activity/... (NOT telemetry)
/users/{uid}/goals                # steps/calories/sleep targets (NOT telemetry)
```

Example active user: `/users/eKjIbPbsi5SqLX5HP8a6CtabtPm2/latest_telemetry`.
The old root paths `/latest_telemetry` and `/history` are NO LONGER used unless
`ENABLE_LEGACY_ROOT_PATHS=1` is explicitly set.

`latest_telemetry` fields:

| field                | type        | notes                                |
|----------------------|-------------|--------------------------------------|
| `heart_rate`         | number      | bpm                                  |
| `spo2`               | number      | %                                    |
| `temperature_c`      | number      | **preferred** when valid (30–45)     |
| `temperature_f`      | number      | converted to °C only if °C missing   |
| `systolic`/`diastolic` | number    | mmHg                                 |
| `bp_estimated`       | boolean     | whether BP is estimated              |
| `battery_level`      | number      | %                                    |
| `steps`/`calories`   | number      |                                      |
| `sleep_duration`     | number      | seconds (new); `sleep_duration_sec` legacy |
| `fall_alert`         | boolean     |                                      |
| `risk`               | **string**  | e.g. "Low" (legacy: numeric `risk_level`) |
| `stress`             | **string**  | e.g. "Normal" (legacy: numeric `stress_label`) |
| `timestamp`          | number      | ms epoch                             |

### Active user resolution
Priority: query `?uid` → `FIREBASE_ACTIVE_UID` env → signed-in user →
first `/users` child with `latest_telemetry` → unavailable. The uid is never
hardcoded in code (env/query only). Reads require authorization: with locked
rules, set `FIREBASE_CREDENTIALS_PATH` (Admin SDK) or `FIREBASE_DB_SECRET`.

### Reading a LOCKED database (production) — Firebase Admin SDK

Production rules deny anonymous reads. The backend reads with the **Firebase
Admin SDK**, which runs server-side and **bypasses database rules** — so the
rules can (and should) stay locked.

1. Firebase console → Project settings → **Service accounts** → **Generate new
   private key** → download the JSON.
2. Put it somewhere local (e.g. `backend/serviceAccountKey.json`) and set:
   ```
   DATA_SOURCE=firebase
   FIREBASE_CREDENTIALS_PATH=backend/serviceAccountKey.json
   FIREBASE_DATABASE_URL=https://<your-project>-default-rtdb.firebaseio.com
   # MUST be the user whose bracelet is CURRENTLY streaming (live "connected").
   FIREBASE_ACTIVE_UID=your-streaming-bracelet-user-id
   ```
   Tip: uids are case-sensitive and contain look-alike characters (capital
   `I` vs lowercase `l`). Copy it exactly from the Firebase console; a wrong
   uid reads an empty/idle node and the dashboard shows disconnected.

   If the host clock is skewed (sandbox / RTC-less gateway), Google may reject
   the OAuth JWT (`invalid_grant: Invalid JWT`). Set `FIREBASE_FIX_CLOCK_SKEW=1`
   to auto-correct it (no-op on a correctly-synced host).
3. Restart the backend. `/api/health` then reports
   `firebase_mode: "admin_sdk"`, `firebase_read_ok: true`.

The service-account JSON is a **secret**: it is git-ignored
(`*serviceAccount*.json`, `firebase-adminsdk*.json`, `backend/.env`, …) and
must never be committed. `pip install -r backend/requirements.txt` includes
`firebase-admin`.

**Modes** (`/api/health.firebase_mode`):
* `admin_sdk` — service account configured; reads locked DB server-side.
* `rest` — fallback/debug only; anonymous HTTPS reads; fails with a clear 401
  (`firebase_read_ok: false`, `firebase_error: …`) when rules deny anonymous
  read.
* `memory` — offline demo / CI. `admin_error` — credentials invalid.

The backend NEVER falls back to anonymous REST when credentials are set, and
NEVER silently uses the simulator in `DATA_SOURCE=firebase`.

## B. Canonical telemetry contract

`normalize_reading()` outputs (see `/api/vitals/latest`):

```jsonc
{
  "available": true,
  "heart_rate": 72, "spo2": 98, "temperature_c": 37.0,
  "steps": 12, "calories": 0.48, "sleep_duration_sec": 28,
  "battery_level": 82, "systolic": 120, "diastolic": 80,
  "fall_alert": false,
  "risk_level": "moderate",  "raw_risk_level": 1,
  "stress_label": "normal",  "raw_stress_label": 1,
  "source": "firebase", "is_simulated": false,
  "timestamp": 1781648601397, "date_time": "2026-06-17 01:23:21",
  "device_status": "connected", "last_seen_seconds": 3.2,
  // model-derived (attached by the API layer):
  "derived_risk_level": "normal", "wellness_score": 100,
  "anomaly_status": "normal", "activity": "unknown"
}
```

Validation: `heart_rate` 20–250, `spo2` 50–100, `temperature` plausible body
range, `battery` 0–100, `steps` ≥ 0, `systolic` 70–260, `diastolic` 40–150.
Out-of-range values become `null` (never charted, never invented).

`temperature_f` → `temperature_c`: `98.6°F → 37.0°C`. A value already in the
Celsius body range (25–45) is accepted as-is; anything impossible → `null`.

## C. Source priority (`DATA_SOURCE`)

1. `firebase` (default): Firebase `/latest_telemetry` if usable → else last
   usable `/history` record → else **unavailable/disconnected** (never the
   simulator).
2. `simulator`: in-process simulator only (explicit demo/testing).
3. `auto`: prefer Firebase, else simulator (clearly labelled
   `source: "simulator"`, `is_simulated: true`).

The simulator is never a silent fallback in `firebase` mode.

## D. Device connection / staleness (robust to a wrong device clock)

Freshness uses the **fresher of two signals** (`resolve_device_status`),
reported as `used_freshness_basis`:

1. `sensor_timestamp` — `now − timestamp`, but only when the timestamp is a
   plausible ms epoch and not implausibly in the future
   (`SENSOR_TS_FUTURE_SKEW_SEC`).
2. `observed_change` — server time of the last moment the `/latest_telemetry`
   **payload changed** (the backend hashes each read). Immune to device clock
   skew.

| status         | age (fresher signal) | env                        |
|----------------|----------------------|----------------------------|
| `connected`    | ≤ 15 s               | `DEVICE_CONNECTED_MAX_SEC` |
| `stale`        | 15–60 s              | `DEVICE_STALE_MAX_SEC`     |
| `disconnected` | > 60 s or missing    |                            |

**Why two signals:** some firmware writes a `timestamp` whose epoch is not
aligned with real time (wrong RTC / timezone). A device actively pushing every
few seconds would then look "disconnected". The observed-change signal fixes
this: a live, changing feed reads as **connected** even with a bad timestamp,
while a feed that stops changing correctly ages into stale → disconnected. The
observed signal only activates after a *real* change is witnessed, so a stale
reading left over while the sensor was off does not look connected on startup.

`/api/device/status` exposes `used_freshness_basis`,
`server_observed_last_seen_at`, and `latest_heart_rate`. The last valid reading
stays visible and is clearly marked; no fake vitals are generated when the
sensor stops. Best long-term fix: have the firmware write `timestamp` as
synced epoch-ms (or a Firebase `ServerValue.TIMESTAMP`).

### Reads must be authorized

The backend reads the root over the RTDB REST API. If the database rules stop
allowing anonymous reads — e.g. **Firebase "test mode" rules expire after ~30
days and flip to deny-all** — reads return `401/403`, the API reports
`available:false` / `disconnected`, and the backend logs a clear message. Fix
by ONE of:
* deploy the `/latest_telemetry` + `/history` read rules in
  `firebase.rules.json`, or
* set `FIREBASE_DB_SECRET` (RTDB secret / privileged token), or
* provide a service account via `FIREBASE_CREDENTIALS_PATH` (Admin SDK).

All API responses send `Cache-Control: no-store`, and the hook fetches with
`cache: "no-store"` + a cache-buster, so a frozen reading is never served from
a cache.

## E. Numeric label mappings (documented + configurable)

The firmware's `risk_level` / `stress_label` semantics are not documented, so
the **raw integer is always preserved** (`raw_risk_level`, `raw_stress_label`)
and the mapping is overridable via env:

```
DATA_RISK_MAP=0:low,1:moderate,2:high
DATA_STRESS_MAP=0:no_stress,1:normal,2:high
```

For clinical decisions (alerts, dashboard risk hero) the backend prefers its
own transparent rule engine (`derived_risk_level`, normal/warning/high)
computed from the actual vitals — not the device's ambiguous numeric label.

## F. Backend APIs (all user-scoped, Firebase-backed)

`GET /api/vitals/latest?uid=`, `GET /api/vitals/history?uid=`,
`GET /api/vitals/window?seconds=60&uid=`, `GET /api/device/status?uid=`,
`GET /api/alerts/current?uid=`, `GET /api/alerts?uid=` (current vs history),
`GET /api/reports/daily?uid=`, `GET /api/profile?uid=`, `GET /api/goals?uid=`,
`POST /api/chat`. Each carries `uid`, `source`, `is_simulated`,
`device_status`, `timestamp`, and `last_seen_seconds` where relevant. All
responses send `Cache-Control: no-store`.

## H. Alert engine (backend/alerts.py)

Deterministic, multi-signal, auditable — never an LLM, never the device's
opaque risk label. Severity scale: `normal < watch < warning < critical`.
Signals: heart rate (context-aware — elevated HR during activity is less
severe than at rest), SpO₂, temperature, blood pressure, fall, battery, device
status, and a recent-window rapid-HR-rise trend. Every alert carries `id`,
`severity`, `title`, `message`, `metric`, `value`, `threshold`,
`safe_guidance`, `emergency_guidance` (critical only), and
`requires_medical_attention`. Current alerts (latest + window + device) are
kept separate from historical alerts. Guidance is conservative: it never
diagnoses a disease, predicts an event, or prescribes medication.

## I. Chatbot grounding + safety

PulseGuard AI is a data-grounded wellness assistant, not a doctor or a generic
chatbot. It answers from backend telemetry + backend current alerts for the
SAME active uid. It explains alerts safely ("Based on your current bracelet
alert… This is wellness guidance, not a medical diagnosis."), refuses diagnosis
(`medical_boundary` intent) and medication advice, discloses stale/disconnected
state, never invents missing values, says "Firebase live sensor data" when
connected, and never says simulator/demo when the source is Firebase. The LLM
tier (opt-in) only handles open general-health questions; all data/alert/safety
intents use the grounded rule-based assistant so the model cannot invent
danger, values, diagnoses, or meds.

## J. Proactive alert cards (frontend)

`ProactiveAlertCard` surfaces a single message when a NEW backend current alert
appears ("I noticed a current alert from your bracelet: …"). It is de-duplicated
by condition (`type`+`severity`), not by the per-reading id (which changes every
poll), so it never spams; a condition can re-alert only after it clears and
returns. Dismiss suppresses it while still active.

## G. ML / WESAD behaviour

The WESAD stress model needs many raw multi-channel features that the Firebase
schema does **not** provide. Therefore:

* `POST /api/ml/predict/stress` stays available **only** for compatible input
  (the full WESAD feature vector); it returns `400/503` for incompatible
  input — missing features are never faked.
* Live stress shown in the app comes from the Firebase `stress_label`
  (mapped + raw kept) and/or the backend's deterministic rule heuristic, not a
  pretend WESAD inference.
