# Final Defense Answers

A panelist may ask any of these. The answers are short, true, and pointed at
specific evidence in the repo.

---

### 1. Can your system be deployed and accessed live right now?

**Answer:** Yes. `docker compose up --build` brings up the backend (port 5000)
and the static frontend (port 8080) on any machine with Docker. The mobile app
ships as an Expo project — `npx expo start` produces an Android/iOS/web
bundle and a QR code. Firebase Auth + Realtime Database are hosted by Google;
deploying the schema rules is one `firebase deploy --only database`.

**Evidence:** [docker-compose.yml](../docker-compose.yml), [backend/Dockerfile](../backend/Dockerfile),
[Dockerfile.frontend](../Dockerfile.frontend), [docs/deployment.md](./deployment.md),
[firebase.rules.json](../firebase.rules.json).

### 2. Can it handle multiple users?

**Answer:** Yes. Each Firebase Auth user has a unique `auth.uid` that becomes
the partition key under `users/{uid}/...`. Realtime Database rules enforce
that a user can only read/write their own subtree. Load testing confirms 25
concurrent users sustain sub-second p95 on the read endpoints.

**Evidence:** [firebase.rules.json](../firebase.rules.json), [backend/firebase_service.py](../backend/firebase_service.py),
[load_tests/k6_backend_test.js](../load_tests/k6_backend_test.js).

### 3. Can a new user set it up quickly?

**Answer:** Yes — three options of increasing realism:
1. `docker compose up --build` (one command).
2. Manual: copy three `.env.example` files, `pip install`, `npm install`, run.
3. Mobile: `cd mobile && npm install && npx expo start`. Tap "Continue as
   demo" to skip credentials entirely.

