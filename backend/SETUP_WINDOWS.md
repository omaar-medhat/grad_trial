# Backend setup on Windows (Python 3.11)

This backend targets **Python 3.11**. Do **not** install it from the Anaconda
`(base)` environment or from Python 3.13.

## Why a dedicated Python 3.11 environment?

Installing from `(base)` on **Python 3.13** fails while building
`pydantic-core`: pip can't find a prebuilt wheel for 3.13, falls back to a
**source build**, and the Rust/C++ build then errors with *"link.exe not
found"* (no Visual C++ Build Tools).

The fix is **not** to install Visual Studio Build Tools. The clean fix is to use
**Python 3.11**, which has prebuilt wheels for `pydantic-core` (and for
`numpy`, `pandas`, `scikit-learn`, `tensorflow`, `torch`, …), so nothing
compiles from source and no C++ toolchain is needed.

## One-time setup

Run these in **Windows PowerShell**:

```powershell
conda create -n gp-backend python=3.11 -y
conda activate gp-backend
cd "C:\Users\medhat\OneDrive\Desktop\elwork elfa5er\Graduation-Project-final\backend"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -r requirements-ai.txt
```

> Your prompt must now show **`(gp-backend)`** at the start of the line — not
> `(base)`. If it still says `(base)`, run `conda activate gp-backend` again.

`requirements-ai.txt` is heavy (TensorFlow for the WESAD model, PyTorch +
Transformers + PEFT for the medical SLM). It is optional — install it only when
you want to run the stress model or the medical chatbot. The Flask API itself
boots fine with just `requirements.txt`.

> **scikit-learn is pinned to `==1.6.1`.** The saved WESAD preprocessor
> (`SimpleImputer` + `RobustScaler` inside `wesad_vscode_model_package`) was
> fitted with scikit-learn **1.6.1**. Newer versions (e.g. 1.9.x) fail to
> unpickle it with `AttributeError: 'SimpleImputer' object has no attribute
> '_fill_dtype'`. Always install from `requirements.txt` (not a newer
> scikit-learn) so the WESAD model loads. `joblib` is pinned to `1.4.2` to match.

### Note on `bitsandbytes`

`bitsandbytes` (4-bit GPU quantization) is for **CUDA/Linux GPUs**. On
**Windows CPU** it is not required and the pip wheel may fail to install — that
is fine. It is intentionally gated to Linux in `requirements-ai.txt`, so a
normal Windows CPU install skips it. The medical SLM automatically falls back to
CPU float32 when CUDA is unavailable (slower, but it runs).

## Verify the environment

```powershell
python scripts/check_environment.py
```

This prints your Python version + interpreter path, warns if you are not on
3.11, and lists which required/optional packages are importable. It exits
non-zero only if a **required** package is missing.

## Test the WESAD stress model

```powershell
python scripts/check_wesad_model.py
```

Loads the bundled `sample_input.json`, runs `predict_stress(...)` and prints the
prediction dict. Needs `tensorflow` (from `requirements-ai.txt`) to load the
DeepDNN model.

## Test the Medical SLM setup (no download)

The Medical SLM defaults to the **lightweight** adapter at
`backend/models/medical_slm_adapter/` (TinyLlama-1.1B), which loads on a normal
laptop. The **Phi-3** adapter at `backend/models/medical_phi3_lora_adapter/` is
**optional and heavy** — Phi-3-mini in float32 needs ~15 GB RAM and can **OOM**
on a 16 GB Windows machine. Do **not** run Phi-3 locally on a weak machine; use
a GPU/server, or accept the slower bfloat16 CPU path. Switch adapters with:

```powershell
$env:MEDICAL_SLM_ADAPTER_PATH = "...\backend\models\medical_phi3_lora_adapter"
```

`model_label()` (and the API `model` field) always reports the base actually
loaded, so it never claims Phi-3 while serving TinyLlama.

Lightweight tests (do not download or load any model):

```powershell
cd "C:\Users\medhat\OneDrive\Desktop\elwork elfa5er\Graduation-Project-final"
python -m pytest backend/tests/test_medical_slm.py -q
```

Direct inference downloads the base model on first run and is slow on CPU:

```powershell
cd "C:\Users\medhat\OneDrive\Desktop\elwork elfa5er\Graduation-Project-final\backend"
python -m ml.medical_slm
```

## Run the Flask backend

```powershell
flask --app app run --port 8000
```

Then, in another terminal:

```powershell
curl -X POST http://localhost:8000/ai/medical-slm `
  -H "Content-Type: application/json" `
  -d '{"question":"I have had a sore throat and mild fever for 2 days. What should I do?","context":"age 30, no chronic conditions"}'
```

## Daily use

After the one-time setup, each new terminal just needs:

```powershell
conda activate gp-backend
cd "C:\Users\medhat\OneDrive\Desktop\elwork elfa5er\Graduation-Project-final\backend"
flask --app app run --port 8000
```
