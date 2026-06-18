"""
PulseGuardAssistant — orchestrates NLU + trained NN intent classifier +
optional real LLM + symbolic responder + per-user memory.

Three-tier brain (in priority order):

  1. **Emergency safety override** — regex NLU detects emergency keywords
     → we always answer with the emergency playbook, never the LLM.

  2. **Real LLM** (Groq / OpenAI / Anthropic / Ollama, auto-detected) —
     when an API key is configured, the LLM handles open-ended questions
     with the live telemetry injected into the system prompt.

  3. **Symbolic + trained-NN fallback** — the original PulseGuardAssistant
     using regex + the trained intent classifier + the knowledge base.
     Used when no LLM is configured or the LLM call fails.

In every tier we strip jargon and keep responses friendly.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ..llm_client import LLMClient
from .memory import MemoryStore
from .nlu import understand
from .responder import compose

logger = logging.getLogger("pulseguard.assistant")

EMERGENCY_PREFIX = (
    "⚠️ Your readings show a critical pattern. Please stop activity and "
    "seek professional medical help right away. "
)

NN_CONFIDENCE_THRESHOLD = 0.45

# Regex-detected structural intents the trained classifier can't represent;
# a confident regex match for these must not be overridden by the NN.
_NN_PROTECTED = frozenset({
    "emergency", "project", "secret_probe", "vitals_report",
    "meta", "greeting", "thanks", "device_status",
    "medical_boundary", "alert_explain",
})

LLM_SYSTEM_PROMPT_TEMPLATE = """\
You are PulseGuard AI, a wellness assistant inside a real-time health \
monitoring bracelet app. The bracelet's readings come from Firebase live \
sensor data. You are NOT a doctor and NOT a general chatbot.

Your job:
- Explain the user's live bracelet readings and alerts in simple language.
- Answer questions about current vitals, alerts, device status, and reports.
- Use ONLY the telemetry, alerts and device status provided below.
- Give safe, general wellness guidance and recommend urgent medical help for \
serious symptoms.

Live readings from the user's bracelet right now (Firebase):
{telemetry_block}

Current risk assessment from the rule engine: {risk_level}
{alert_message_block}

You MUST NOT:
- invent sensor values or alerts that are not provided above;
- diagnose diseases or claim the user has a condition;
- predict that the user will have a medical event;
- prescribe or recommend medications or dosages;
- claim the data is live if the device is stale/disconnected;
- say the data is a simulator/demo when the source is Firebase.

