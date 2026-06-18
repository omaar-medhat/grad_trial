# Firebase

PulseGuard AI uses **two** Firebase services and **nothing else**:

- **Firebase Authentication** — Email/Password for the web and mobile apps.
- **Firebase Realtime Database** — single source of truth for live telemetry,
  history, alerts, and per-user profile.

The following are **NOT** used:
- Cloud Firestore
- Cloud Storage
- Cloud Functions
- Hosting / App Check / Analytics features in code

## Data model

Standard paths (every part of the codebase imports them through helpers, so a
rename happens in one place):

```
users/
  {uid}/
    latest_telemetry        # one node; overwritten on every ingest
      ├── heart_rate
      ├── spo2
      ├── temperature_c      # Celsius — never temperature_f
      ├── steps
      ├── calories
      ├── sleep_duration_sec
      ├── battery_level      # bracelet charge %, 0–100 (optional)
      ├── activity_level     # 0–100 motion index (optional)
      ├── wellness_score     # 0–100 wellness indicator (not a diagnosis)
      ├── activity           # "resting" | "active" | "walking" | "running"
      ├── stress_label       # "relaxed" | "normal" | "stressed"
      ├── stress_score       # 0–100
      ├── source             # "simulator" | "real_bracelet" | "uploaded_dataset"
      ├── risk_level         # "normal" | "warning" | "high"
      ├── alert_message
      └── timestamp          # ms epoch
    history/
      {push_id}/              # appended on every ingest
        (same shape as latest_telemetry)
    alerts/
      {push_id}/              # only when risk_level != "normal"
        ├── risk_level        # "warning" | "high"
        ├── message
        ├── reasons           # array of human strings
        ├── source            # "rule_engine" | "simulator" | ...
        └── timestamp
    profile/                  # written by the Profile page in web + mobile
      ├── display_name
      ├── gender
      ├── blood_type
      ├── date_of_birth
      ├── height_cm
      ├── weight_kg
      ├── emergency_contact
      └── updated_at
```

**Naming**: the canonical key is `latest_telemetry` (no typos like
`latest_telemerty`). A repo-wide grep before opening any PR is a good habit.

**Units**: the schema is Celsius-only via `temperature_c`. The legacy
frontend in `src/lib/health-data.ts` still works internally in Fahrenheit
because the in-browser simulator was authored that way, but it always
converts to Celsius at the display + Firebase write boundary.

## Frontend helpers

- Web: [src/integrations/firebase/client.ts](../src/integrations/firebase/client.ts)
  exposes:
  - `getFirebaseAuth()` — lazy Auth instance (returns `null` when env is missing)
  - `getFirebaseDb()` — lazy Realtime DB instance (returns `null` when env is missing)
  - `fbPath.{latest,history,alerts,profile}(uid)` — single source of truth for paths
- Mobile: [mobile/src/lib/firebase.ts](../mobile/src/lib/firebase.ts) is the
  symmetrical helper, using `initializeAuth` + `getReactNativePersistence(AsyncStorage)`.
- Both consume the same `useLiveTelemetry` hook pattern.

## Backend helpers

- [backend/firebase_service.py](../backend/firebase_service.py) wraps the
  Admin SDK with a thread-safe in-memory fallback. Every method has the
  same return shape regardless of mode, so the rest of the backend is
  unaware which is active.
- The Admin SDK uses a service-account JSON (`backend/serviceAccountKey.json`,
  gitignored). Download it from the Firebase Console under
  **Project Settings → Service accounts → Generate new private key**.

## Authentication

- The web app uses Firebase JS SDK `signInWithEmailAndPassword`,
  `createUserWithEmailAndPassword`, and `sendPasswordResetEmail`.
- The mobile app uses the same, with AsyncStorage-backed persistence.
- Both apps have a **demo mode** fallback: if env vars are missing OR the
  user taps "Continue as demo", a deterministic `demo-user-001` identity is
  cached locally. This lets the demo run with zero credentials.

## Fallback

When Firebase credentials are not present:
- Backend logs a single warning and uses the in-memory store. Writes still
  succeed; reads still return data; alerts still fire. Data is per-process
  and resets on restart.
- Frontend logs a single info line in DevTools and switches to polling the
  backend's `/api/latest`, `/api/history`, `/api/alerts`. The UI looks
  identical.
- If both Firebase and the backend are unreachable, the dashboard falls
  back to the in-browser simulator (see `useLiveTelemetry`).

This three-tier design means the demo always works.

## Security rules

See [firebase.rules.json](../firebase.rules.json). They restrict read/write
to the owning UID and validate every payload against the schema above.
Because we use **Firebase Authentication**, `auth.uid === $uid` is enforced
at the database layer — no server-side custom-token bridging required.

### Deploying the rules

```bash
# from project root
firebase login
firebase use lab10prototyping
firebase deploy --only database
```

(Make sure `firebase.json` points to `firebase.rules.json` — example below.)

```jsonc
// firebase.json
{
  "database": {
    "rules": "firebase.rules.json"
  }
}
```

## Seeding sample data

```bash
# Backend running on :5000
python -m backend.simulator --uid demo-user-001 --interval 1 --count 60
```

This writes 60 readings (with occasional anomalies) into Firebase or the
in-memory store. The dashboard updates live.

## A note on `storageBucket`

The Firebase Web SDK config includes a `storageBucket` value — that's a
property of the project, not an opt-in to Cloud Storage. We never call
`getStorage()` and we ship no upload features. You can keep `storageBucket`
in `.env` without enabling Cloud Storage in your Firebase project.
