# Security

## Authentication

- **Web + Mobile**: Firebase Authentication (Email/Password).
  - Web → `firebase/auth` (`signInWithEmailAndPassword`, `createUserWithEmailAndPassword`, `sendPasswordResetEmail`, `onAuthStateChanged`).
  - Mobile → `firebase/auth` with AsyncStorage-backed React Native persistence (`initializeAuth` + `getReactNativePersistence`).
- The Firebase `user.uid` is the namespace under `users/{uid}` in Realtime Database.
- **Demo mode** lets the apps run with **zero credentials**: a deterministic
  `demo-user-001` identity is cached locally and used for both the UI and the
  RTDB paths.
- **Supabase is NOT used.** Any previously committed Supabase keys have been
  removed; the migrations folder under `supabase/` was deleted.

## Authorization

- Realtime Database is gated by [firebase.rules.json](../firebase.rules.json):
  - `users/{uid}` is readable/writable only by the matching authenticated user.
  - Every write is schema-validated (heart_rate / spo2 / temperature_c bounds,
    risk_level enum, message length, etc.).
- The Flask backend uses the Firebase **Admin SDK** to write telemetry, which
  intentionally bypasses these rules — server-side ingest from the wearable
  is always allowed by design.
- Cloud Firestore is **NOT used** — no `firestore.rules` needed.
- Cloud Storage is **NOT used** — no `storage.rules` needed.

## Secrets management

- `.env` and `backend/.env` are **gitignored** and never checked in. A
  starter `.env.example` is provided in each location.
- The Firebase Web SDK config values (`apiKey`, `authDomain`, `databaseURL`,
  `projectId`, `storageBucket`, `messagingSenderId`, `appId`,
  `measurementId`) are **public client config** — safe to ship in the JS
  bundle. Database security is enforced by Firebase Auth + Realtime Database
  rules, not by hiding the API key.
- The Firebase **Admin SDK** service-account JSON IS a secret. Place it at
  `backend/serviceAccountKey.json` (gitignored) or mount it into the Docker
  container at `/secrets/serviceAccountKey.json`.
- A historical `.env` containing Supabase publishable keys was untracked
  from the repo. Those keys are no longer needed since Supabase is removed.

## Input validation

- All telemetry is validated server-side in
  [backend/anomaly_detection.py](../backend/anomaly_detection.py) before it
  reaches the Firebase write path. Reject criteria:
  - Missing required fields → 400 `INVALID_INPUT`
  - Out-of-range values (e.g. HR=500, SpO₂=150) → 400 `INVALID_INPUT`
- Chatbot input is trimmed and capped at 2000 characters.
- The frontend never trusts a Firebase value blindly — risk badges are
  rendered with the rule-engine-attached `risk_level` field which is
  recomputed server-side on every ingest.

## CORS

- `CORS_ORIGINS` env (comma-separated) controls the allowlist. The Docker
  default restricts to `http://localhost:8080,http://127.0.0.1:8080`.
- In dev, the Vite proxy means the browser never hits the backend
  cross-origin at all — same-origin requests under `/api/*`.

## Rate limiting

`flask-limiter` is wired up in [backend/app.py](../backend/app.py) with
per-IP default and per-route overrides:

| Scope | Default cap | Env override |
|---|---|---|
| Every route | 120 / minute, 2000 / hour | `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_HOURLY` |
| `/api/telemetry` | 60 / minute | `RATE_LIMIT_TELEMETRY` |
| `/api/simulate` | 30 / minute | `RATE_LIMIT_SIMULATE` |
| `/api/chat`, `/chat` | 30 / minute | `RATE_LIMIT_CHAT` |

When the cap is exceeded the response is a standard 429 envelope:

```json
{ "ok": false, "error": { "code": "RATE_LIMIT_EXCEEDED", "message": "..." } }
```

Storage defaults to in-process memory (`memory://`) so the demo has no
external dependency; set `RATE_LIMIT_STORAGE_URI=redis://...` in
production to share state across gunicorn workers. The pytest suite
disables the limiter (`RATE_LIMIT_ENABLED=0` in `conftest.py`) so the
broader test bank does not produce flaky 429s; a dedicated suite in
[backend/tests/test_rate_limit.py](../backend/tests/test_rate_limit.py)
re-enables it with a tight cap and proves the limit actually trips.

## Medical safety

- The chatbot system prompt forbids diagnosis claims.
- Every chatbot response has the "not a doctor" disclaimer appended.
- High-risk readings prepend an emergency-help line.
- The dashboard and mobile app both render a permanent disclaimer.
- Repeated-word generations are collapsed (some TinyLlama runs degenerate
  into "help help help ...").

## Known security limitations

- The in-memory rate-limit storage is per-process, so a multi-worker
  gunicorn deployment will hand out separate counters per worker.
  Acceptable for the demo; in prod, set
  `RATE_LIMIT_STORAGE_URI=redis://...` to share state.
- The in-memory Firebase fallback is not shared between processes, so a
  multi-worker gunicorn deployment will see different data per worker. This
  is documented and is acceptable for the graduation demo (real Firebase
  removes the issue).
- TinyLlama responses are not formally audited for medical safety beyond the
  guardrails described above. For real-world clinical use a model card,
  red-teaming, and clinician sign-off would be required.
- The demo mode cache lives in browser `localStorage` / mobile `AsyncStorage`
  in plain text. That's fine for a demo user but a real "guest mode" should
  also exclude reads/writes to per-uid Firebase paths.
