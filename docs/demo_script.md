# Demo Script (Defense Walkthrough)

This script walks the panel through the system in ~8 minutes. Practice it
once before the defense; numbers in brackets are rough timings.

> **Stack one-liner**: Wearable → Flask backend → Firebase Realtime Database
> → web dashboard + Expo mobile app + AI chatbot. **Firebase Auth** (Email/Password)
> for identity, **Realtime Database** for data. No Supabase, no Firestore, no Storage.

> Tip: have **three terminal tabs** open before you start —
> (1) backend, (2) frontend, (3) `python -m backend.simulator`.

## 0. Pre-flight (off-camera, 30 s)

```bash
# Tab 1
cd backend && python -m backend.app

# Tab 2
npm run dev

# Tab 3 — leave the command ready, don't run it yet
python -m backend.simulator --uid demo-user-001 --interval 2
```

Open **http://localhost:8080** and the Expo Web build (`mobile/ npx expo start --web`).

## 1. Pitch + architecture (60 s)

> "PulseGuard AI is a smart health monitoring system. A wearable sends
> vitals → Flask backend validates and analyzes them → **Firebase Realtime
> Database** broadcasts to a web dashboard and a mobile app → a healthcare
> chatbot explains the readings in plain language. Today I'll show the full
> pipeline end-to-end, including the safety guardrails and the three-tier
> fallback that keep the demo working even with the network unplugged."

Show the architecture diagram in [README.md](../README.md#architecture).

## 2. Mobile app — Firebase Auth + dashboard (90 s)

1. Open the Expo app.
2. **Option A — sign in for real**: enter email/password → Firebase Auth
   takes over → land on **Dashboard**.
3. **Option B — instant demo**: tap **"Continue as demo"** — no credentials
   needed.
4. On the Dashboard, point out:
   - the **source badge** (`Live · Firebase` if signed in, `Demo · Simulator` otherwise),
   - the **risk hero card** (green / amber / red),
   - the six metric cards,
   - the **"Send synthetic reading"** button (writes via backend → RTDB → UI).
   - the medical disclaimer at the bottom.

## 3. Web dashboard + Firebase Realtime DB (60 s)

Switch to **http://localhost:8080**, sign in (or tap "Continue as demo").

- Open the **Firebase Console → Realtime Database** in a side window.
- Run `python -m backend.simulator --uid <YOUR_UID> --interval 2`.
- Watch `users/<uid>/latest_telemetry` update in Firebase **and** the
  dashboard re-render at the same time.
- Tab → **Analytics** to show the chart updating.

## 4. Trigger an alert (45 s)

In a fourth tab, send a deliberately abnormal reading via cURL:

```bash
curl -X POST http://127.0.0.1:5000/api/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo-user-001",
    "heart_rate": 165, "spo2": 88, "temperature_c": 39.4,
    "steps": 0, "calories": 0, "sleep_duration_sec": 0,
    "timestamp": '$(date +%s%3N)'
  }'
```

- Risk hero card flips to **High Risk** (red).
- An entry appears under `users/demo-user-001/alerts/` in Firebase.
- The dashboard **Alerts** page lists the new alert with reasons.

## 5. Chatbot safety demo (60 s)

Open **AI Chat** on the web or **Assistant** in the mobile app.

- "**Am I okay?**" → returns plain-language explanation referencing live vitals,
  ends with the *not a doctor* disclaimer.
- "**Should I stop taking my medication?**" → refuses, advises clinician.
- Show the JSON response: `source: "rule_based"` and a low `latency_ms`.

If you enabled `LOAD_CHATBOT_MODEL=1`, mention that `source` would be
`model:adapter` and latency ~5–15 s on CPU.

## 6. Observability (45 s)

- `curl http://localhost:5000/health` → uptime, services, version.
- `curl http://localhost:5000/api/metrics` → live counters
  (`telemetry_ingested`, `alerts_raised`, `chat_replies`).
- Switch to the backend terminal and point out the structured access log
  with `rid=` IDs that match the response `X-Request-ID` header.

## 7. Tests + load (45 s)

- `pytest backend/tests -q` → 110 tests pass in a few seconds.
- Show [`load_tests/k6_backend_test.js`](../load_tests/k6_backend_test.js).
  If time permits, run `k6 run -e USERS=25 -e DURATION=20s load_tests/k6_backend_test.js`
  and call out the p95 line.

## 8. Resilience walkthrough (60 s)

Show what happens when things break — read these failure modes from
[docs/final_defense_answers.md](./final_defense_answers.md):

- AI model missing → rule-based reply fires.
- Firebase Auth disabled → demo mode lets the user keep going.
- Firebase RTDB unreachable → in-memory fallback / backend polling.
- Backend down → frontend simulator + stale-data badge.
- Wearable disconnected → dashboard surfaces "stale" in < 30 s.

## 9. Wrap (30 s)

> "Production-grade pieces are in place — Docker, env-driven config, tests,
> rule engine, fallbacks, and a clear separation between **what the AI does**
> and **what the deterministic rules do**, which is critical for healthcare.
> Known limitations and next steps are in `docs/maturity_checklist_mapping.md`."
