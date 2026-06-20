# PulseGuard AI — Final Project Report (Corrected Architecture)

> This is the authoritative description of the **current** system. It supersedes
> any earlier report that described open Firebase rules, direct client→Firebase
> writes, real secrets in `.env.example`, "last frontend uid" sensor mapping, or
> REST writes without the Admin SDK. Those describe an earlier prototype and are
> **not** the final architecture.

## 1. Security model (authoritative)

- **Firebase Authentication** is used for signup/login (email/password).
- The **mobile app uses the Firebase Auth client only** — to sign in and obtain
  a Firebase **ID token**. It does **not** read or write the Realtime Database
  directly, and it never uses Firebase REST writes.
- The **backend is the only trusted layer**. It verifies Firebase **ID tokens
  with the Firebase Admin SDK** and is the only component that reads/writes
  protected RTDB data under `/users/{uid}`.
- **Firebase Realtime Database rules stay LOCKED.** Clients have no direct read/
  write access; all access is mediated by the backend (Admin SDK).
- **Secrets are never committed.** `serviceAccountKey.json` and `.env` files are
  git-ignored. `.env.example` files contain **placeholders or public-only**
  client values (Firebase web config keys are public client identifiers; service
  account keys and DB secrets are not and must never be committed).
- The backend resolves the user from the **verified token uid only** — a
  client-supplied `uid` is ignored whenever a valid token is present.

### Trust boundary

```
Mobile / Web client                         Backend (trusted)            Firebase
─────────────────────                       ──────────────────           ────────
Firebase Auth (client SDK) ── ID token ──▶  verify_id_token (Admin SDK)
                                            read/write /users/{uid}  ──▶  RTDB (LOCKED)
GET/PUT/POST  /api/...      ──────────────▶  Flask API
            ◀── JSON (no Firebase creds) ──
```

The client never holds Admin credentials and never talks to RTDB directly.

## 2. Data model — `/users/{uid}`

| Node | Written by | Notes |
|------|-----------|-------|
| `profile` | Backend (Admin SDK) on bootstrap + `PUT /api/profile/me` | `profile_complete` / `onboarding_completed` flags drive routing |
| `goals` | Backend (Admin SDK) on bootstrap | default `{steps, calories, sleep}` |
| `latest_telemetry` | Backend, when the real bracelet posts | **never** fabricated by bootstrap |
| `history/{id}` | Backend, on each reading | **never** fabricated by bootstrap |

`profile` required fields: `name`, `age`, `gender`, `height_cm`, `weight_kg`,
`activity`. Optional: `blood_type`, `emergency_contact`, `photo`.

## 3. Signup / login / onboarding flow

**Signup**
1. User creates a Firebase Auth account (client SDK).
2. App obtains a Firebase **ID token**.
3. App calls `POST /api/auth/bootstrap` (token attached).
4. Backend **verifies the token** and uses the verified uid.
5. Backend creates a **minimal** `profile` + default `goals` if missing.
6. The minimal profile is **incomplete** → `needs_onboarding = true` → app
   navigates to **onboarding**.
7. User fills the required fields once.
8. App calls `PUT /api/profile/me` (token attached).
9. Backend validates, saves via Admin SDK, sets `profile_complete = true` and
   `onboarding_completed = true`.
10. App navigates to the **dashboard**.

**Login**
1. User signs in with Firebase Auth.
2. App obtains an ID token.
3. App calls `POST /api/auth/bootstrap` (or `GET /api/me`).
4. Backend verifies the token and computes profile completeness.
5. `profile_complete = true` → **dashboard**.
6. `profile_complete = false` → **onboarding**.
7. Login **never** re-asks profile details from an already-complete user.

**Legacy users:** if the required fields already exist but the explicit
`profile_complete` flag is missing, the backend treats the profile as complete
and best-effort persists `profile_complete = true` (it never fails the request
over the flag).

## 4. Profile completion rules (backend)

A profile is **complete** only when all required fields are present **and valid**:

