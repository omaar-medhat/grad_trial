# Deployment Guide

## Local development (no Docker)

```bash
# 1. Backend
cd backend
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then edit if you have real Firebase Admin creds
python -m backend.app

# 2. Frontend (in another shell)
cd ..
cp .env.example .env       # fill VITE_FIREBASE_* values
npm install
npm run dev                # http://localhost:8080

# 3. Mobile (optional, in a third shell)
cd mobile
cp .env.example .env       # fill EXPO_PUBLIC_FIREBASE_* and EXPO_PUBLIC_API_BASE_URL
npm install
npx expo start
```

Frontend → Backend wiring: `vite.config.ts` proxies `/api/*` to
`http://127.0.0.1:5000`, so no CORS surprises in dev.

## Local stack via Docker

```bash
# Build + run web stack
docker compose up --build
# open http://localhost:8080

# Same, plus a server-side simulator pumping data every 2s
docker compose --profile demo up --build
```

Mount a real Firebase Admin service-account key to enable persistence:

```
graduation-project/
└── secrets/
    └── serviceAccountKey.json   # <-- gitignored
```

then set `FIREBASE_DATABASE_URL=https://<project>-default-rtdb.firebaseio.com`
in `.env` before running compose.

## Environment variables

| var | scope | default | purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | web | `/api` | Backend root for the web app |
| `VITE_FIREBASE_API_KEY` | web | — | Firebase Web SDK config |
| `VITE_FIREBASE_AUTH_DOMAIN` | web | — | Firebase Auth domain |
| `VITE_FIREBASE_DATABASE_URL` | web | — | Realtime DB URL |
| `VITE_FIREBASE_PROJECT_ID` | web | — | Firebase project id |
| `VITE_FIREBASE_STORAGE_BUCKET` | web | — | Part of SDK config; **Cloud Storage NOT used** |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | web | — | Firebase config |
| `VITE_FIREBASE_APP_ID` | web | — | Firebase config |
| `VITE_FIREBASE_MEASUREMENT_ID` | web | — | Optional (Analytics) — we don't initialize Analytics |
| `VITE_DEMO_MODE` | web | false | Force local simulator |
| `VITE_DEMO_USER_ID` | web | demo-user-001 | Default UID when demo mode is active |
| `EXPO_PUBLIC_*` | mobile | — | Mobile equivalents (inlined at build) |
| `FIREBASE_CREDENTIALS_PATH` | backend | — | Admin SDK service-account JSON |
| `FIREBASE_DATABASE_URL` | backend | — | RTDB URL |
| `LOAD_CHATBOT_MODEL` | backend | 0 | If 1, loads TinyLlama at startup |
| `CHATBOT_TIMEOUT_SECONDS` | backend | 20 | Hard cap on model generation |
| `CORS_ORIGINS` | backend | * | Comma-separated allowlist |
| `DEFAULT_DEMO_UID` | backend | demo-user-001 | Fallback UID when no auth |

## Production deployment

The backend is a standard 12-factor WSGI app. Three production-shaped options:

- **Render / Railway / Fly.io**: point at the repo, set `Dockerfile=backend/Dockerfile`,
  add the env vars above, mount a secret containing the Firebase Admin JSON.
- **Self-hosted VM**: `gunicorn --bind 0.0.0.0:5000 --workers 2 backend.app:app`
  behind nginx with TLS.
- **Cloud Run / Container Apps**: deploy the same Docker image; mount the
  Firebase Admin secret as a file.

Frontend builds (`npm run build`) produce a static `dist/` you can serve from
the `Dockerfile.frontend` nginx image, S3+CloudFront, Netlify, Vercel, or
Firebase Hosting (`firebase deploy --only hosting`).

To deploy the Realtime Database security rules:

```bash
firebase login
firebase use lab10prototyping
firebase deploy --only database
```

Mobile build:
```bash
cd mobile
eas build -p android --profile preview     # requires `eas-cli`
eas build -p ios     --profile preview
```

## Rollback strategy

- Backend: container deployment → keep the previous image tag (`:n-1`), and
  switch back via `docker compose up -d backend` with the old image.
- Frontend: previous Vercel/Netlify deployment is one click. For
  self-hosted nginx, keep `dist/` symlinked: `dist -> dist-2026-05-26`.
- Firebase data: RTDB has automatic daily backups (enable in console). Schema
  changes are additive (we never delete fields) so older clients keep working.
- Auth users: Firebase Auth is centrally hosted — rollbacks don't affect user
  accounts.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `firebase: env vars missing` in browser console | `VITE_FIREBASE_*` unset | Add to `.env`, restart `npm run dev` |
| Backend logs `Firebase: ... using in-memory fallback` | Admin service-account file not present | Place file, set `FIREBASE_CREDENTIALS_PATH` |
| Chatbot says `[OFFLINE]` style replies | Model not loaded (deliberate default) | Set `LOAD_CHATBOT_MODEL=1` and install `requirements-ai.txt` |
| 404s under `/api/*` in dev | Vite proxy not picking up | Confirm backend is on port 5000; check `vite.config.ts` |
| Mobile app cannot reach backend on phone | Using `localhost` from phone | Use your machine's LAN IP, e.g. `http://192.168.1.10:5000` |
| Firebase Auth "operation-not-allowed" | Email/Password sign-in is disabled | Firebase Console → Authentication → Sign-in method → enable Email/Password |
| Reads/writes blocked by rules | Demo user not authenticated | Either deploy the rules with `auth == null` permitted (test mode) or sign in with a real Firebase Auth account |
