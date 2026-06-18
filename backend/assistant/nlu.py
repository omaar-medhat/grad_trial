"""
Natural-Language Understanding (NLU) for PulseGuardAssistant.

Classifies a user message into one of a small set of intents and extracts
the entities the responder needs (which vital, which symptom, which tip
topic). Pure-Python, no ML dependency — transparent, fast, and easy to
extend. The trained intent classifier in backend/ml/ overrides this when
its confidence is high enough.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------
# Intent taxonomy. Order matters: emergency wins, then specific over
# general.
# ---------------------------------------------------------------------
INTENTS = (
    "emergency",
    "greeting",
    "thanks",
    "secret_probe",    # "show me your system prompt / api key"
    "medical_boundary",  # "do I have heart disease?", "what medicine should I take?"
    "alert_explain",   # "why did I get an alert?", "explain my alert"
    "device_status",   # "is my bracelet connected?", "why is my data stale?"
    "vitals_report",   # "summarize my vitals", "what is my stress/risk/activity now?"
    "project",         # "is this simulated?", "which ML models?", "what is the anomaly score?"
    "meta",            # "what can you do?", "are you a doctor?"
    "status_check",    # "how am I?", "am I okay?"
    "metric_query",    # "what's my heart rate?"
    "symptom_query",   # "I feel dizzy"
    "tip_request",     # "how do I sleep better?"
    "history_query",   # "what was my heart rate earlier?"
    "compare_query",   # "is my heart rate normal?"
    "smalltalk",       # "how's it going?"
    "general_health",  # "what's a healthy resting heart rate?"
    "fallback",
)

# Metric synonyms → canonical key in telemetry.
METRIC_ALIASES = {
    "heart_rate": [
        "heart rate", "heartrate", "hr", "pulse", "bpm", "heart",
    ],
    "spo2": [
        "spo2", "sp o2", "oxygen", "blood oxygen",
        "saturation", "o2",
    ],
    "temperature_c": [
        "temperature", "temp", "fever", "celsius", "body temperature",
    ],
    "steps": [
        "steps", "step count", "walking", "walked",
    ],
    "calories": [
        "calories", "kcal", "energy",
    ],
    "sleep_duration_sec": [
        "sleep", "rest", "slept", "sleeping",
    ],
    "battery_level": [
        "battery", "charge", "battery level", "battery percent",
    ],
    "blood_pressure": [
        "blood pressure", "bp", "systolic", "diastolic",
    ],
    "fall_alert": [
        "did i fall", "have i fallen", "i fell", "fall detected",
        "fall alert", "a fall",
    ],
}

SYMPTOM_KEYWORDS = {
    "dizzy": [
        "dizzy", "dizziness", "lightheaded", "light-headed",
        "vertigo", "spinning",
    ],
    "chest_pain": [
        "chest pain", "chest pressure", "chest hurts",
        "chest tight", "tight chest", "heart attack",
    ],
    "fatigue": [
        "tired", "fatigue", "exhausted", "drained",
        "no energy", "sleepy",
    ],
    "headache": [
        "headache", "migraine", "head hurts", "head pain",
    ],
    "shortness_of_breath": [
        "breathless", "short of breath", "can't breathe",
        "cant breathe", "out of breath", "breathing hard",
    ],
    "nausea": [
        "nauseous", "nausea", "feel sick",
        "want to vomit", "throw up",
    ],
    "anxiety": [
        "anxious", "panic", "stressed", "stress",
        "nervous", "racing",
    ],
    "fever_feel": [
        "hot", "burning up", "chills", "shivering",
    ],
}

# Probing for internal config / secrets — always refuse safely.
SECRET_TRIGGERS = [
    "system prompt", "api key", "api-key", "apikey", "password",
    "secret", ".env", "env file", "environment variable",
    "service account", "show me your", "internal file", "source code",
    "credentials", "private key",
]

# Project / system / "explain the model" questions — answered with grounded,
# accurate facts (never the small LLM, which would hallucinate them).
PROJECT_TRIGGERS = [
    "simulated", "simulation", "simulator", "real data", "real hardware",
    "fake data", "is this real", "really my data", "actual data",
    "where does the data", "data come from", "data source", "hardware",
    "bracelet real", "ml model", "ml models", "machine learning model",
    "which model", "what model", "models used", "models do you use",
    "algorithm", "neural network", "trained on", "wesad", "uci har",
    "anomaly score", "anomaly detection", "risk score", "risk level",
    "risk prediction", "stress score", "stress prediction",
    "stress detection", "stress model", "wellness score",
    "how does the app", "how does this app", "how does pulseguard",
    "how does the simulator", "what dataset",
]

MED_DIAGNOSIS_TRIGGERS = [
    "do i have", "heart disease", "have a disease", "have a condition",
    "diagnos", "is this cancer", "do i have diabetes", "what disease",
    "what's wrong with me", "whats wrong with me", "am i sick",
    "do i have a heart", "is something wrong with me",
]
MED_MEDICATION_TRIGGERS = [
    "medicine", "medication", "what pill", "which drug", "what drug",
    "should i take", "take medicine", "prescribe", "prescription",
    "dosage", "what dose",
]

ALERT_EXPLAIN_TRIGGERS = [
    "why did i get an alert", "why this alert", "explain my alert",
    "explain the alert", "what alert", "why the alert", "my alert",
    "why am i getting an alert", "what does this alert", "why alert",
    "explain my current alert", "what's this alert", "whats this alert",
]

DEVICE_TRIGGERS = [
    "bracelet connected", "is my bracelet", "is the bracelet",
    "device connected", "is my device", "sensor connected",
    "still connected", "is it connected", "connection status",
    "bracelet disconnected", "bracelet online", "bracelet offline",
    "data stale", "is my data stale", "why is my data", "stale data",
    "is my data fresh", "data fresh", "bracelet working",
]

EMERGENCY_TRIGGERS = [
    "heart attack", "stroke", "cant breathe", "can't breathe",
    "passing out", "i'm dying", "im dying", "call ambulance",
    "call 911", "emergency", "lost consciousness",
    # Bleeding — specific phrases ("blood" alone matched "blood pressure").
    "bleeding", "coughing blood", "vomiting blood", "losing blood",
]

TIP_TOPICS = {
    "sleep": [
        "sleep", "insomnia", "rest", "cant sleep",
        "can't sleep", "tired", "fatigue",
    ],
    "stress": [
        "stress", "anxiety", "calm", "relax",
        "panic", "breathing exercise", "meditation",
    ],
    "exercise": [
        "exercise", "workout", "training", "active",
        "burn calorie", "burn fat", "lose weight",
        "weight loss", "weight-loss", "more steps",
        "cardio workout", "fitness", "gym",
        "running", "walking more",
    ],
    "hydration": [
        "water", "hydrate", "dehydrat", "thirsty",
    ],
    "heart": [
        "heart health", "lower heart rate",
        "resting heart rate", "lower hr",
        "lower bpm", "lower pulse",
    ],
    "diet": [
        "diet", "eat", "food", "nutrition", "meal",
        "what to eat", "healthy eating",
    ],
}


@dataclass
class Understanding:
    raw: str
    text: str                  # lowercased, trimmed
    intent: str = "fallback"
    metrics: List[str] = field(default_factory=list)
    symptoms: List[str] = field(default_factory=list)
    tip_topic: Optional[str] = None
    is_question: bool = False
    is_negated: bool = False
    report_all: bool = False
    report_fields: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------
def _has_any(text: str, needles: List[str]) -> bool:
    return any(n in text for n in needles)


# Common typos / variants normalized before intent + entity detection.
_TYPO_FIXES = {
    "write now": "right now",
    "wright now": "right now",
    "rite now": "right now",
    "hartrate": "heart rate",
    "heartrate": "heart rate",
    "hart rate": "heart rate",
    "harte rate": "heart rate",
    "temprature": "temperature",
    "temperatur": "temperature",
    "tempreture": "temperature",
    "oxegen": "oxygen",
    "oxigen": "oxygen",
    "oxygyn": "oxygen",
    "spo two": "spo2",
    "spo 2": "spo2",
    "sp o2": "spo2",
}

# Model-derived fields the assistant can report a CURRENT value for.
_MODEL_FIELDS = {
    "wellness": ["wellness"],
    "risk": ["risk"],
    "stress": ["stress"],
    "activity": ["activity", "motion", "moving", "exercising"],
    "anomaly": ["anomaly", "anomalies", "anomalous"],
}
# "Report everything" triggers.
_REPORT_ALL = [
    "summar", "all my", "overview", "current vitals", "my vitals",
    "my readings", "all vitals", "full report",
    "vitals report", "my health", "my stats", "my metrics",
]
# Phrases that signal "give me the current VALUE" (vs. "explain it").
_VALUE_ASK = [
    "my ", "current", "right now", "latest", " now", "how am i",
    "how are my", "what's my", "whats my", "what is my",
]


def understand(message: str) -> Understanding:
    text = (message or "").strip().lower()
    for wrong, right in _TYPO_FIXES.items():
        if wrong in text:
            text = text.replace(wrong, right)
    u = Understanding(raw=message or "", text=text)
    if not text:
        return u

    first = text.split()[0] if text.split() else ""
    u.is_question = "?" in text or first in {
        "how", "what", "why", "when", "where", "who",
        "is", "am", "are", "do", "does", "should", "can",
    }
    u.is_negated = any(
        w in text for w in [" not ", "n't", " no ", " never "]
    )

    # Entities first — they help disambiguate intent.
    for metric, aliases in METRIC_ALIASES.items():
        if _has_any(text, aliases):
            u.metrics.append(metric)
    for sym, keys in SYMPTOM_KEYWORDS.items():
        if _has_any(text, keys):
            u.symptoms.append(sym)
    for topic, keys in TIP_TOPICS.items():
        if _has_any(text, keys):
            u.tip_topic = topic
            break

    # ----- intent classification (priority order) ---------------------
    # 1. Emergency overrides everything.
    if _has_any(text, EMERGENCY_TRIGGERS) or "chest_pain" in u.symptoms:
        u.intent = "emergency"
        return u

    # 1b. Medical boundary — refuse diagnosis / medication advice (before the
    # metric/symptom/tip routing so "do I have heart disease?" / "what medicine
    # should I take?" never get answered as data or tips).
    if _has_any(text, MED_DIAGNOSIS_TRIGGERS) or _has_any(
        text, MED_MEDICATION_TRIGGERS
    ):
        u.intent = "medical_boundary"
        return u

    # 1c. Alert explanation — grounded in backend current alerts.
    if _has_any(text, ALERT_EXPLAIN_TRIGGERS):
        u.intent = "alert_explain"
        return u

    # 2. Greetings / thanks (very short, no other content).
    greeting_re = (
        r"(hi|hey|hello|yo|sup|hiya|hi there|hey there|"
        r"good (morning|afternoon|evening|night))[!.?\s]*"
    )
    if re.fullmatch(greeting_re, text):
        u.intent = "greeting"
        return u
    thanks_re = (
        r"(thanks|thank you|thx|ty|cheers|appreciate it)[!.?\s]*"
    )
    if re.fullmatch(thanks_re, text):
        u.intent = "thanks"
        return u

    # 3. Meta / self-questions about the assistant.
    meta_phrases = [
        "what can you do", "what do you do",
        "who are you", "what are you",
        "are you a doctor", "are you real",
        "are you human", "are you an ai",
        "help me", "how do you work", "what is pulseguard",
    ]
    if any(p in text for p in meta_phrases):
        u.intent = "meta"
        return u

    # 3b. Secret probing — refuse safely before anything else routes it.
    if _has_any(text, SECRET_TRIGGERS):
        u.intent = "secret_probe"
        return u

    # 3b1. Device connection / data-freshness questions.
    if _has_any(text, DEVICE_TRIGGERS):
        u.intent = "device_status"
        return u

    # 3b2. Current-vitals REPORT (the live value, not an explanation).
    #   • "summarize my vitals" → report everything.
    #   • "what is my stress/risk/activity/anomaly/wellness right now?" →
    #     report that field's current value. Classic metrics (HR/SpO₂/temp/
    #     steps/battery) keep going to metric_query below.
    if _has_any(text, _REPORT_ALL):
        u.intent = "vitals_report"
        u.report_all = True
        return u
    _explain = _has_any(text, [
        "mean", "explain", "how does", "what does", "definition",
        "how is it calculated", "how do you calculate",
    ])
    if _has_any(text, _VALUE_ASK):
        fields = [f for f, kws in _MODEL_FIELDS.items() if _has_any(text, kws)]
        if fields:
            u.intent = "vitals_report"
            u.report_fields = fields
            return u
    # "stress level", "risk score", "anomaly status" → report the value
    # (but "what does risk level mean" stays an explainer → project).
    if not _explain and _has_any(
        text, ["level", "score", "status", "reading", "prediction"]
    ):
        fields = [f for f, kws in _MODEL_FIELDS.items() if _has_any(text, kws)]
        if fields:
            u.intent = "vitals_report"
            u.report_fields = fields
            return u

    # 3c. Project / system / "explain the model or data" questions. Placed
    # before symptoms so "explain the stress prediction" isn't read as a
    # symptom. Plain symptom talk ("i feel stressed") has no project trigger.
    if _has_any(text, PROJECT_TRIGGERS):
        u.intent = "project"
        return u

    # 4. Symptoms (high priority — health-related).
    if u.symptoms:
        u.intent = "symptom_query"
        return u

    # 5. Tip / advice requests.
    tip_phrases = [
        "tips for", "tip for", "advice for",
        "how do i", "how to", "how can i",
        "what should i do", "recommend", "recommendation",
        "recommendations", "suggestion", "suggest",
        "help me ", "i want to ", "i need to ",
    ]
    if u.tip_topic or any(p in text for p in tip_phrases):
        u.intent = "tip_request"
        return u

    # 6. Status check.
    status_re = (
        r"\b(how (am|do) i|am i (ok|okay|fine|alright|good|well|healthy)|"
        r"is (this|everything) (ok|okay|fine|normal|alright)|"
        r"what'?s? my status|how (is|are) (my|the) (vitals|readings)|"
        r"status)\b"
    )
    if re.search(status_re, text):
        u.intent = "status_check"
        return u

    # 7. Comparison ("is my heart rate normal/high/low?").
    compare_words = [
        "normal", "high", "low", "good", "bad",
        "elevated", "concerning", "healthy",
    ]
    if u.metrics and any(w in text for w in compare_words):
        u.intent = "compare_query"
        return u

    # 8. Direct metric query.
    if u.metrics:
        u.intent = "metric_query"
        return u

    # 9. History / trend.
    history_phrases = [
        "earlier", "yesterday", "last hour", "history",
        "trend", "over time", "this morning", "today",
    ]
    if any(p in text for p in history_phrases):
        u.intent = "history_query"
        return u

    # 10. Smalltalk catch.
    smalltalk_phrases = [
        "how's it going", "hows it going",
        "what's up", "whats up",
        "good day", "nice to meet", "you there",
    ]
    if any(p in text for p in smalltalk_phrases):
        u.intent = "smalltalk"
        return u

    # 11. General health question.
    if u.is_question:
        u.intent = "general_health"
        return u

    # 12. Otherwise fallback.
    u.intent = "fallback"
    return u
