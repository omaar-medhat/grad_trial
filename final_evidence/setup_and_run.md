# Setup and Run

Backend targets **Python 3.11**. The WESAD preprocessor requires
**scikit-learn==1.6.1** (it fails to unpickle on 1.9.x). Full Windows guide:
[`backend/SETUP_WINDOWS.md`](../backend/SETUP_WINDOWS.md).

## 1. Create the environment (one-time)

```powershell
conda create -n gp-backend python=3.11 -y
conda activate gp-backend
cd "C:\Users\medhat\OneDrive\Desktop\elwork elfa5er\Graduation-Project-final\backend"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt        # base API + WESAD preprocessor deps
python -m pip install -r requirements-ai.txt     # heavy: tensorflow (WESAD), torch/peft (SLM)
```

> The prompt must show **`(gp-backend)`**, not `(base)`. A `(base)` / Python 3.13
> environment fails to build `pydantic-core` on Windows — use 3.11.

## 2. Verify the environment

```powershell
python scripts/check_environment.py
```
Prints Python version + interpreter, warns if not 3.11, and checks required
(flask/numpy/pandas/sklearn/joblib) and optional (tensorflow/torch/transformers/
peft) packages. Exits non-zero only if a **required** package is missing.

## 3. Verify the WESAD model

```powershell
python scripts/check_wesad_model.py
```
Loads `backend/models/wesad_vscode_model_package/sample_input.json`, runs
`predict_stress(...)` and prints the prediction. Verified output:
```json
{ "prediction": "stress", "prediction_id": 1,
  "stress_probability": 0.9969, "threshold": 0.88, "model_name": "DeepDNN" }
```

## 4. Run the backend

```powershell
flask --app app run --port 8000
# production-style:  gunicorn -w 2 -b 0.0.0.0:8000 app:app   (app = create_app())
```

## 5. (Optional) Docker one-command run
A `Dockerfile` and `docker-compose.yml` exist at the repo root:
```bash
docker compose up --build              # backend + dashboard
docker compose --profile demo up --build   # + server-side simulator
```

## Daily use
```powershell
conda activate gp-backend
cd "...\Graduation-Project-final\backend"
flask --app app run --port 8000
```

## Environment variables (optional)
| Var | Effect |
|-----|--------|
| `MEDICAL_SLM_ADAPTER_PATH` | Override the medical adapter (default = lightweight TinyLlama) |
| `LOAD_CHATBOT_MODEL` | `1` to load the local chatbot LLM at startup |
| `RATE_LIMIT_ENABLED` | `0` to disable rate limiting (tests set this) |
| `FIREBASE_DATABASE_URL` / `FIREBASE_CREDENTIALS_PATH` | Use real Firebase instead of the in-memory fallback |
