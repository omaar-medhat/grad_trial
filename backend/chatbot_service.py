"""
PulseGuard AI - Healthcare Chatbot service.

Two-tier design (priority order, chosen at startup):
  1. **TinyLlama-1.1B + fine-tuned LoRA adapter** (opt-in via
     LOAD_CHATBOT_MODEL=1). The fine-tuned medical adapter generates the
     reply; telemetry context is injected into the system prompt. On CUDA it
     loads 4-bit (NF4); on CPU it loads full-precision float32 (bitsandbytes
     4-bit requires a GPU). Generation is wall-clock capped.
  2. **PulseGuardAssistant** (default + always the fallback) — fully-local
     neuro-symbolic assistant (intent NN + clinical knowledge base +
     telemetry-aware composition + per-user memory). Sub-ms latency, no
     external calls. Used when the model is off OR generation fails/empties.

Safety rails applied to EVERY reply (model or rule-based):
  * Never claim a diagnosis; append a one-line "not a doctor" disclaimer.
  * If the rule engine says "high" risk -> prepend the emergency advice line.
  * Truncate runaway repetitions / role tokens from the model tier.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from .assistant import PulseGuardAssistant

logger = logging.getLogger("pulseguard.chatbot")

_REPEAT_RE = re.compile(r"\b(\w+)( \1){3,}", flags=re.IGNORECASE)

_SYSTEM_PROMPT = (
    "You are PulseGuard AI, a careful health & wellness assistant. "
    "You are NOT a doctor and must not diagnose. Give clear, safe, concise "
    "guidance and recommend professional care when symptoms are serious."
)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    for tok in ("<|user|>", "<|assistant|>", "<|system|>"):
        text = text.replace(tok, "")
    for stop in ("\nUser:", "\nuser:", "\nQ:"):
        if stop in text:
            text = text.split(stop, 1)[0]
    text = _REPEAT_RE.sub(r"\1", text)
    return text.strip()


def _apply_safety(response: str, analysis: Optional[Dict[str, Any]]) -> str:
    response = _clean_text(response)
    if not response:
        response = "I'm not able to generate a clear answer right now."
    if "not a doctor" not in response.lower():
        response = (
            f"{response}\n\n_I'm an AI assistant, not a doctor. For any "
            f"medical concern, please consult a qualified healthcare "
            f"professional._"
        )
    if (
        analysis and analysis.get("risk_level") == "high"
        and "seek" not in response.lower()
    ):
        response = (
            "⚠️ Your readings show a critical pattern. Please stop activity "
            "and seek professional medical help right away. " + response
        )
    return response


def _telemetry_context(
    latest: Optional[Dict[str, Any]], analysis: Optional[Dict[str, Any]]
) -> str:
    if not latest:
        return ""
    bits = []
    for key, label, unit in (
        ("heart_rate", "HR", "bpm"),
        ("spo2", "SpO2", "%"),
        ("temperature_c", "temp", "C"),
    ):
        if latest.get(key) is not None:
            bits.append(f"{label} {latest[key]}{unit}")
    risk = (analysis or {}).get("risk_level")
    if risk:
        bits.append(f"risk={risk}")
    return ("Current readings: " + ", ".join(bits) + ".") if bits else ""


# ---------------------------------------------------------------------------
class ChatbotService:
    """Fine-tuned TinyLlama front (opt-in), PulseGuardAssistant fallback."""

    def __init__(
        self,
        base_model: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        adapter_path: str = "",
        timeout_seconds: float = 20.0,
        load_model: bool = False,
    ) -> None:
        self.base_model = base_model
        self.adapter_path = adapter_path
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_new_tokens = int(os.environ.get("CHATBOT_MAX_NEW_TOKENS", "160"))
        self._assistant = PulseGuardAssistant()
        self._model = None
        self._tokenizer = None
        self._device = None
        self._lock = threading.Lock()
        self.model_status = "pulseguard_ai"  # pulseguard_ai | base | adapter

        if load_model:
            self._try_load_model()

        logger.info("Chatbot initialized (model_status=%s)", self.model_status)

    # ------------------------------------------------------------------
    def _try_load_model(self) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            use_cuda = torch.cuda.is_available()
            has_adapter = bool(self.adapter_path) and os.path.isdir(
                self.adapter_path
            )
            tok_src = (
                self.adapter_path
                if has_adapter and os.path.exists(
                    os.path.join(self.adapter_path, "tokenizer_config.json")
                )
                else self.base_model
            )
            logger.info("Chatbot: loading tokenizer from '%s'", tok_src)
            tokenizer = AutoTokenizer.from_pretrained(tok_src)
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token

            load_kwargs: Dict[str, Any] = {}
            if use_cuda:
                from transformers import BitsAndBytesConfig
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
                load_kwargs["device_map"] = "auto"
                logger.info("Chatbot: loading base in 4-bit (CUDA)")
            else:
                load_kwargs["dtype"] = torch.float32
                logger.info("Chatbot: loading base in float32 (CPU)")

            model = AutoModelForCausalLM.from_pretrained(
                self.base_model, **load_kwargs
            )
            self.model_status = "base"

            if has_adapter:
                try:
                    from peft import PeftModel
                    model = PeftModel.from_pretrained(model, self.adapter_path)
                    self.model_status = "adapter"
                    logger.info(
                        "Chatbot: LoRA adapter loaded from %s",
                        self.adapter_path,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Chatbot: adapter failed (%s). Using base model.", exc
                    )

            model.eval()
            self._tokenizer = tokenizer
            self._model = model
            self._device = next(model.parameters()).device
            logger.info("Chatbot: model ready (status=%s)", self.model_status)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Chatbot: cannot load model (%s). Using PulseGuard AI only.",
                exc,
            )
            self._model = None
            self._tokenizer = None
            self.model_status = "pulseguard_ai"

    # ------------------------------------------------------------------
    def _build_messages(
        self,
        user_message: str,
        latest: Optional[Dict[str, Any]],
        analysis: Optional[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        ctx = _telemetry_context(latest, analysis)
        system = _SYSTEM_PROMPT + (f"\n{ctx}" if ctx else "")
        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        # Keep the last few turns only (CPU latency + context budget).
        for turn in (history or [])[-4:]:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _generate(self, messages: List[Dict[str, str]]) -> str:
        import torch
        enc = self._tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )
        enc = {k: v.to(self._device) for k, v in enc.items()}
        input_len = enc["input_ids"].shape[1]
        with torch.no_grad():
            out = self._model.generate(
                **enc,
                max_new_tokens=self.max_new_tokens,
                max_time=self.timeout_seconds,  # hard wall-clock cap
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(
            out[0][input_len:], skip_special_tokens=True
        )

    # ------------------------------------------------------------------
    def reply(
        self,
        user_message: str,
        latest: Optional[Dict[str, Any]] = None,
        analysis: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[str] = None,
        alerts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Returns {response, source, intent, latency_ms, suggestions}.

        Routing: data/project/vitals/safety questions go to the grounded
        rule-based assistant (correct + safe, never hallucinates project
        facts). The fine-tuned medical LLM is used only for open-ended
        general-health questions, where its fluency helps.
        """
        from .assistant.nlu import understand
        intent = understand(user_message or "").intent
        # The LLM tier handles only open-ended general health questions. Data-,
        # alert- and safety-boundary intents always use the grounded assistant
        # so the model can never invent values, alerts, diagnoses or meds.
        llm_intents = {"general_health"}
        use_llm = (
            self._model is not None
            and self._tokenizer is not None
            and intent in llm_intents
        )

        # Tier 1: fine-tuned TinyLlama (only for open health questions).
        if use_llm:
            start = time.time()
            try:
                with self._lock:  # one generation at a time (CPU/GPU safety)
                    raw = self._generate(
                        self._build_messages(
                            user_message or "", latest, analysis, history
                        )
                    )
                response = _apply_safety(raw, analysis)
                if _clean_text(raw):
                    return {
                        "response": response,
                        "source": f"model:{self.model_status}",
                        "intent": "llm",
                        "latency_ms": int((time.time() - start) * 1000),
                        "suggestions": [],
                    }
                logger.info("Chatbot: empty model output — falling back.")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Chatbot: generation failed (%s) — falling back.", exc
                )

        # Tier 2: always-available neuro-symbolic assistant (grounded in the
        # backend telemetry + backend alerts).
        return self._assistant.reply(
            user_id=user_id or "anonymous",
            message=user_message or "",
            telemetry=latest,
            analysis=analysis,
            history=history,
            alerts=alerts,
        )
