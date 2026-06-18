# PulseGuard AI — Mobile App (Expo / React Native)

A cross-platform (Android / iOS) companion for the PulseGuard AI smart health
bracelet. It is a **thin client of the Flask backend**: every reading, alert,
report, profile and goal comes from the backend APIs.

## Architecture & security (read this first)

```
Bracelet → Firebase Realtime DB → Flask backend (Firebase Admin SDK)
                                 → backend APIs → 📱 Mobile app
```

* The mobile app talks **only** to the backend APIs. It **does NOT** read the
  Firebase Realtime Database directly, and it **does NOT** contain the Firebase
  Admin SDK.
* **Never** put `serviceAccountKey.json`, Firebase Admin credentials, private
  keys, or any backend secret in this app or in `mobile/.env`. The only Firebase
  used here is the **public web Auth config** (login → uid).
* All data is **user-scoped** by the signed-in user's `uid` (`?uid=` on each
  call). In `DATA_SOURCE=firebase` mode the app shows live Firebase data only —
  never simulator data.

Backend endpoints used: `/api/health`, `/api/vitals/latest`,
`/api/vitals/history`, `/api/device/status`, `/api/alerts`,
`/api/alerts/current`, `/api/reports/daily`, `/api/profile`, `/api/goals`,
`/api/chat`.

## Screens
- **Dashboard** — connection/device status (Firebase live / stale / disconnected
  / offline), HR, SpO₂, temperature, blood pressure, battery, steps, calories,
  sleep, fall status, risk/stress labels, wellness, current-alert summary.
- **History** — recent Firebase history (via backend), empty state when none.
- **Reports** — daily summary from backend (`/api/reports/daily`), insufficient-
  history state.
- **Alerts** — current vs historical alerts from the backend alert engine
  (severity, message, safe + emergency guidance).
- **Assistant** — `/api/chat`, grounded in the same backend telemetry/alerts.
- **Profile** — read-only profile + goals from the backend, plus backend/data-
  source/connection status. Sign out (Firebase Auth).

Every screen has loading / empty / error states and never shows a blank screen.

## Prerequisites
- Node 18+, the **Expo Go** app on your phone (or an Android/iOS emulator).
- The Flask backend running and reachable (`firebase_mode=admin_sdk`,
  `firebase_read_ok=true`).

## Install & run
```bash
cd mobile
cp .env.example .env          # set EXPO_PUBLIC_API_BASE_URL (see below)
npm install
npx expo start                # press 'a' Android, 'i' iOS, or scan QR in Expo Go
```

### Setting `EXPO_PUBLIC_API_BASE_URL` (the backend URL)
This is the #1 thing to get right — pick the form that matches how you run:

| Running on… | `EXPO_PUBLIC_API_BASE_URL` |
|---|---|
| Android **emulator** | `http://10.0.2.2:5000` (emulator alias for your PC's localhost) |
| iOS **simulator** | `http://localhost:5000` |
| **Physical phone** (Expo Go) | `http://<your-PC-LAN-IP>:5000`, e.g. `http://192.168.1.20:5000` |

Find your LAN IP: Windows `ipconfig` (IPv4 Address), macOS/Linux `ifconfig`/`ip a`.
Phone and PC must be on the **same Wi-Fi**. Restart `expo start` after editing `.env`.

### Connect to the local backend
From the project root (separate terminal):
```bash
python -m backend.app        # serves http://localhost:5000 (Admin SDK)
curl http://localhost:5000/api/health   # expect firebase_mode=admin_sdk, firebase_read_ok=true
```

## Verify live Firebase data appears in the app
1. Backend `/api/health` shows `firebase_mode=admin_sdk`, `firebase_read_ok=true`.
2. Sign in (or Continue as demo) in the app.
3. Dashboard shows the connection badge as **Firebase live** and real values
   (HR/SpO₂/temp/BP/battery) that update every ~2 s while the bracelet streams.
4. Stop the bracelet → status becomes **Stale** then **Disconnected**, the last
   reading stays visible, and the Assistant says it's using the last known
   reading. No simulator values ever appear.

## Common networking problems
- **"Network error" / nothing loads:** wrong `EXPO_PUBLIC_API_BASE_URL`.
  Emulator → `10.0.2.2`; physical phone → your PC's LAN IP (not `localhost`).
- **Phone can't reach PC:** same Wi-Fi? PC firewall may block port 5000 — allow
  inbound on 5000, or use a tunnel.
- **`firebase_read_ok=false` on the backend:** that's a backend/credentials issue
  (service account / clock skew), not the app — see the backend docs.

## Auth
Firebase Email/Password (`useAuth`, AsyncStorage persistence) **only to obtain
the uid**, plus a one-tap **Continue as demo**. No database access. Sign out
clears both the Firebase session and the demo cache.

## Notifications
`useAlertNotifications` raises a **local** notification for new `warning`/
`critical` **backend** alerts (deduped by condition). Remote push (FCM/APNs) is
the documented upgrade path (dev build + Expo push token registered with the
backend).

## Known limitations
- History/Reports are simple lists/summaries (no heavy charts) for a clean
  mobile UX; `react-native-svg` charts are an easy follow-up.
- Profile/goals are **read-only** in the app (no backend write endpoint yet).
- Notifications are **local** (on-device) — see above for remote push.
- `expo lint` may need a clean standalone `npm install` (eslint can conflict if
  hoisted with the web project's eslint v9); `npm run tsc` is the primary check.
