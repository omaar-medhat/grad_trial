"""
TinyLlama + fine-tuned LoRA adapter — local inference test.

Production-style loader that mirrors the Colab setup but degrades gracefully
off-GPU:
  * On CUDA  -> 4-bit NF4 quantization (bitsandbytes), float16 compute.
  * On CPU   -> full-precision float32 (bitsandbytes 4-bit needs CUDA).

Usage:
  python test_llama.py                       # runs a couple of test prompts
  python test_llama.py --interactive         # chat loop
  python test_llama.py --prompt "Explain SpO2 in simple words"
  python test_llama.py --adapter ./path/to/adapter
"""

from __future__ import annotations

import argparse
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
# Bundled fine-tuned medical LoRA adapter (copied into the repo).
DEFAULT_ADAPTER = "backend/models/medical_slm_adapter"


def load(adapter_path: str):
    use_cuda = torch.cuda.is_available()
    print(f"[load] CUDA available: {use_cuda}")

    tok_src = adapter_path if _has_tokenizer(adapter_path) else BASE_MODEL
    tokenizer = AutoTokenizer.from_pretrained(tok_src)

    kwargs = {}
    if use_cuda:
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        kwargs["device_map"] = "auto"
        print("[load] using 4-bit NF4 quantization")
    else:
        kwargs["torch_dtype"] = torch.float32
        print("[load] CPU mode — full precision float32 (no 4-bit)")

    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, **kwargs)

    if adapter_path:
        try:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter_path)
            print(f"[load] LoRA adapter loaded from {adapter_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[load] no adapter loaded ({exc}) — base model only")

    model.eval()
    print(f"[load] ready in {time.time() - t0:.1f}s")
    return model, tokenizer


def _has_tokenizer(path: str) -> bool:
    import os
    return bool(path) and os.path.exists(
        os.path.join(path, "tokenizer_config.json")
    )


def generate(model, tokenizer, prompt: str, max_new_tokens: int = 160) -> str:
    chat = [
        {"role": "system", "content":
         "You are a careful health assistant. You are not a doctor."},
        {"role": "user", "content": prompt},
    ]
    enc = tokenizer.apply_chat_template(
        chat, add_generation_prompt=True, return_tensors="pt", return_dict=True
    )
    enc = {k: v.to(model.device) for k, v in enc.items()}
    input_len = enc["input_ids"].shape[1]
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )
    text = tokenizer.decode(out[0][input_len:], skip_special_tokens=True)
    print(f"  (generated in {time.time() - t0:.1f}s)")
    return text.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=DEFAULT_ADAPTER)
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--max-new-tokens", type=int, default=160)
    args = ap.parse_args()

    model, tokenizer = load(args.adapter)

    if args.interactive:
        print("\nModel ready. Type 'exit' to stop.\n")
        while True:
            text = input("You: ")
            if text.lower().strip() in ("exit", "quit"):
                break
            print("\nAI:", generate(model, tokenizer, text, args.max_new_tokens))
            print("-" * 50)
        return

    prompts = [args.prompt] if args.prompt else [
        "My heart rate has been 110 while resting. Should I worry?",
        "Explain what SpO2 means in simple words.",
    ]
    for p in prompts:
        print(f"\nYou: {p}")
        print("AI:", generate(model, tokenizer, p, args.max_new_tokens))
        print("-" * 50)


if __name__ == "__main__":
    main()
