"""
PulseGuard AI Assistant — a fully-local, neuro-symbolic healthcare assistant.

This is *our* assistant, built specifically for PulseGuard. It does not call
any external API (no OpenAI / Claude / Gemini). It runs on the same Flask
backend, so there is zero network latency and zero data leaves the user's
device.

Architecture:
  nlu.py        — intent classification + entity extraction
  knowledge.py  — clinical facts (vitals ranges, symptoms, recommendations)
  memory.py     — per-user conversation state (topics seen, last intent)
  responder.py  — composes the actual reply from intent + entities + telemetry

The public surface is one class:
  >>> from backend.assistant import PulseGuardAssistant
  >>> bot = PulseGuardAssistant()
  >>> bot.reply(user_id, "Am I okay?", telemetry, analysis, history)
  {"response": "...", "source": "pulseguard_ai", "intent": "status_check", "latency_ms": 3}
"""

from .assistant import PulseGuardAssistant

__all__ = ["PulseGuardAssistant"]
