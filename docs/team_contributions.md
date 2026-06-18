# Team Contributions

| Team Member | Program | Main Contributions | Evidence |
|---|---|---|---|
| **Omar Medhat** | Data Science & AI (DSAI) | AI chatbot (TinyLlama + PEFT integration), Flask backend, model loading + safety guardrails + fallback, health insight generation, AI-production checklist | [chatbot.py](../chatbot.py), [backend/chatbot_service.py](../backend/chatbot_service.py), [backend/app.py](../backend/app.py), [docs/ai_production_checklist.md](./ai_production_checklist.md) |
| **Asmaa Desokey** | Data Science & AI (DSAI) | Health-data simulation (clinical distributions), rule-based + statistical anomaly detection (Z-score, IQR, moving average, isolation), patient scenarios | [src/lib/health-data.ts](../src/lib/health-data.ts), [src/lib/anomaly-detection.ts](../src/lib/anomaly-detection.ts), [backend/anomaly_detection.py](../backend/anomaly_detection.py), [backend/simulator.py](../backend/simulator.py) |
| **Lama Omar** | Software Engineering | React + Vite dashboard, UI components (shadcn), Firebase Authentication integration (web + mobile), mobile UI scaffolding, frontend ↔ backend integration | [src/pages/](../src/pages/), [src/components/](../src/components/), [src/hooks/useAuth.tsx](../src/hooks/useAuth.tsx), [mobile/app/](../mobile/app/) |

## Cross-cutting work (all three)

- System architecture review and final defense materials
- Firebase Realtime Database schema design + rules
- Testing (Pytest backend suite, mobile manual test plan, load tests)
- Documentation suite under `docs/`
- Docker + one-command deployment story

> Run `git shortlog -sn --all` after every team member has pushed a few
> commits to back this up with raw stats for the defense panel.
