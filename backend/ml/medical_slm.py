"""
Medical Small Language Model — base LLM + fine-tuned medical LoRA adapter.

Serves a medical LoRA adapter (fine-tuned on HealthCareMagic-100k) on top of
its base model. The adapter is NOT a standalone model: we load the base model
first, then attach the adapter with `PeftModel.from_pretrained`.

Design notes
------------
* Default adapter is the LIGHTWEIGHT one at
  `backend/models/medical_slm_adapter` (TinyLlama-1.1B) — it loads on a typical
  laptop. Override with env `MEDICAL_SLM_ADAPTER_PATH`. Files are not moved.
* The Phi-3 medical adapter at `backend/models/medical_phi3_lora_adapter` is
  OPTIONAL and heavier: Phi-3-mini in float32 needs ~15 GB RAM and OOMs on a
  16 GB machine, so it is NOT the default. To serve it, point
  MEDICAL_SLM_ADAPTER_PATH at that folder (preferably with a GPU, or accept the
  bfloat16 CPU path).
* The base model is read from the adapter's own `adapter_config.json`
  (`base_model_name_or_path`) so the loader always pairs the adapter with the
  base it was trained against — a Phi-3 / TinyLlama mismatch can't crash the
  load. Override with env `MEDICAL_SLM_BASE_MODEL`.
* Loading is LAZY and the model is cached after the first call — importing this
  module is cheap and never pulls in torch/transformers.
* CUDA → 4-bit NF4 (BitsAndBytesConfig). No CUDA → CPU bfloat16 (half the RAM
  of float32) with a loud warning that generation will be slow.
* Phi-3 compatibility (harmless for TinyLlama): its remote modeling code needs
  eager attention and a normalized rope_scaling, and its DynamicCache
  regression means we disable the KV cache everywhere: `config.use_cache =
  False`, `generation_config.use_cache = False`, and `use_cache=False` inside
  `generate`.

NOT a medical diagnosis. The prompt is deliberately conservative.

Run a smoke test from the backend/ folder:

    python -m ml.medical_slm
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("pulseguard.ml.medical_slm")

# Canonical label for the Phi-3 medical model, returned by the API when the
# served base is Phi-3. model_label() reports the runtime-accurate value for
# whichever adapter is actually loaded (e.g. TinyLlama by default).
MODEL_LABEL = "phi-3-mini-4k-instruct-lora-medical"

# Fallback base only if an adapter_config.json lacks base_model_name_or_path.
DEFAULT_BASE_MODEL = "microsoft/Phi-3-mini-4k-instruct"

# Resolve the adapter path relative to this file so it works from any cwd.
# Default = the lightweight TinyLlama adapter (Phi-3 is optional, see docstring).
# backend/ml/medical_slm.py -> backend/models/medical_slm_adapter
_DEFAULT_ADAPTER_DIR = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "medical_slm_adapter"
)

ADAPTER_DIR = Path(
    os.environ.get("MEDICAL_SLM_ADAPTER_PATH", str(_DEFAULT_ADAPTER_DIR))
)

# Files that must exist for the adapter to be loadable.
_REQUIRED_ADAPTER_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "tokenizer_config.json",
    "tokenizer.json",
)

# A safe, conservative system instruction for the medical assistant.
_SYSTEM_INSTRUCTION = (
    "You are a careful medical assistant. Answer the user's health question "
    "clearly and honestly. Avoid certainty and do not give a definitive "
    "diagnosis. Explain possibilities in plain language, suggest reasonable "
    "next steps, and recommend seeing a qualified doctor when appropriate. "
    "If the symptoms could be severe or life-threatening (for example chest "
    "pain, trouble breathing, stroke signs, or heavy bleeding), tell the "
    "person to seek emergency care immediately. You are not a substitute for "
    "professional medical advice."
)

# Deterministic, conservative answer returned when the local SLM cannot load or
# generate (e.g. weak/CPU-only hardware). Keeps /ai/medical-slm demo-ready
# without ever pretending to be a real diagnosis.
SAFE_FALLBACK_ANSWER = (
    "I can't run the local AI medical model on this machine right now, but "
    "here is general, careful guidance:\n\n"
    "- For mild symptoms that have lasted only a day or two (for example a sore "
    "throat, low-grade fever, or a runny nose): rest, stay hydrated, and "
    "monitor how you feel. Over-the-counter remedies may ease symptoms.\n"
    "- See a doctor if symptoms are severe, keep getting worse, or last more "
    "than a few days, or if you have a high or persistent fever, a rash, "
    "dehydration, or any symptom that worries you.\n"
    "- Seek EMERGENCY care immediately for chest pain, difficulty breathing, "
    "signs of a stroke (face drooping, arm weakness, slurred speech), severe "
    "bleeding, a stiff neck with fever, or fainting.\n\n"
    "This is general information, not a diagnosis. I am not a doctor — please "
    "consult a qualified healthcare professional for medical advice."
)


def safe_fallback_answer() -> str:
    """Deterministic safe medical guidance for when the model is unavailable."""
    return SAFE_FALLBACK_ANSWER


def demo_mode_enabled() -> bool:
    """True when MEDICAL_SLM_DEMO_MODE is set to a truthy value.

    In demo mode the endpoint returns the deterministic safe fallback instantly
    and never loads the model — reliable on weak/CPU-only hardware for a live
    demo where real TinyLlama CPU generation is too slow."""
    return os.environ.get("MEDICAL_SLM_DEMO_MODE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


class DegenerateGenerationError(RuntimeError):
    """Raised when the model produces empty / repetitive / degenerate text.

    The endpoint treats this like any generation failure: it returns the safe
    deterministic fallback (fallback=true) instead of the garbage output.
    """


def _is_degenerate(text: Optional[str]) -> bool:
    """Detect obviously broken model output (e.g. 'Rome Rome Rome ...').

    Conservative — it only flags clearly degenerate text so it never rejects a
    real answer:
      * empty / whitespace only,
      * mostly punctuation / non-letters,
      * the same word repeated many times in a row,
      * very low unique-word diversity over a non-trivial length,
      * a single word dominating the output.
    """
    if not text or not text.strip():
        return True
    t = text.strip()

    # Mostly non-letters (punctuation / symbols / digits).
    letters = sum(c.isalpha() for c in t)
    if letters < max(3, 0.3 * len(t)):
        return True

    words = re.findall(r"[^\W\d_]+", t.lower())  # alphabetic word tokens
    if not words:
        return True

    # Longest run of the SAME word repeated consecutively ("Rome Rome Rome…").
    longest_run = 1
    run = 1
    for prev, cur in zip(words, words[1:]):
        run = run + 1 if cur == prev else 1
        longest_run = max(longest_run, run)
    if longest_run >= 4:
        return True

    counts = Counter(words)
    # A single token dominates the (non-trivial) output.
    if len(words) >= 6 and counts.most_common(1)[0][1] / len(words) > 0.5:
        return True
    # Very low diversity over a reasonable length.
    if len(words) >= 8 and len(counts) / len(words) < 0.35:
        return True

    return False


_lock = threading.Lock()
_state: dict[str, Any] = {"model": None, "tokenizer": None, "device": None}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def missing_adapter_files(adapter_dir: Optional[Any] = None) -> list[str]:
    """Return the required adapter files that are missing (empty == OK)."""
    path = Path(adapter_dir) if adapter_dir else ADAPTER_DIR
    if not path.is_dir():
        return list(_REQUIRED_ADAPTER_FILES)
    return [f for f in _REQUIRED_ADAPTER_FILES if not (path / f).exists()]


def _validate_adapter(adapter_dir: Path) -> None:
    if not adapter_dir.is_dir():
        raise FileNotFoundError(
            f"Medical adapter folder not found at {adapter_dir}. Set "
            f"MEDICAL_SLM_ADAPTER_PATH or place the adapter there."
        )
    missing = missing_adapter_files(adapter_dir)
    if missing:
        raise FileNotFoundError(
            "Medical adapter is incomplete — missing: "
            + ", ".join(missing)
            + f" (looked under {adapter_dir})."
        )


def _resolve_base_model(adapter_dir: Path) -> str:
    """Read the base model from the adapter config (env override wins)."""
    override = os.environ.get("MEDICAL_SLM_BASE_MODEL")
    if override:
        return override
    try:
        with open(adapter_dir / "adapter_config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        base = cfg.get("base_model_name_or_path")
        if base:
            return str(base)
    except Exception as exc:  # noqa: BLE001
        logger.warning("medical_slm: could not read adapter_config (%s)", exc)
    return DEFAULT_BASE_MODEL


def _is_phi3(base_model_name: str) -> bool:
    """True if the base is a Phi-3 model. Only Phi-3 needs the rope/remote-code
    compatibility surgery; applying it to Llama/TinyLlama breaks them."""
    low = (base_model_name or "").lower()
    return "phi-3" in low or "phi3" in low


def model_label(adapter_dir: Optional[Any] = None) -> str:
    """Return an API model label that reflects the base actually served.

    Phi-3 → the canonical `phi-3-mini-4k-instruct-lora-medical`; otherwise a
    slug derived from the base name (so the API never reports Phi-3 while a
    different base, e.g. TinyLlama, is loaded)."""
    target = Path(adapter_dir) if adapter_dir else ADAPTER_DIR
    base = _resolve_base_model(target)
    if _is_phi3(base):
        return MODEL_LABEL
    slug = base.split("/")[-1].lower().replace("_", "-")
    return f"{slug}-lora-medical"


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def build_prompt(question: str, context: Optional[str] = None) -> str:
    """Build the instruction-style prompt.

    Uses the classic `### Instruction: / ### Input: / ### Response:` layout so
    the fine-tuned adapter sees the same shape it was trained on.
    """
    input_block = (context or "").strip() or "(no additional context provided)"
    return (
        "### Instruction:\n"
        f"{_SYSTEM_INSTRUCTION}\n\n"
        f"Patient question: {question.strip()}\n\n"
        "### Input:\n"
        f"{input_block}\n\n"
        "### Response:\n"
    )


# ---------------------------------------------------------------------------
# Base config loading (Phi-3 rope_scaling compatibility)
# ---------------------------------------------------------------------------
# Genuine Phi-3 rope scaling types the bundled remote modeling code accepts.
# Anything else (notably the standardized "default" newer transformers injects
# for the un-scaled 4k model) must collapse to None.
_PHI3_ROPE_TYPES = {"su", "yarn", "longrope"}


def _normalize_rope_scaling(rope_scaling: Any) -> Any:
    """Mirror `type` <-> `rope_type` in a Phi-3 rope_scaling dict.

    Older Phi-3 remote modeling code reads `rope_scaling["type"]`, while newer
    transformers configs store the key as `rope_type`. When only one is present
    the other is missing and inference dies with `KeyError: 'type'`. Returning a
    dict that carries BOTH keys keeps either code path happy. Non-dict values
    (e.g. None) are returned unchanged.
    """
    if not isinstance(rope_scaling, dict):
        return rope_scaling
    rope_scaling = dict(rope_scaling)  # copy — never mutate the original
    if "type" not in rope_scaling and "rope_type" in rope_scaling:
        rope_scaling["type"] = rope_scaling["rope_type"]
    if "rope_type" not in rope_scaling and "type" in rope_scaling:
        rope_scaling["rope_type"] = rope_scaling["type"]
    return rope_scaling


def _effective_rope_scaling(rope_scaling: Any) -> Any:
    """Return rope_scaling the bundled Phi-3 modeling code accepts, else None.

    Mirrors `type`/`rope_type`, then keeps only genuine Phi-3 scaling types
    (su/yarn/longrope). Anything else — most importantly the standardized
    `{"rope_type": "default"}` that newer transformers injects for the un-scaled
    Phi-3-mini-4k model — collapses to None, so the bundled `_init_rope()` takes
    the no-scaling path instead of raising `Unknown RoPE scaling type default`.
    """
    if not isinstance(rope_scaling, dict):
        return None
    normalized = _normalize_rope_scaling(rope_scaling)
    rope_type = str(
        normalized.get("type") or normalized.get("rope_type") or ""
    ).lower()
    return normalized if rope_type in _PHI3_ROPE_TYPES else None


def _load_base_config(base_model_name: str):
    """Load the base model config and normalize its rope_scaling so Phi-3's
    remote modeling code does not raise on `type` (KeyError) or on the
    standardized "default" scaling (`Unknown RoPE scaling type default`)."""
    from transformers import AutoConfig

    config = AutoConfig.from_pretrained(
        base_model_name,
        trust_remote_code=True,
    )
    if isinstance(getattr(config, "rope_scaling", None), dict):
        config.rope_scaling = _effective_rope_scaling(config.rope_scaling)
    return config


# ---------------------------------------------------------------------------
# Model loading (lazy, cached)
# ---------------------------------------------------------------------------
def _load_model_once():
    """Load base model + LoRA adapter once and cache it. Thread-safe."""
    if _state["model"] is not None:
        return _state["model"], _state["tokenizer"], _state["device"]

    with _lock:
        if _state["model"] is not None:
            return _state["model"], _state["tokenizer"], _state["device"]

        adapter_dir = ADAPTER_DIR
        _validate_adapter(adapter_dir)
        base_model = _resolve_base_model(adapter_dir)

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Medical SLM requires torch, transformers and peft. Install "
                "them with: pip install -r requirements-ai.txt"
            ) from exc

        is_phi3 = _is_phi3(base_model)

        logger.info(
            "medical_slm: loading tokenizer from adapter %s", adapter_dir
        )
        tokenizer = AutoTokenizer.from_pretrained(
            str(adapter_dir), trust_remote_code=True
        )
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token

        use_cuda = torch.cuda.is_available()
        load_kwargs: dict[str, Any] = {
            "trust_remote_code": True,
            # Force the plain PyTorch attention. Phi-3's remote modeling code
            # otherwise selects an sdpa/flash path that warns about unsupported
            # window_size and SEGFAULTS on CPU. Eager is safe for Llama too.
            "attn_implementation": "eager",
        }
        # ONLY Phi-3 needs the normalized rope config (its remote modeling code
        # chokes on the standardized "default" scaling). Mutating rope on a
        # Llama/TinyLlama config breaks transformers 5.x — it sets
        # config.rope_parameters to None and the model then does
        # `config.rope_parameters["rope_type"]` -> TypeError. So for non-Phi-3
        # bases we pass NO custom config and let transformers build a valid one.
        if is_phi3:
            load_kwargs["config"] = _load_base_config(base_model)
        if use_cuda:
            from transformers import BitsAndBytesConfig

            load_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            load_kwargs["device_map"] = "auto"
            logger.info(
                "medical_slm: loading base '%s' in 4-bit (CUDA)", base_model
            )
        else:
            # bfloat16 (not float32): Phi-3-mini in float32 needs ~15 GB RAM and
            # OOM-segfaults on a typical 16 GB machine. bfloat16 halves that to
            # ~7.6 GB and runs fine for CPU inference. low_cpu_mem_usage keeps
            # the peak during load low.
            load_kwargs["dtype"] = torch.bfloat16
            load_kwargs["low_cpu_mem_usage"] = True
            logger.warning(
                "medical_slm: CUDA not available — loading base '%s' on CPU "
                "in bfloat16. Generation will be SLOW (tens of seconds per "
                "answer). A GPU is strongly recommended.",
                base_model,
            )

        try:
            model = AutoModelForCausalLM.from_pretrained(
                base_model, **load_kwargs
            )
            model = PeftModel.from_pretrained(
                model, str(adapter_dir), is_trainable=False
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Failed to load medical SLM (base='{base_model}', "
                f"adapter='{adapter_dir}'): {exc}"
            ) from exc

        # Phi-3 DynamicCache fix: disable the KV cache everywhere.
        model.config.use_cache = False
        if getattr(model, "generation_config", None) is not None:
            model.generation_config.use_cache = False
        model.eval()

        device = next(model.parameters()).device
        _state.update(model=model, tokenizer=tokenizer, device=device)
        logger.info("medical_slm: model ready on %s", device)
        return model, tokenizer, device


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _build_inputs(
    tokenizer, question: str, context: Optional[str], is_phi3: bool, device
):
    """Tokenize the prompt. Phi-3 uses its native chat/instruct template (which
    fixes the rambling/degenerate output from a mismatched prompt); other bases
    (TinyLlama) keep the `### Instruction:` layout their adapter was trained on.

    Returns (encoded_inputs, prompt_token_length)."""
    if is_phi3 and getattr(tokenizer, "chat_template", None):
        user = f"Patient question: {question.strip()}"
        if context and str(context).strip():
            user += f"\n\nAdditional context: {str(context).strip()}"
        # Try system+user first, then user-only (some templates reject system).
        for messages in (
            [{"role": "system", "content": _SYSTEM_INSTRUCTION},
             {"role": "user", "content": user}],
            [{"role": "user", "content": _SYSTEM_INSTRUCTION + "\n\n" + user}],
        ):
            try:
                enc = tokenizer.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    return_tensors="pt",
                    return_dict=True,
                ).to(device)
                return enc, enc["input_ids"].shape[1]
            except Exception:  # noqa: BLE001
                continue
    prompt = build_prompt(question, context)
    enc = tokenizer(prompt, return_tensors="pt").to(device)
    return enc, enc["input_ids"].shape[1]


def generate_medical_answer(
    question: str, context: Optional[str] = None
) -> str:
    """Answer a medical question with the local medical LoRA model.

    Uses safe deterministic decoding (greedy + repetition controls). If the
    decoded output is empty or degenerate (e.g. 'Rome Rome Rome ...') it raises
    `DegenerateGenerationError` so the caller returns the safe fallback instead
    of garbage. Raises FileNotFoundError if the adapter is missing and
    RuntimeError if the model cannot be loaded.
    """
    if not question or not question.strip():
        raise ValueError("question must be a non-empty string.")

    import torch

    model, tokenizer, device = _load_model_once()
    is_phi3 = _is_phi3(_resolve_base_model(ADAPTER_DIR))
    enc, input_len = _build_inputs(
        tokenizer, question, context, is_phi3, device
    )

    max_new_tokens = int(os.environ.get("MEDICAL_SLM_MAX_NEW_TOKENS", "256"))
    eos_id = tokenizer.eos_token_id
    pad_id = tokenizer.pad_token_id
    if pad_id is None:
        pad_id = eos_id

    with torch.no_grad():
        output = model.generate(
            **enc,
            max_new_tokens=max_new_tokens,
            do_sample=False,            # deterministic greedy (no temperature)
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
            use_cache=False,            # Phi-3 DynamicCache fix
            pad_token_id=pad_id,
            eos_token_id=eos_id,
        )

    # Decode ONLY the newly generated tokens, not the prompt.
    generated = output[0][input_len:]
    text = tokenizer.decode(generated, skip_special_tokens=True).strip()
    # Trim anything the model tacks on after starting a new section.
    for stop in ("### Instruction", "### Input", "### Response"):
        if stop in text:
            text = text.split(stop, 1)[0].strip()

    if _is_degenerate(text):
        logger.warning(
            "medical_slm: degenerate_generation — returning safe fallback "
            "(first 80 chars: %r)", text[:80],
        )
        raise DegenerateGenerationError("degenerate_generation")
    return text


# ---------------------------------------------------------------------------
# Smoke test:  python -m ml.medical_slm
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print(f"Adapter dir : {ADAPTER_DIR}")
    missing = missing_adapter_files()
    if missing:
        print(f"Missing adapter files: {missing}")
        raise SystemExit(1)
    print(f"Base model  : {_resolve_base_model(ADAPTER_DIR)}")

    sample_q = "I've had a mild headache and a runny nose for two days. "
    sample_q += "What could be going on and what should I do?"
    print("\n--- Prompt ---")
    print(build_prompt(sample_q))

    print("--- Generating (this loads the model; CPU is slow) ---")
    try:
        answer = generate_medical_answer(sample_q)
        degenerate = False
    except DegenerateGenerationError:
        print("[degenerate output detected — using safe fallback]")
        answer, degenerate = safe_fallback_answer(), True
    except Exception as exc:  # noqa: BLE001
        print(f"[generation failed ({exc}) — using safe fallback]")
        answer, degenerate = safe_fallback_answer(), True

    print("\n--- Answer ---")
    print(answer)
    print(f"\n[fallback used: {degenerate}]")
