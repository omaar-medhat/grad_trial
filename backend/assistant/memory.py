"""
Per-user conversation memory for PulseGuardAssistant.

Tracks topics already covered in the session so the assistant doesn't repeat
itself ("As I just said…") and can produce natural follow-ups ("Earlier you
mentioned dizziness — is it better?").
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass
class SessionState:
    user_id: str
    last_intent: Optional[str] = None
    last_symptoms: List[str] = field(default_factory=list)
    last_metrics_discussed: List[str] = field(default_factory=list)
    last_tip_topic: Optional[str] = None
    tips_given: Dict[str, int] = field(default_factory=dict)
    turn_count: int = 0
    last_turn_at: float = 0.0
    recent_turns: Deque[dict] = field(default_factory=lambda: deque(maxlen=8))


class MemoryStore:
    """In-process, thread-safe session store keyed by user_id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, SessionState] = {}

    def get(self, user_id: str) -> SessionState:
        with self._lock:
            if user_id not in self._sessions:
                self._sessions[user_id] = SessionState(user_id=user_id)
            return self._sessions[user_id]

    def update(self, user_id: str, *, intent: Optional[str] = None,
               symptoms: Optional[List[str]] = None,
               metrics: Optional[List[str]] = None,
               tip_topic: Optional[str] = None,
               user_message: Optional[str] = None,
               assistant_message: Optional[str] = None) -> SessionState:
        with self._lock:
            s = self.get(user_id)
            now = time.time()

            # Long pause → soft reset of short-term context (>15 min).
            if s.last_turn_at and now - s.last_turn_at > 15 * 60:
                s.last_intent = None
                s.last_symptoms = []
                s.last_metrics_discussed = []

            if intent is not None:
                s.last_intent = intent
            if symptoms:
                s.last_symptoms = symptoms
            if metrics:
                s.last_metrics_discussed = metrics
            if tip_topic is not None:
                s.last_tip_topic = tip_topic
                s.tips_given[tip_topic] = s.tips_given.get(tip_topic, 0) + 1

            if user_message:
                s.recent_turns.append({"role": "user", "content": user_message, "t": now})
            if assistant_message:
                s.recent_turns.append({"role": "assistant", "content": assistant_message, "t": now})

            s.turn_count += 1
            s.last_turn_at = now
            return s

    def reset(self, user_id: str) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)