**Evidence:** [README.md#quickstart](../README.md), [docs/deployment.md](./deployment.md).

### 4. What architecture did you choose and why?

**Answer:** Thin REST backend, push-based persistence layer, two clients.
- Flask + Gunicorn on the backend — small, well-known, easy to deploy
  anywhere Python runs.
- Firebase Realtime Database — sub-second push to multiple clients without
  us building a websocket layer.
- Firebase Authentication (Email/Password) — managed identity, no password
  storage in our code.
- React + Vite + shadcn for the web dashboard — fast HMR, accessible components.
- Expo React Native for mobile — true native build for Android and iOS from
  one TypeScript codebase.

The split keeps the **AI** isolated as a service. We could swap TinyLlama
for any other model without touching the frontend.

**Evidence:** architecture diagram in [README.md](../README.md#architecture).

### 5. What are the main components?

**Answer:**
1. Backend (Flask) — validation + anomaly engine + chatbot + Firebase Admin writes.
2. Anomaly engine — pure-Python rule engine + a frontend ensemble for drift.
3. Chatbot — TinyLlama with PEFT adapter (optional) + deterministic rule-based fallback.
4. Firebase service — Admin SDK adapter with in-memory fallback.
5. Web dashboard (React/Vite).
6. Mobile app (Expo React Native).
7. Simulator (CLI + in-browser).
8. Auth (Firebase Email/Password) with demo bypass.

### 6. Where can the system fail?

**Answer:** We mapped each component to a fallback before it ships:
- Firebase Admin auth → in-memory store, identical contract.
- TinyLlama model unloadable → deterministic rule-based reply (< 5 ms).
- Firebase Web Auth disabled → demo mode keeps the user productive.
- Backend unreachable from web → frontend simulator + stale badge.
- Wearable disconnected → "stale data" badge after 30 s.

**Evidence:** [docs/observability.md](./observability.md), [backend/chatbot_service.py](../backend/chatbot_service.py),
[src/hooks/useAuth.tsx](../src/hooks/useAuth.tsx), [src/hooks/useLiveTelemetry.ts](../src/hooks/useLiveTelemetry.ts).

### 7. How do you handle invalid input?

**Answer:** Server-side, before any persistence. `validate_telemetry` rejects
missing fields and physically impossible values with `400 INVALID_INPUT` and
a human-readable message. Frontend validation exists too but is not relied on.

**Evidence:** [backend/anomaly_detection.py](../backend/anomaly_detection.py),
test cases T-AD-02 through T-AD-14 in [docs/testing.md](./testing.md).

### 8. What tests did you implement?

**Answer:** 44 backend tests (anomaly rules, endpoints, chatbot safety,
Firebase fallback). One frontend vitest smoke test + the existing baseline.
Mobile uses `npm run tsc` for type safety. Full catalog in
[docs/testing.md](./testing.md).

### 9. What are your load testing results?

**Answer:** Two scripts (k6 + Locust), four scenarios (10/25/50 users, plus
"+AI" variant). Headline numbers and known bottlenecks are recorded in
[docs/performance.md](./performance.md). Highlights: rule-based chatbot p95
< 200 ms, AI-mode p95 5–15 s on CPU (deliberately opt-in).

### 10. How do you monitor the system?

**Answer:** `GET /health` returns version + sub-service status (consumed by
Docker healthcheck). `GET /api/metrics` returns in-process counters. Every
request emits a structured log line with an `X-Request-ID` that the response
echoes back. See [docs/observability.md](./observability.md).

### 11. How do you deploy it?

**Answer:** Docker for everything except mobile. Backend is a standard 12-factor
container suitable for Render / Fly.io / Cloud Run. Frontend is a static
artifact suitable for any CDN (or Firebase Hosting). Rollback strategy in
[docs/deployment.md#rollback-strategy](./deployment.md#rollback-strategy).

### 12. How do you authenticate users?

**Answer:** **Firebase Authentication** with Email/Password on both clients.
The user's Firebase UID is the partition key in Realtime Database, and the
database security rules use `auth.uid === $uid` to enforce isolation. Demo
mode skips auth for a no-setup defense. See [docs/security.md#authentication](./security.md#authentication).

### 13. How is data structured?

**Answer:** Documented in [docs/firebase.md](./firebase.md). Per-user tree
in Realtime Database with `latest_telemetry`, `history/{push_id}`,
`alerts/{push_id}`, and `profile`. Schema is enforced server-side (validator)
and again at the storage layer ([firebase.rules.json](../firebase.rules.json)).
**Cloud Firestore is not used. Cloud Storage is not used.**

### 14. How does the system scale?

**Answer:** The backend is stateless (state lives in Firebase). Horizontal
scaling is one extra container. Firebase Realtime Database handles the read
fan-out for us. The chatbot is the bottleneck — production should move it
behind a worker queue with its own pool of GPU machines.

### 15. What did each team member contribute?

**Answer:** Detailed table in [docs/team_contributions.md](./team_contributions.md).
Summary: Omar (chatbot + backend), Asmaa (simulation + anomaly engine),
Lama (frontend + mobile UI + Firebase Auth integration).

### 16. Why are you using AI?

**Answer:** Two reasons. (1) **Communication**: turning raw vitals into plain
language a non-clinician can understand. (2) **Drift detection**: the
frontend ensemble (Z-score / IQR / moving average / isolation forest) catches
slow drifts that absolute-value rules miss. Rule engine + AI are complementary,
not redundant.

### 17. What happens if AI is removed?

**Answer:** The rule engine still classifies risk and raises alerts. The
chatbot still answers using the deterministic composer. Users would lose the
nuanced explanations but the dashboard and alerts continue to work — by
design.

### 18. What happens if AI fails?

**Answer:** The chatbot service catches exceptions and falls back to the
rule-based composer. Logged as a warning. End user sees a coherent, safe
reply with a `source: "rule_based"` field in the JSON (visible in DevTools).
Tested by `T-CB-01`.

### 19. What happens if Firebase fails?

**Answer:**
- Realtime DB down → backend uses in-memory fallback; web/mobile poll the
  backend's `/api/latest` instead.
- Firebase Auth disabled → users tap "Continue as demo" and the app keeps
  working with a cached demo identity in localStorage / AsyncStorage.
- Both apps show the data-source badge so the user is always informed.

Tested in `T-FB-01..05`.

### 20. What happens if the backend fails?

**Answer:** The web dashboard's `useLiveTelemetry` hook probes `/health` and
flips to the in-browser simulator if the backend doesn't answer in 800 ms.
The mobile app shows an empty state on the dashboard and a clear network
error in the chat. Both surface a "stale data" warning.

### 21. What happens if the chatbot gives a wrong answer?

**Answer:** Three layers of defense:
1. The system prompt forbids diagnosis claims.
2. `_apply_safety` post-processes every reply (disclaimer + emergency prefix
   on high-risk telemetry + repetition cleanup).
3. The UI permanently shows the medical disclaimer.

We also recommend logging chat replies for audit. Today, the backend logs
latency + `source`; turning on per-message content logging is a one-line
change with PII implications, so it's intentionally off by default.

### 22. How do you detect, debug, and fix production failure?

**Answer:**
- **Detect**: `/health` probes from Docker / uptime monitor; alert when status
  != ok or services drop. Add Sentry for exception aggregation.
- **Debug**: every request has an `X-Request-ID`. Grep the backend log for
  the rid. The chatbot reply's `source` field reveals which tier answered.
- **Fix**: roll back the container to the previous tag (frontend and backend
  are immutable images). Firebase data is preserved across rollbacks.