| Field | Validation |
|-------|-----------|
| `name` | non-empty string |
| `age` | integer 1–120 |
| `gender` | one of `male`/`female`/`other` |
| `height_cm` | number 30–300 |
| `weight_kg` | number 2–500 |
| `activity` | one of `sedentary`/`light`/`moderate`/`active`/`very_active` |

"Profile exists" is **not** "profile complete": the bootstrap creates a minimal,
intentionally incomplete profile. Legacy aliases `height`/`weight` are accepted
for `height_cm`/`weight_kg`.

## 5. Endpoints (auth-gated, backend-mediated)

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/auth/bootstrap` | Bearer ID token | Ensure profile+goals exist; return completeness |
| `GET  /api/me` | Bearer ID token | profile + goals + `profile_complete` + `needs_onboarding` + `missing_fields` |
| `PUT  /api/profile/me` | Bearer ID token | Validate + save profile (Admin SDK); set completion flags |
| `GET  /api/profile`, `/api/goals` | Bearer ID token | Read profile/goals |

`bootstrap` / `me` response shape:

```json
{
  "ok": true,
  "data": {
    "uid": "…",
    "created_profile": true,
    "created_goals": true,
    "profile": { "...": "..." },
    "goals": { "steps": 5000, "calories": 500, "sleep": 8 },
    "profile_complete": false,
    "needs_onboarding": true,
    "missing_fields": ["name", "age", "gender", "height_cm", "weight_kg", "activity"],
    "write_backend": "admin_sdk",
    "write_ok": true
  }
}
```

Invalid/expired token → `401`. A required-field validation failure on
`PUT /api/profile/me` → `400` with `missing/invalid` fields. Bootstrap never
creates `latest_telemetry` or `history`.

> `write_backend` reports the backend's actual Firebase mode. In production this
> is `admin_sdk` (locked DB, trusted writes). Memory mode is used for tests.

## 6. Telemetry / alerts / reports / AI — all via backend APIs

Telemetry ingest, alerts, reports, ML inference and the chatbot are served
through backend APIs (`/api/telemetry`, `/api/vitals/latest`, `/api/alerts`,
`/api/reports/*`, `/api/ml/predict/stress`, `/api/chat`, `/ai/medical-slm`). The
bracelet posts readings to the backend; the backend analyses and persists them
under the authenticated user. Clients only read through the API.

## 7. AI / ML components

- **WESAD stress classifier** — a **real, trained and evaluated** ML artifact
  (DeepDNN, best of a 15-model bake-off; package at
  `backend/models/wesad_vscode_model_package/`). It consumes **252 engineered
  wrist+chest features** and is therefore **not directly live-compatible** with
  the current Firebase summary fields (HR/SpO₂/temp/steps) unless a compatible
  252-feature vector is supplied. Served at `POST /api/ml/predict/stress`.
- **Risk / anomaly / intent classifiers** — supporting ML modules used in the
  telemetry analysis pipeline.
- **TinyLlama / LLM assistant** — the chatbot layer (local LoRA adapter), served
  at `POST /ai/medical-slm` with a deterministic safe fallback.
- **Rule-based safety logic** — alert thresholds, emergency guidance, device
  status, and medical refusal are **deterministic rules**, not model output.
- **The system does not diagnose disease or recommend medication.** All AI
  output is advisory and accompanied by a "not a doctor" disclaimer.

## 8. What changed vs. the earlier (outdated) report

| Outdated claim | Corrected reality |
|----------------|-------------------|
| Firebase rules opened with `.read/.write: true` | Rules stay **locked**; only the backend (Admin SDK) accesses data |
| Frontend writes to RTDB via REST | Clients **never** write RTDB; all writes go through the backend |
| `.env.example` contains real Firebase values | `.env.example` holds **placeholders / public-only** values; real secrets are git-ignored |
| Backend maps sensor data using "last frontend uid" | Sensor data is associated by the **authenticated user**; the backend is the trusted resolver |
| REST mode writes to Firebase without Admin SDK | Trusted writes require the **Admin SDK**; the backend is the only writer |
| "Profile exists" ⇒ user is set up | A profile is only **complete** when required fields are valid; onboarding is gated on that |