Style:
- Conversational, warm, direct; avoid jargon; under 150 words.
- Reference the user's actual numbers above when relevant.
- Do NOT begin with "Hi"/"Hello" unless the user greeted you first.
- If the data is stale/disconnected, say you are showing the last known \
reading. If a value is missing, say it is unavailable — do not guess.
- For a clear emergency, calmly tell them to call their local emergency \
number (112, 911, or 999).
"""


class PulseGuardAssistant:
    """Single instance per process; thread-safe."""

    def __init__(self) -> None:
        self._memory = MemoryStore()
        self._llm = LLMClient()

        try:
            from ..ml import get_models
            self._intent_classifier = get_models().intent
            self.intent_classifier_status = self._intent_classifier.status
        except Exception as exc:
            logger.warning(
                "Assistant: intent classifier unavailable (%s)", exc
            )
            self._intent_classifier = None
            self.intent_classifier_status = "unavailable"

    # ------------------------------------------------------------------
    def reply(
        self,
        user_id: str,
        message: str,
        telemetry: Optional[Dict[str, Any]] = None,
        analysis: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        alerts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        start = time.time()
        user_id = user_id or "anonymous"

        if not message or not message.strip():
            return {
                "response": (
                    "Please type a question — I can help with your "
                    "vitals, symptoms, or health tips."
                ),
                "source": "pulseguard_ai",
                "intent": "empty",
                "latency_ms": 0,
                "suggestions": [
                    "How am I doing?", "Any tips for me?",
                ],
                "nn_intent": None,
            }
        if len(message) > 2000:
            message = message[:2000]

        # Step 1: regex NLU for entities + first-pass intent.
        u = understand(message)
        regex_intent = u.intent

        # Step 2: trained NN intent classifier (optional override).
        # The NN was trained on the original taxonomy, so it can't emit the
        # structural intents below — protect a confident regex match for them
        # from being clobbered by a stale NN label.
        nn_label: Optional[str] = None
        nn_confidence: Optional[float] = None
        if (
            self._intent_classifier is not None
            and u.intent not in _NN_PROTECTED
        ):
            pred = self._intent_classifier.predict(message)
            if pred is not None:
                nn_label = pred.label
                nn_confidence = pred.confidence
                if (
                    pred.confidence >= NN_CONFIDENCE_THRESHOLD
                    and pred.label != "fallback"
                ):
                    u.intent = pred.label

        # Step 3: choose brain.
        #   • Emergency: always symbolic (safety override).
        #   • Else if LLM available: real LLM with telemetry context.
        #   • Else: symbolic + trained NN.
        session = self._memory.get(user_id)
        text: str
        source: str
        suggestions: List[str] = []
        if u.intent == "emergency":
            text, suggestions = compose(u, telemetry, analysis, session, alerts)
            source = "pulseguard_ai+safety"
        elif self._llm.is_available:
            llm_reply = self._llm.chat(
                system_prompt=self._build_llm_system_prompt(
                    telemetry, analysis
                ),
                messages=self._build_llm_history(history, message),
            )
            if llm_reply is not None:
                text = llm_reply.text
                source = f"llm:{llm_reply.provider}"
                suggestions = self._suggest_follow_ups(
                    u, telemetry, analysis
                )
            else:
                # LLM call failed — fall back to symbolic.
                text, suggestions = compose(u, telemetry, analysis, session, alerts)
                source = (
                    "pulseguard_ai+nn"
                    if nn_label and u.intent == nn_label
                    else "pulseguard_ai"
                )
        else:
            text, suggestions = compose(u, telemetry, analysis, session, alerts)
            source = (
                "pulseguard_ai+nn"
                if nn_label and u.intent == nn_label
                else "pulseguard_ai"
            )

        text = self._apply_safety(text, analysis, u.intent)

        self._memory.update(
            user_id,
            intent=u.intent,
            symptoms=u.symptoms,
            metrics=u.metrics,
            tip_topic=u.tip_topic,
            user_message=message,
            assistant_message=text,
        )

        latency_ms = int((time.time() - start) * 1000)
        return {
            "response": text,
            "source": source,
            "intent": u.intent,
            "regex_intent": regex_intent,
            "nn_intent": nn_label,
            "nn_confidence": (
                round(nn_confidence, 4)
                if nn_confidence is not None else None
            ),
            "latency_ms": latency_ms,
            "suggestions": suggestions,
        }

    # ------------------------------------------------------------------
    def _build_llm_system_prompt(
        self,
        telemetry: Optional[Dict[str, Any]],
        analysis: Optional[Dict[str, Any]],
    ) -> str:
        if telemetry:
            sleep_hours = (
                (telemetry.get("sleep_duration_sec") or 0) / 3600
            )
            tb = (
                f"- Heart rate: {telemetry.get('heart_rate', 'n/a')} bpm\n"
                f"- SpO₂: {telemetry.get('spo2', 'n/a')}%\n"
                f"- Temperature: "
                f"{telemetry.get('temperature_c', 'n/a')} °C\n"
                f"- Steps today: {telemetry.get('steps', 0)}\n"
                f"- Calories: {telemetry.get('calories', 0)} kcal\n"
                f"- Sleep: {sleep_hours:.1f} h"
            )
        else:
            tb = "- No live reading yet."
        risk = (analysis or {}).get("risk_level", "unknown")
        alert = (analysis or {}).get("alert_message")
        alert_block = (
            f"Latest alert: {alert}"
            if alert and risk != "normal" else ""
        )
        return LLM_SYSTEM_PROMPT_TEMPLATE.format(
            telemetry_block=tb,
            risk_level=risk,
            alert_message_block=alert_block,
        )

    def _build_llm_history(
        self,
        history: Optional[List[Dict[str, str]]],
        new_message: str,
    ) -> List[Dict[str, str]]:
        msgs: List[Dict[str, str]] = []
        for turn in (history or [])[-6:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if not content:
                continue
            msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": new_message})
        return msgs

    def _suggest_follow_ups(
        self,
        u,
        telemetry: Optional[Dict[str, Any]],
        analysis: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Generic follow-ups when the LLM authored the reply."""
        risk = (analysis or {}).get("risk_level", "normal")
        if risk == "high":
            return [
                "What should I do right now?",
                "Should I call a doctor?",
                "What does this mean?",
            ]
        if u.intent == "symptom_query":
            return [
                "Anything I should do next?",
                "Could this be serious?",
                "Tips to feel better",
            ]
        if u.intent == "tip_request":
            return [
                "More detail on that",
                "How does this apply to me?",
                "Other ideas?",
            ]
        return [
            "How am I doing right now?",
            "Any tips for me today?",
            "Tell me about my heart rate",
        ]

    # ------------------------------------------------------------------
    # Intents where a high-risk vitals banner is relevant. Project/meta/
    # secret/greeting answers should NOT be hijacked by the emergency line.
    _MEDICAL_INTENTS = frozenset({
        "status_check", "metric_query", "compare_query", "symptom_query",
        "history_query", "general_health", "tip_request", "vitals_report",
    })

    def _apply_safety(
        self,
        text: str,
        analysis: Optional[Dict[str, Any]],
        intent: str,
    ) -> str:
        # Per user request: NO "not a doctor" disclaimer.
        # Add the emergency banner on critical readings only for medical
        # intents, and only if the reply didn't already point to getting help.
        if (
            analysis
            and analysis.get("risk_level") == "high"
            and intent in self._MEDICAL_INTENTS
        ):
            if (
                "seek" not in text.lower()
                and "emergency" not in text.lower()
                and "doctor" not in text.lower()
            ):
                text = EMERGENCY_PREFIX + text
        return text.strip()

    # ------------------------------------------------------------------
    def reset_session(self, user_id: str) -> None:
        self._memory.reset(user_id)

    def llm_info(self) -> Dict[str, Any]:
        return self._llm.info()
