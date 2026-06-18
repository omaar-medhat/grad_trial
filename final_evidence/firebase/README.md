# Firebase Evidence

Drop here:
- `firebase-latest-telemetry.png` — Firebase console showing `users/demo-user-001/latest_telemetry` with live values.
- `firebase-history.png` — same console, showing `history/` accumulating.
- `firebase-alerts.png` — same console, showing one or more `alerts/` entries with `risk_level: "high"`.
- `firebase-rules.png` — screenshot of the rules editor with our `firebase.rules.json` deployed.
- `firebase-memory-fallback.log` — backend log slice showing `Firebase: ... using in-memory fallback` when creds are absent.

Generate the events: `python -m backend.simulator --uid demo-user-001 --interval 1 --count 30`.
