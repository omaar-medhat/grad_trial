# Demo Script

A ~5-minute walkthrough that proves the project runs, predicts, serves the AI
endpoints, and handles failure cleanly. Run each block in Windows PowerShell.

## 0. Activate the environment
```powershell
conda activate gp-backend
cd "C:\Users\medhat\OneDrive\Desktop\elwork elfa5er\Graduation-Project-final\backend"
```
> Prompt should now show `(gp-backend)`.

## 1. Verify the environment
```powershell
python scripts/check_environment.py
```
**Show:** Python 3.11, scikit-learn 1.6.1, and tensorflow/torch/transformers/peft all `[ok]`.

## 2. Verify the WESAD model (real prediction)
```powershell
python scripts/check_wesad_model.py
```
**Show:** `prediction: stress`, `model_name: DeepDNN`, `stress_probability ≈ 0.9969`.

## 3. Start the backend
```powershell
flask --app app run --port 8000
```
Leave it running; open a **second** terminal (also `conda activate gp-backend`).

## 4. Health check (no model load)
```powershell
curl http://127.0.0.1:8000/health
```
**Show:** `ok: true`, `status: ok`, `services.ml_stress: trained` — instant, lazy.

## 5. Call the Medical SLM endpoint

**TinyLlama is the real local SLM.** It produces genuine answers, but on a
**CPU-only** laptop generation is slow (tens of seconds). For a smooth, reliable
demo, enable **demo mode** — it returns a deterministic safe medical answer
**instantly without loading the model**:

```powershell
# In the backend terminal, BEFORE `flask run` (or restart with it set):
$env:MEDICAL_SLM_DEMO_MODE = "true"
flask --app app run --port 8000
```

```powershell
curl -X POST http://127.0.0.1:8000/ai/medical-slm `
  -H "Content-Type: application/json" `
  -d '{"question":"I have had a sore throat and mild fever for 2 days. What should I do?","context":"age 30, no chronic conditions"}'
```
**Show (demo mode):** `ok: true`, a safe medical answer with a disclaimer, and
`model: "safe-fallback"`, `fallback: true`, `demo_mode: true` — returned
instantly.

**Real model (optional, slower):** leave `MEDICAL_SLM_DEMO_MODE` unset, then the
same call runs the real TinyLlama — `model: "tinyllama-1.1b-chat-v1.0-lora-medical"`,
`fallback: false`. The first call loads the model (a few seconds), generation is
slower on CPU.

> Optional heavier Phi-3 model (needs more RAM/GPU; OOMs on 16 GB):
> `$env:MEDICAL_SLM_ADAPTER_PATH = "...\backend\models\medical_phi3_lora_adapter"`
> then restart the backend. `model` will then report `phi-3-mini-4k-instruct-lora-medical`.

## 6. Failure case — invalid input
```powershell
curl -X POST http://127.0.0.1:8000/ai/medical-slm -H "Content-Type: application/json" -d '{}'
```
**Show:** `HTTP 400`, `{"ok":false,"error":{"code":"INVALID_INPUT","message":"Provide a non-empty 'question'."}}`
— a clean error, **no stack trace**.

```powershell
curl -X POST http://127.0.0.1:8000/api/ml/predict/stress -H "Content-Type: application/json" -d '{"vector":[0.0,1.0]}'
```
**Show:** `HTTP 400 INVALID_INPUT` (needs the full 252 WESAD features).

## 7. Explain logs / errors
Switch to the backend terminal and point out the **access log line** for each
call: `rid=… method=POST path=/ai/medical-slm status=400 latency_ms=…`. Explain:
- every request has a **request id (rid)**,
- handled errors log a `WARNING`, unexpected ones log a full traceback
  server-side while the client still only sees `{ok:false,error}`.

## 8. (Optional) Load test
```powershell
python scripts/load_test_backend.py -n 500 -c 50
```
**Show:** ~500 req/s on `/health`, p95 ≈ 110 ms, 0 failures.

## 9. (Optional) Tests
```powershell
cd ..
python -m pytest backend/tests/test_wesad_model_package.py backend/tests/test_ml.py backend/tests/test_medical_slm.py -q
```
**Show:** all passing.
