"""
Clinical knowledge base for PulseGuardAssistant.

These are short, sourced reference ranges and educational facts the
assistant draws on. Each entry is human-written, plain-language, and
mirrors the thresholds enforced by the rule engine in
``backend/anomaly_detection.py`` so the user never gets contradictory
information across the dashboard and the chat.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Metric explainers — keyed by canonical metric name.
# Each explainer returns a tuple (status_word, plain_message).
# ---------------------------------------------------------------------------
def explain_heart_rate(value: float) -> Dict[str, str]:
    if value < 40:
        return {"status": "critical", "label": "critically low",
                "msg": "very far below the normal resting range",
                "context": "Most healthy adults sit between 60 and 100 beats per minute at rest."}
    if value < 60:
        return {"status": "low", "label": "on the low side",
                "msg": "slightly below the typical resting range",
                "context": "This can be normal for athletes or during deep rest. If you feel fine, no need to worry."}
    if value <= 100:
        return {"status": "normal", "label": "healthy",
                "msg": "in the normal resting range",
                "context": "A resting heart rate between 60 and 100 bpm is considered healthy for most adults."}
    if value <= 140:
        return {"status": "elevated", "label": "elevated",
                "msg": "above the typical resting range",
                "context": "Recent exercise, caffeine, stress, or anxiety can cause this temporarily."}
    return {"status": "critical", "label": "critically high",
            "msg": "well above the typical resting range",
            "context": "If this isn't from exercise, stop activity, sit down, and consider seeking medical help."}


def explain_spo2(value: float) -> Dict[str, str]:
    if value >= 95:
        return {"status": "normal", "label": "healthy",
                "msg": "in the normal range",
                "context": "Blood oxygen of 95% or higher is considered healthy for most adults."}
    if value >= 92:
        return {"status": "low", "label": "slightly low",
                "msg": "a little below the normal range",
                "context": "Try sitting upright and taking slow, deep breaths for a few minutes."}
    return {"status": "critical", "label": "critically low",
            "msg": "well below the normal range",
            "context": "This can be a sign of breathing trouble — please seek medical advice if it persists."}


def explain_temperature(value: float) -> Dict[str, str]:
    if value >= 38.5:
        return {"status": "critical", "label": "high fever",
                "msg": "in the high-fever range",
                "context": "Rest, hydrate, and consider seeing a clinician if it stays high or other symptoms appear."}
    if value > 37.5:
        return {"status": "elevated", "label": "slightly elevated",
                "msg": "above your normal range",
                "context": "Sometimes this happens after exercise or in warm environments. Keep an eye on it."}
    if value < 35.5:
        return {"status": "low", "label": "below normal",
                "msg": "below the normal range",
                "context": "Make sure you're warm. If you feel cold, shivery, or unwell, contact a clinician."}
    return {"status": "normal", "label": "normal",
            "msg": "in the healthy range",
            "context": "Normal body temperature is roughly 36.0–37.5 °C."}


def explain_steps(value: int) -> Dict[str, str]:
    if value >= 10000:
        return {"status": "great", "label": "excellent",
                "msg": "well above the daily 10,000-step target",
                "context": "Great job staying active today."}
    if value >= 6000:
        return {"status": "good", "label": "good",
                "msg": "a healthy amount of activity",
                "context": "Aiming for around 8–10k steps a day is a common healthy target."}
    if value >= 2000:
        return {"status": "low", "label": "light",
                "msg": "on the lighter side",
                "context": "Even a short walk can help — try a 10-minute stroll if you can."}
    return {"status": "very_low", "label": "very low",
            "msg": "very low so far today",
            "context": "Even small movement breaks every hour can make a difference."}


def explain_sleep(seconds: int) -> Dict[str, str]:
    hours = seconds / 3600
    if hours >= 9:
        return {"status": "high", "label": "long",
                "msg": f"a long stretch ({hours:.1f} h)",
                "context": "Most adults need 7–9 hours. Consistent rest matters more than total time."}
    if hours >= 7:
        return {"status": "good", "label": "healthy",
                "msg": f"{hours:.1f} hours — within the healthy range",
                "context": "7–9 hours is the typical adult recommendation."}
    if hours >= 5:
        return {"status": "low", "label": "a little short",
                "msg": f"{hours:.1f} hours — a bit below the recommended range",
                "context": "Try to wind down 30 minutes earlier tonight if you can."}
    return {"status": "very_low", "label": "very short",
            "msg": f"only {hours:.1f} hours",
            "context": "Short sleep can affect heart rate and mood. Aim for at least 7 hours."}


METRIC_EXPLAINERS = {
    "heart_rate":         explain_heart_rate,
    "spo2":               explain_spo2,
    "temperature_c":      explain_temperature,
    "steps":              explain_steps,
    "sleep_duration_sec": explain_sleep,
}


# ---------------------------------------------------------------------------
# Symptom playbooks. Each returns plain-language guidance + when-to-escalate.
# ---------------------------------------------------------------------------
SYMPTOM_PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    "dizzy": {
        "explanation": "Dizziness can come from a few things — low blood sugar, dehydration, standing up too fast, or a change in your heart rate.",
        "actions": [
            "Sit or lie down somewhere safe.",
            "Sip some water and avoid sudden movements.",
            "Breathe slowly and steadily for a couple of minutes.",
        ],
        "escalate": "Call a doctor right away if it gets worse, you faint, or you also feel chest discomfort or numbness.",
        "relevant_metrics": ["heart_rate", "spo2"],
    },
    "fatigue": {
        "explanation": "Feeling drained can be caused by short sleep, dehydration, low activity, or stress.",
        "actions": [
            "Drink a glass of water.",
            "Take a 5–10 minute movement break.",
            "Try to wind down earlier tonight.",
        ],
        "escalate": "If extreme tiredness lasts for several days, it's worth speaking to a clinician.",
        "relevant_metrics": ["sleep_duration_sec", "steps"],
    },
    "headache": {
        "explanation": "Headaches often come from dehydration, screen fatigue, tension, or skipped meals.",
        "actions": [
            "Drink water and rest your eyes for 10 minutes.",
            "Step away from screens and stretch your neck and shoulders.",
            "If you haven't eaten in a while, have a light snack.",
        ],
        "escalate": "Seek urgent medical help if it's sudden and severe, or comes with vision changes, weakness, or confusion.",
        "relevant_metrics": ["spo2"],
    },
    "shortness_of_breath": {
        "explanation": "Feeling out of breath without exertion can be linked to oxygen levels, anxiety, or respiratory issues.",
        "actions": [
            "Sit upright and place your hands on your knees.",
            "Breathe in slowly through your nose for 4 seconds, out through pursed lips for 6 seconds.",
            "Repeat for a couple of minutes and see if it eases.",
        ],
        "escalate": "If breathing doesn't ease, your lips look blue, or you have chest pain, please get emergency care immediately.",
        "relevant_metrics": ["spo2", "heart_rate"],
    },
    "nausea": {
        "explanation": "Nausea can be caused by something you ate, dehydration, anxiety, or motion.",
        "actions": [
            "Sit upright and take slow breaths.",
            "Try small sips of water.",
            "If it helps, a small piece of bread or a cracker can settle the stomach.",
        ],
        "escalate": "If you can't keep liquids down for several hours, or there's severe pain, please seek medical advice.",
        "relevant_metrics": [],
    },
    "anxiety": {
        "explanation": "When you feel anxious, your heart rate can climb and your breathing speeds up — even without exercise.",
        "actions": [
            "Try a box-breathing technique: inhale 4 s · hold 4 s · exhale 4 s · hold 4 s · repeat.",
            "Name three things you can see and three you can hear — a quick way to ground yourself.",
            "Step somewhere quieter if you can.",
        ],
        "escalate": "If anxiety is overwhelming or persistent, talking to a mental-health professional can really help.",
        "relevant_metrics": ["heart_rate"],
    },
    "fever_feel": {
        "explanation": "Feeling overheated or shivery can be a sign your body temperature is changing.",
        "actions": [
            "Drink water and find a cool, calm spot.",
            "Take your temperature using the bracelet for a reliable reading.",
        ],
        "escalate": "If you're shivering, very hot, and feel unwell, see a clinician — especially if temperature stays above 38.5 °C.",
        "relevant_metrics": ["temperature_c"],
    },
}


# ---------------------------------------------------------------------------
# Tip libraries — short, evidence-based, written in friendly tone.
# ---------------------------------------------------------------------------
TIPS: Dict[str, List[str]] = {
    "sleep": [
        "Aim for 7–9 hours, with a regular bed and wake time — even on weekends.",
        "Dim lights and put screens away 30–60 minutes before bed.",
        "Keep the room cool (around 18–20 °C) and as dark as possible.",
        "Avoid caffeine after midday — it can stay in your system for 6+ hours.",
        "If you can't sleep within 20 minutes, get up, do something calm, then return when sleepy.",
    ],
    "stress": [
        "Try box breathing: in 4 s, hold 4 s, out 4 s, hold 4 s, repeat 4 times.",
        "Step outside for a 5-minute walk — natural light and movement both help.",
        "Name what's stressing you out loud or in a note — it reduces its mental weight.",
        "Limit news and social media when you're already feeling tense.",
    ],
    "exercise": [
        "Most adults benefit from 150 minutes of moderate activity per week.",
        "Start small — a daily 20-minute walk is more sustainable than a weekly gym marathon.",
        "Mix cardio with two short strength sessions per week.",
        "Listen to your body — sore is fine, sharp pain isn't.",
    ],
    "hydration": [
        "Aim for around 1.5–2 L of water daily — more if you exercise or it's hot.",
        "Sip throughout the day; don't wait until you're thirsty.",
        "Pale-yellow urine is a good hydration signal; dark yellow means drink more.",
    ],
    "heart": [
        "Lower resting heart rate over time with regular cardio (walking, cycling, swimming).",
        "Limit caffeine and alcohol — both can elevate resting heart rate.",
        "Manage stress: 5 minutes of slow breathing daily makes a measurable difference.",
        "Sleep well — short sleep raises resting heart rate noticeably.",
    ],
    "diet": [
        "Build half your plate from vegetables when you can.",
        "Choose whole grains over refined ones (brown rice, oats, whole-wheat bread).",
        "Watch added sugar — drinks are the biggest source for most people.",
        "Don't skip meals; it usually leads to overeating later.",
    ],
}


def random_tip(topic: str, n: int = 3) -> List[str]:
    items = TIPS.get(topic, [])
    return items[:n]


def general_health_fact(query: str) -> Optional[str]:
    """
    Lightweight Q&A on common general-health questions. Plain rules keep us
    honest — we only answer when we recognize a question we have a sourced
    fact for; otherwise the responder falls back to a meta reply.
    """
    q = query.lower()
    if "resting heart rate" in q or "normal heart rate" in q:
        return ("A healthy resting heart rate for most adults sits between 60 and 100 beats per minute. "
                "Athletes often have lower resting rates (40–60) thanks to their conditioning.")
    if "normal spo2" in q or "good spo2" in q or "normal oxygen" in q:
        return ("Healthy adults usually have blood oxygen (SpO₂) of 95% or higher. "
                "Anything under 92% is considered low and worth attention.")
    if "normal body temperature" in q or "normal temperature" in q:
        return ("A normal body temperature is around 36.5–37.5 °C (97.7–99.5 °F), though it varies "
                "slightly by person and time of day.")
    if "how many steps" in q:
        return ("A commonly cited target is 10,000 steps a day, but research shows real benefits start "
                "much lower — even 7,000–8,000 steps a day is meaningfully healthier than being sedentary.")
    if "how much sleep" in q or "how many hours of sleep" in q:
        return ("Most adults do best with 7–9 hours of sleep per night. Children and teens need more.")
    if "how much water" in q:
        return ("A common guide is 1.5–2 L of water per day for adults, more if you're active or it's hot. "
                "Your urine being pale yellow is a good sign you're hydrated.")
    return None
