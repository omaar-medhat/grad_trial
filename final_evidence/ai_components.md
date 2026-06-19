# AI Components

The project has two distinct AI subsystems. They are independent: a failure in
one never affects the other.

---

## 1. WESAD Stress Classifier

**Why AI is used** — Stress is not a simple threshold on one vital; it is a
pattern across many physiological channels. A learned model captures that
pattern better than hand-written rules.

- **Model type:** **DeepDNN** — a deep neural network **binary** classifier
  (`non_stress` / `stress`), selected as the best of a 15-model bake-off on the
  WESAD dataset (group / leave-subjects split).
- **Package:** `backend/models/wesad_vscode_model_package/` (self-contained:
  `inference.py`, `DeepDNN.keras`, preprocessor, metadata) — served by
  `backend/ml/stress_classifier.py`.
- **Input:** **252 engineered features** from 60-second wrist + chest windows
  (BVP/EDA/TEMP/ECG/EMG/ACC: mean, std, quantiles, spectral power, entropy, …).
- **Output:** label `stress` / `non_stress`, `stress_probability`,
  `non_stress_probability`, `confidence`, decision `threshold` (0.88).
- **Evaluation metrics (test):** accuracy ≈ **0.93**, ROC-AUC ≈ **0.98**,
  precision ≈ 0.93, recall ≈ 0.75 (threshold tuned for precision).
- **Verified prediction:** `prediction: stress`, `stress_probability ≈ 0.9969`,
  `model_name: DeepDNN`.

**Limitations**
- Requires the **full 252-feature WESAD window**; a basic bracelet
  (HR/SpO₂/temp) does **not** provide these, so it is not wired to live
  Firebase telemetry — the app does **not** fabricate missing features.
- Trained on the WESAD cohort; not a medical diagnosis.

**Failure handling**
- Package missing/incomplete → `StressClassifier` is a **stub**
  (`status: "stub"`), endpoint returns `503 MODEL_UNAVAILABLE`.
- TensorFlow missing or load error → caught and surfaced as a clear error; the
  rest of the API stays up. Loading is **lazy** (no TF at import/boot).
- scikit-learn pinned to **1.6.1** so the saved preprocessor unpickles.

---

## 2. Medical SLM (chatbot)

**Why AI is used** — to answer free-text health questions in natural language
locally, without sending data to an external LLM provider.

- **Model type:** a **local Small Language Model + LoRA adapter** (PEFT). The
  adapter is attached to a base model with `PeftModel.from_pretrained`.
- **Default local runtime:** the **lightweight TinyLlama-1.1B** adapter at
  `backend/models/medical_slm_adapter/` — runs on a normal laptop.
- **Optional heavier model:** the **Phi-3-mini** adapter at
  `backend/models/medical_phi3_lora_adapter/`, enabled via
  `MEDICAL_SLM_ADAPTER_PATH`. Phi-3 in float32 needs ~15 GB RAM and **OOMs on a
  16 GB machine**, so it is opt-in and prefers a GPU (or the bfloat16 CPU path).
- **Truthful labelling:** `model_label()` reports the base actually loaded
  (e.g. `tinyllama-1.1b-chat-v1.0-lora-medical` vs
  `phi-3-mini-4k-instruct-lora-medical`) — the API never claims Phi-3 while
  serving TinyLlama.

**Prompt safety design**
- Fixed instruction format `### Instruction:` / `### Input:` / `### Response:`.
- The system instruction tells the model to answer carefully, **avoid
  certainty**, recommend seeing a doctor when appropriate, and recommend
  **emergency care for severe symptoms**.

**Performance note (real model)**
- TinyLlama is the **real local SLM** and does generate genuine answers, but on
  a **CPU-only** machine generation is slow (tens of seconds per reply). That is
  fine for development/testing but too slow for a smooth live demo.

**Demo-safe fast mode**
- Set `MEDICAL_SLM_DEMO_MODE=true` to make `/ai/medical-slm` return the
  **deterministic `safe_fallback_answer()` instantly without loading the
  model** — reliable and fast for a panel demo on weak hardware.
- In demo mode the response is `ok:true` with
  `fallback:true`, `model:"safe-fallback"`, `demo_mode:true`.
- With demo mode **off/unset** (the default) the real TinyLlama path runs, and
  only falls back if loading/generation actually fails.

**Limitations / hallucination risk**
- A small local model can be wrong or hallucinate; it is **not** a diagnostic
  tool. Output is advisory only.
- Short context; not for long clinical histories.

**Fallback & disclaimer behavior**
- Invalid input (empty question) → `400 INVALID_INPUT`.
- Adapter files missing → `503 MODEL_UNAVAILABLE` (clear, no stack trace).
- Load/generation failure (e.g. CPU OOM) → `200` with the **safe fallback
  answer** (`fallback:true`), so the endpoint stays demo-ready instead of 500.
- Empty generation → safe fallback string.
- The fallback and the chatbot path (`chatbot_service.py`) always carry a
  **"not a doctor" disclaimer** and emergency-care guidance; the rule-based
  assistant is the always-on fallback when the model is off or fails.
- Phi-3 compatibility fixes (eager attention, normalized `rope_scaling`,
  `use_cache=False`) are applied **only to Phi-3** — they are not applied to
  TinyLlama (doing so broke it on transformers 5.x).
