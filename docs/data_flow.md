# Data Flow & Single Source of Truth

This project has **one canonical telemetry contract** (snake_case), used
identically by the backend, the web app, and the mobile app. No component
invents or caches its own vitals.

## Canonical contract (current state)

Returned whole by **`GET /api/vitals/latest`** and embedded in every reading:

| Field | Type | Notes |
|---|---|---|
| `heart_rate` | number | bpm |
| `spo2` | number | % |
| `temperature_c` | number | °C (canonical; never `temp`/`temperatureF` outside the legacy in-browser sim, which converts at the boundary) |
| `steps` | integer | cumulative |
| `activity` | string | resting / active / walking / running |
| `battery_level` | integer | bracelet charge % |
| `source` | string | `simulator` \| `real_bracelet` \| `uploaded_dataset` \| `unknown` |
| `is_simulated` | boolean | `source != "real_bracelet"` |
| `wellness_score` | number | 0–100 |
| `risk_level` | string | normal / warning / high |
| `stress_label` / `stress_score` | string / number | from the deterministic signal or model |
| `anomaly_status` / `anomaly_score` | string / number | `flagged`/`normal` + autoencoder score (null if not computed) |
| `risk_confidence` | number | ML risk confidence when available |
| `timestamp` | integer | ms epoch |

Missing values are **null** — never faked.

## Where each component gets its data

| Component | Source | Status |
|---|---|---|
| Web dashboard / header | `useLiveTelemetry()` → `live.data` | ✅ single hook |
| Web chat page | `useLiveTelemetry()` → sends `live.data` to `/api/chat` | ✅ same `live.data` as header |
| Web analytics | `useLiveTelemetry().history` | ✅ same hook |
| Web alerts | `useLiveTelemetry().alerts` | ✅ same hook |
| Backend chat (`/api/chat`) | **prefers client `telemetry`**, else `read_latest` | ✅ matches the UI; reports `telemetry_origin` |
| Backend vitals | `read_latest` → `_normalize_state` (`/api/vitals/latest`) | ✅ normalized |
| Backend model endpoints | `analyze()` + trained models on the **same** reading | ✅ consistent |
| Reports / analytics (backend) | `read_history` (same store) | ✅ |
| Mobile dashboard/chat/alerts/reports | `useLiveTelemetry(uid)`; chat **sends `data`** to `/api/chat` | ✅ same contract |

## Why heart rate mismatched (root cause, fixed)

The header used the **in-browser simulator** (`live.data`) while `/api/chat`
read the **backend store** (`firebase.read_latest`) — two different simulators.
Fix: the client now **sends the exact vitals it is displaying**, and the
backend **prefers them**, so chatbot answers always equal the dashboard. The
same fix was applied to the mobile chat screen.

## Demo debugging

- `GET /api/vitals/latest` — the one snapshot every layer should match.
- `/api/chat` response includes `telemetry_origin` (`client_live` /
  `backend_store` / `none`), `telemetry_source`, and `telemetry_ts`.
- `GET /health` + `GET /api/models/status` report live model/data status.
