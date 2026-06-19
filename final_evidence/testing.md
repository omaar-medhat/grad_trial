# Testing

## Test types
| Type | Where | What it covers |
|------|-------|----------------|
| Unit | `backend/tests/test_ml.py`, `test_contract.py`, `test_alert_engine.py` | Model wrappers, telemetry contract, rule engine logic |
| Integration (API) | `backend/tests/test_endpoints.py`, `test_vitals_api.py`, `test_chat_*.py`, `test_auth.py`, `test_rate_limit.py` | Real Flask test client, full request/response + error envelope |
| Lightweight model | `backend/tests/test_wesad_model_package.py`, `test_medical_slm.py` | Package/adapter presence, prediction shape, prompt builder — **no heavy model load by default** |
| Safety | `test_chat_safety.py` | Disclaimer / emergency wording on chatbot replies |

The lightweight model tests deliberately **skip** the parts that need
TensorFlow / a full LLM download when those are absent, so the suite is green on
a minimal install and fully exercised on the `gp-backend` env.

## Commands

Targeted (model-focused):
```powershell
python -m pytest backend/tests/test_wesad_model_package.py backend/tests/test_ml.py backend/tests/test_medical_slm.py -q
```

Full suite:
```powershell
python -m pytest backend/tests -q
```

Manual checks:
```powershell
cd backend
python scripts/check_environment.py
python scripts/check_wesad_model.py
```

## Critical scenarios covered
- WESAD model **loads and predicts** (DeepDNN, 252 features) — package test asserts the result dict has `prediction`, `prediction_id`, `threshold`, `model_name`.
- WESAD `StressClassifier` is **package-backed**, lazy, and reports `model_name == "DeepDNN"`.
- Medical SLM **default adapter is the lightweight one** (`medical_slm_adapter`) and `model_label()` is **truthful** to the loaded base.
- Prompt builder contains `### Instruction:` / `### Input:` / `### Response:`.
- `/api/ml/predict/stress` and `/ai/medical-slm` return correct **200 / 400 / 503**.
- Rate limiting, auth gating, user-scoped data isolation, telemetry freshness.

## Failure cases tested
- Missing model files → `status == "stub"`, endpoint `503`, `predict()` returns `None`.
- Wrong-length / invalid input → `400 INVALID_INPUT`.
- Missing adapter files (medical) → clear `FileNotFoundError` / `503`.
- rope_scaling normalization for Phi-3 (`_effective_rope_scaling`) unit-tested.

## Latest passing test summary
> Environment: `gp-backend` (Python 3.11.15, scikit-learn 1.6.1, tensorflow 2.21, torch 2.12, transformers 5.12).

| Run | Result |
|-----|--------|
| `test_wesad_model_package.py + test_ml.py + test_medical_slm.py` | **35 passed** |
| Full `backend/tests` | **253 passed, 0 failed** |
| `check_wesad_model.py` | prediction = `stress`, p ≈ 0.9969, exit 0 |

_Re-run the commands above to refresh these numbers before the demo._
