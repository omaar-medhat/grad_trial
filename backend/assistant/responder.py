"""
Response composer for PulseGuardAssistant.

Given an Understanding (from nlu.py), the live telemetry, the rule-engine
analysis and the session memory, this module produces a natural-language
reply plus a list of suggested follow-up questions.

The reply is always built from the same five-step template:
  1. acknowledge   — empathic opener
  2. answer        — answer the specific question
  3. ground        — quote one or two real telemetry numbers
  4. act           — practical next step (only when relevant)
  5. follow_up     — closing question to keep the conversation flowing

Each step is optional; the composer picks the ones that fit the intent.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from .knowledge import (
    METRIC_EXPLAINERS, SYMPTOM_PLAYBOOKS, TIPS, general_health_fact, random_tip,
)
from .memory import SessionState
from .nlu import Understanding


METRIC_LABELS = {
    "heart_rate":         ("Heart rate", "bpm"),
    "spo2":               ("Blood oxygen (SpO₂)", "%"),
    "temperature_c":      ("Body temperature", "°C"),
    "steps":              ("Steps", ""),
    "calories":           ("Calories", "kcal"),
    "sleep_duration_sec": ("Sleep", "h"),
    "battery_level":      ("Battery", "%"),
    "blood_pressure":     ("Blood pressure", "mmHg"),
    "fall_alert":         ("Fall status", ""),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _format_metric_value(metric: str, telemetry: Dict[str, Any]) -> str:
    # Composite / boolean metrics first (no single telemetry key).
    if metric == "blood_pressure":
        sys_bp = telemetry.get("systolic")
        dia_bp = telemetry.get("diastolic")
        if sys_bp is None or dia_bp is None:
            return "no recent reading"
        return f"{int(round(float(sys_bp)))}/{int(round(float(dia_bp)))} mmHg"
    if metric == "fall_alert":
        v = telemetry.get("fall_alert")
        if v is None:
            return "no fall data available"
        return "a fall was detected" if v else "no fall detected"
    v = telemetry.get(metric)
    if v is None:
        return "no recent reading"
    if metric == "sleep_duration_sec":
        return f"{v / 3600:.1f} h"
    if metric == "temperature_c":
        return f"{float(v):.1f} °C"
    if metric == "spo2":
        return f"{int(round(float(v)))}%"
    if metric == "heart_rate":
        return f"{int(round(float(v)))} bpm"
    if metric == "steps":
        return f"{int(v):,} steps"
    if metric == "calories":
        return f"{int(round(float(v)))} kcal"
    if metric == "battery_level":
        return f"{int(round(float(v)))}%"
    return str(v)


def _pick(options: List[str]) -> str:
    return random.choice(options)


def _telemetry_snapshot(t: Optional[Dict[str, Any]]) -> str:
    if not t:
        return "I don't have a live reading from your bracelet yet."
    return (
        f"Heart rate {_format_metric_value('heart_rate', t)} · "
        f"SpO₂ {_format_metric_value('spo2', t)} · "
        f"Temp {_format_metric_value('temperature_c', t)}"
    )


def _format_age(secs: Any) -> str:
    if not isinstance(secs, (int, float)):
        return "a moment"
    if secs < 90:
        return f"about {int(round(secs))} seconds"
    if secs < 3600:
        return f"about {int(round(secs / 60))} minutes"
    return f"about {round(secs / 3600, 1)} hours"


def _source_note(telemetry: Optional[Dict[str, Any]]) -> str:
    """Disclose data source + bracelet freshness.

    Stale/disconnected wins over the source label: the user must always be told
    when they're looking at the last known reading rather than a fresh one. We
    never claim Firebase data is simulated, or vice-versa.
    """
    t = telemetry or {}
    status = t.get("device_status")
    secs = t.get("last_seen_seconds")
    if status == "stale":
        return (
            f" Note: this is the last known reading from {_format_age(secs)} "
            "ago — your bracelet data is currently stale."
        )
    if status == "disconnected":
        return (
            " Note: your bracelet appears disconnected, so I'm showing the "
            f"last known reading from {_format_age(secs)} ago."
        )
    src = t.get("source")
    if src == "simulator":
        return " This reading is coming from the simulator/demo data source."
    if src == "uploaded_dataset":
        return " This reading is from an uploaded dataset, not a live device."
    if src == "firebase":
        return " This is Firebase live sensor data."
    return ""


def _risk_word(level: Optional[str]) -> str:
    return {"normal": "all good", "warning": "worth watching", "high": "needs attention"}.get(
        level or "normal", "okay"
    )


# ---------------------------------------------------------------------------
# Intent-specific composers — each returns (reply_text, suggestions)
# ---------------------------------------------------------------------------

def _say_emergency(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    snapshot = _telemetry_snapshot(telemetry) if telemetry else ""
    text = (
        "⚠️ If you might be having a medical emergency, please call your local emergency number "
        "right now (in many countries this is 112, 911, or 999). "
        "If someone is nearby, ask them to help you call.\n\n"
        "While you wait, sit or lie down somewhere safe and try to stay calm. "
    )
    if snapshot:
        text += f"For reference, your current readings: {snapshot}."
    return text, ["I called for help, what should I do now?", "How do I do rescue breathing?"]


def _say_greeting(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    name_part = "👋 Hi there!"
    if telemetry:
        snap = _telemetry_snapshot(telemetry)
        return (
            f"{name_part} I just looked at your latest reading — {snap}, and overall it's "
            f"{_risk_word(analysis.get('risk_level') if analysis else None)}. "
            f"What would you like to know?"
        ), ["How am I doing right now?", "Any tips for me today?"]
    return (
        f"{name_part} I'm PulseGuard AI, your health companion. Once your bracelet sends a "
        "reading I can walk you through it. Anything you'd like to ask in the meantime?"
    ), ["What can you do?", "How do I read my vitals?"]


def _say_thanks(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    return _pick([
        "You're welcome! I'm here whenever you need me.",
        "Anytime 💚 Take care of yourself.",
        "Glad I could help — stay well!",
    ]), ["How am I doing now?", "Any tips for better sleep?"]


def _say_meta(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    return (
        "I'm **PulseGuard AI**, the assistant built into this app. I read your live vitals "
        "from your bracelet (heart rate, blood oxygen, temperature, steps, sleep), explain them "
        "in plain language, flag anything unusual, and share evidence-based tips for sleep, "
        "stress, and activity.\n\n"
        "I'm not a doctor — for any medical concern please contact a qualified clinician."
    ), [
        "How am I doing right now?",
        "What does my SpO₂ mean?",
        "Tips for better sleep",
    ]


def _say_status(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    if not telemetry:
        return (
            "I don't have a fresh reading from your bracelet yet, so I can't comment on your status. "
            "Hit \"New reading\" on the dashboard, or wait a few seconds for the next sample."
        ), ["What can you do?", "What's a healthy resting heart rate?"]

    risk = analysis.get("risk_level") if analysis else "normal"
    reasons = analysis.get("reasons", []) if analysis else []
    snap = _telemetry_snapshot(telemetry)
    if risk == "normal":
        opener = _pick([
            "You're doing well right now.",
            "Things are looking healthy from here.",
            "All your readings are in a healthy range.",
        ])
        body = f"{snap}. Nothing is flagged — keep it up."
        suggestions = ["Any tips for me today?", "How was my sleep?", "How do I lower my resting heart rate?"]
    elif risk == "warning":
        opener = "There's one or two things to keep an eye on."
        body = f"{snap}. " + (f"What I noticed: {reasons[0].lower()}" if reasons else "")
        suggestions = ["What should I do?", "Is this dangerous?", "How can I bring it back to normal?"]
    else:
        opener = "Some of your readings look concerning."
        body = f"{snap}. " + (f"In particular: {reasons[0].lower()}" if reasons else "")
        body += " Please consider slowing down and seeking medical advice if it doesn't improve."
        suggestions = ["What should I do right now?", "Should I call a doctor?", "What does this mean?"]
    return f"{opener} {body}", suggestions


def _say_metric_query(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    if not telemetry:
        asked = (u.metrics or ["reading"])[0]
        label = METRIC_LABELS.get(asked, ("reading", ""))[0].lower()
        return (
            f"I don't have a current {label} reading available right now. "
            "Tap \"New reading\" on the dashboard or give the bracelet a "
            "moment to sync."
        ), []

    def _present(m: str) -> bool:
        if m == "blood_pressure":
            return (telemetry.get("systolic") is not None
                    and telemetry.get("diastolic") is not None)
        if m == "fall_alert":
            return telemetry.get("fall_alert") is not None
        return m in telemetry and telemetry.get(m) is not None

    parts = []
    for m in u.metrics or []:
        if not _present(m):
            continue
        label, _ = METRIC_LABELS.get(m, (m, ""))
        value = _format_metric_value(m, telemetry)
        explain = METRIC_EXPLAINERS.get(m)
        if explain:
            info = explain(telemetry[m] if m != "sleep_duration_sec" else telemetry[m])
            parts.append(
                f"Your current **{label.lower()}** is {value}, which is "
                f"{info['label']}. {info['context']}"
            )
        else:
            parts.append(f"Your current **{label.lower()}** is {value}.")
    if not parts:
        return _say_status(u, telemetry, analysis, session)
    text = "\n\n".join(parts) + _source_note(telemetry)
    suggestions = []
    if "heart_rate" in u.metrics:
        suggestions.append("How do I lower my resting heart rate?")
    if "spo2" in u.metrics:
        suggestions.append("Why does SpO₂ drop?")
    if "sleep_duration_sec" in u.metrics:
        suggestions.append("Tips for better sleep")
    if not suggestions:
        suggestions = ["Am I okay overall?", "Give me a health tip"]
    return text, suggestions


def _say_compare(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    # Same shape as metric_query but biased toward the "is this normal?" framing.
    return _say_metric_query(u, telemetry, analysis, session)


def _say_symptom(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    if not u.symptoms:
        return _say_status(u, telemetry, analysis, session)
    sym = u.symptoms[0]
    book = SYMPTOM_PLAYBOOKS.get(sym)
    if not book:
        return (
            "I hear you. I don't have a specific playbook for that, but if it's bothering you "
            "or getting worse, please contact a clinician."
        ), ["What else can I tell you?", "Any tips for stress?"]

    chunks = [book["explanation"]]
    # Quote a relevant metric if we have one.
    if telemetry:
        for m in book.get("relevant_metrics", []):
            if m in telemetry:
                label, _ = METRIC_LABELS.get(m, (m, ""))
                explain = METRIC_EXPLAINERS.get(m)
                if explain:
                    info = explain(telemetry[m])
                    chunks.append(
                        f"Your current {label.lower()} is {_format_metric_value(m, telemetry)} "
                        f"({info['label']})."
                    )
                break

    actions = "\n".join(f"• {a}" for a in book["actions"])
    chunks.append(f"Things you can try right now:\n{actions}")
    chunks.append(f"_{book['escalate']}_")
    suggestions = ["I tried that, it didn't help", "Any tips for stress?", "Should I see a doctor?"]
    return "\n\n".join(chunks), suggestions


def _infer_tip_topic_from_entities(u: Understanding) -> Optional[str]:
    """Best-effort topic guess when the user didn't name one explicitly.

    Uses the metrics / symptoms / question text to land somewhere sensible
    instead of picking the first unseen topic (which used to default to
    sleep — surprising for questions like 'how do I burn calories?').
    """
    txt = u.text
    # Specific words first.
    if any(w in txt for w in ("burn", "calorie", "weight", "fat", "lose")):
        return "exercise"
    if any(w in txt for w in ("eat", "food", "meal", "diet", "nutrition")):
        return "diet"
    if any(w in txt for w in ("water", "drink", "hydrat", "thirsty")):
        return "hydration"
    if any(w in txt for w in ("heart rate", "pulse", "bpm", "lower hr")):
        return "heart"
    if any(w in txt for w in ("sleep", "rest", "insomnia", "bed")):
        return "sleep"
    if any(w in txt for w in ("stress", "anxiety", "calm", "relax", "panic")):
        return "stress"
    # Then by entity.
    if "calories" in u.metrics or "steps" in u.metrics:
        return "exercise"
    if "sleep_duration_sec" in u.metrics:
        return "sleep"
    if "heart_rate" in u.metrics:
        return "heart"
    return None


def _say_tip(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    topic = u.tip_topic or _infer_tip_topic_from_entities(u)
    if not topic:
        # No clear topic — ask the user instead of guessing wrong.
        return (
            "Happy to share advice — what would you like tips on? "
            "I can help with **sleep**, **stress**, **exercise**, "
            "**hydration**, **heart health**, or **diet**."
        ), [
            "Tips for exercise", "Tips for sleep", "Tips for stress",
            "Tips for diet",
        ]
    tips = random_tip(topic, n=3)
    if not tips:
        return (
            "I don't have specific tips on that, but I can share advice on "
            "sleep, stress, exercise, hydration, heart health, or diet. "
            "Which would you like?"
        ), [
            "Tips for sleep", "Tips for stress", "Tips for hydration",
        ]
    bullets = "\n".join(f"• {t}" for t in tips)
    return (
        f"Here are a few evidence-based tips for **{topic}**:\n\n{bullets}"
        "\n\nWant to dig deeper into any of these?"
    ), [
        f"More tips for {topic}",
        "How do these apply to me?",
        ("What does my data say about "
         + (topic if topic in ("sleep",) else "this") + "?"),
    ]


def _say_history(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    if not telemetry:
        return ("I don't have any readings to look back on yet. Once your bracelet has been "
                "sending data for a few minutes, I can describe trends."), []
    snap = _telemetry_snapshot(telemetry)
    return (
        f"Right now: {snap}. For longer trends, the **Analytics** page in the dashboard plots "
        "your heart rate, SpO₂, temperature and activity over time — that's the best place to "
        "see your day at a glance."
    ), ["Open analytics", "How was my sleep?", "Am I doing better today?"]


def _say_general_health(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    fact = general_health_fact(u.text)
    if fact:
        return fact, ["Is mine in that range?", "How do I improve it?"]
    return (
        "That's a good question — I keep my answers grounded in clinical guidelines and "
        "your live readings. Could you rephrase, or ask about your heart rate, SpO₂, "
        "temperature, sleep, or activity?"
    ), ["How am I doing right now?", "Any tips for me today?"]


def _say_secret(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    return (
        "I can't share internal configuration, secrets, credentials, or "
        "system files. I can explain your vitals, your alerts, or how the "
        "app works, though — what would you like to know?"
    ), ["How does the app work?", "Which ML models are used?", "How am I doing?"]


def _say_project(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    """Grounded, accurate answers about the system, data, and models.

    Kept factual and honest: the data is simulated until the bracelet
    hardware is ready, and nothing here is a medical diagnosis.
    """
    t = u.text
    follow = ["How does the simulator work?", "Which ML models are used?",
              "Is this real or simulated data?"]

    if any(w in t for w in (
        "simulated", "simulation", "real data", "real hardware", "fake",
        "is this real", "actual data", "data come from", "data source",
        "hardware", "really my data", "bracelet real",
    )):
        src = (telemetry or {}).get("source")
        if src == "firebase":
            return (
                "The vitals you see are **Firebase live sensor data** — read "
                "from the bracelet's Realtime Database feed, normalized by the "
                "backend, and **not** simulated. Every reading carries a "
                "`source` field (`firebase`) and a device-status so you can "
                "always tell live data from demo data. If the bracelet stops "
                "sending, I show the last known reading and label it "
                "stale/disconnected rather than inventing new values."
            ), follow
        return (
            "Right now this view is using the **simulator/demo data source** — "
            "a virtual sensor producing realistic values, not a real device. "
            "Every reading is tagged with a `source` field (`firebase` for "
            "live bracelet data vs `simulator` for demo), so live hardware "
            "data is always clearly distinguished. I never present simulated "
            "readings as real measurements."
        ), follow

    if "simulator" in t or "how is the data generated" in t or "what dataset" in t:
        return (
            "The **virtual simulator** generates realistic vitals — heart rate, "
            "SpO₂, temperature, steps/activity and battery — from clinically-"
            "grounded scenarios. You can force a scenario from the dashboard's "
            "**New reading** menu: resting, walking, running, sleep, fever, "
            "stress, anomaly, or low-battery. It stands in for the bracelet "
            "until the hardware is connected."
        ), follow

    if any(w in t for w in (
        "ml model", "ml models", "machine learning", "which model",
        "what model", "models used", "models do you use", "algorithm",
        "neural network", "wesad", "uci har", "trained on",
    )):
        return (
            "PulseGuard uses several trained models:\n"
            "• **Risk classifier** — flags normal / warning / high vitals.\n"
            "• **Anomaly autoencoder** — spots readings far from your normal.\n"
            "• **Stress model** — trained on the **WESAD** dataset (best: MLP).\n"
            "• **Activity model** — trained on the public **UCI HAR** dataset.\n"
            "• **Intent classifier** — routes your chat questions.\n"
            "• **Chat assistant** — a fine-tuned TinyLlama medical adapter, "
            "with this rule-based assistant as a safe fallback.\n\n"
            "None of these is a medical diagnostic device — they're wellness "
            "and explainability tools."
        ), ["What does the anomaly score mean?", "How does the simulator work?",
            "What does my risk level mean?"]

    if "anomaly" in t:
        return (
            "The **anomaly score** comes from an autoencoder trained only on "
            "healthy readings — it measures how far a reading sits from your "
            "normal pattern. When it crosses a threshold the reading is "
            "flagged as unusual and worth a closer look. It's an early "
            "heads-up, not a diagnosis."
        ), ["What does my risk level mean?", "How am I doing right now?"]

    if "risk" in t:
        risk = (analysis or {}).get("risk_level")
        extra = f" Your current level is **{risk}**." if risk else ""
        return (
            "The **risk level** (normal / warning / high) is decided by a "
            "transparent rule engine using AHA/WHO reference ranges, cross-"
            "checked by a trained classifier. 'high' means one or more vitals "
            "are well outside the safe range — slow down and seek advice if it "
            f"persists.{extra}"
        ), ["What should I do?", "What does the anomaly score mean?"]

    if "stress" in t:
        return (
            "The **stress** signal flags an elevated heart rate while you're "
            "physically still (the classic stress pattern), versus the same "
            "heart rate during exercise (not stress). A model trained on the "
            "**WESAD** dataset provides richer stress detection when full "
            "sensor features are available. It's a wellness indicator, not a "
            "diagnosis."
        ), ["What does my risk level mean?", "Any tips for stress?"]

    if "wellness" in t:
        return (
            "The **wellness score** (0–100) is a simple, explainable indicator "
            "of how far your vitals sit from the healthy band — higher is "
            "better. It's a wellness guide, not a medical score."
        ), ["How am I doing right now?", "What does my risk level mean?"]

    # Generic project overview.
    return (
        "**PulseGuard AI** is a software-only health-monitoring platform "
        "(the bracelet hardware is in progress). A virtual simulator streams "
        "realistic vitals → the backend validates them and runs a rule engine "
        "plus trained ML models (risk, anomaly, stress, activity) → the "
        "dashboard and this assistant explain everything in plain language. "
        "The data is currently **simulated**, clearly tagged as such."
    ), follow


def _model_value(field: str, telemetry, analysis) -> Optional[str]:
    """Current value for a model-derived field, from telemetry then analysis."""
    t = telemetry or {}
    a = analysis or {}
    if field == "wellness":
        v = t.get("wellness_score", a.get("wellness_score"))
        return f"Wellness score: **{int(v)}/100**" if v is not None else None
    if field == "risk":
        # Mirror what the dashboard shows (telemetry.risk_level) first.
        v = t.get("risk_level") or a.get("risk_level")
        return f"Risk level: **{v}**" if v else None
    if field == "stress":
        label = t.get("stress_label") or (a.get("stress") or {}).get("label")
        score = t.get("stress_score")
        if score is None:
            score = (a.get("stress") or {}).get("score")
        if label is None:
            return None
        s = f" ({score}/100)" if isinstance(score, (int, float)) else ""
        return f"Stress: **{label}**{s}"
    if field == "activity":
        v = t.get("activity") or a.get("activity")
        return f"Activity: **{v}**" if v and v != "unknown" else None
    if field == "anomaly":
        score = t.get("ml_anomaly_score")
        if score is None:
            score = ((a.get("ml") or {}).get("anomaly") or {}).get("score")
        flagged = ((a.get("ml") or {}).get("anomaly") or {}).get("is_anomaly")
        if score is None and flagged is None:
            return None
        state = "flagged" if flagged else "normal (no anomaly detected)"
        sc = f" (score {round(float(score), 2)})" if score is not None else ""
        return f"Anomaly: **{state}**{sc}"
    return None


def _say_vitals_report(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    """Report the CURRENT live values — the same numbers the dashboard shows."""
    if not telemetry:
        return (
            "I don't have any current readings available right now. Tap "
            "\"New reading\" on the dashboard or give the bracelet a moment "
            "to sync."
        ), ["How does the simulator work?", "What can you do?"]

    metric_order = [
        "heart_rate", "spo2", "temperature_c", "steps", "battery_level",
    ]
    model_order = ["wellness", "risk", "stress", "activity", "anomaly"]

    if u.report_all or not u.report_fields:
        want_metrics = [m for m in metric_order if telemetry.get(m) is not None]
        want_model = model_order
        header = "Here are your current readings:"
    else:
        want_metrics = []
        want_model = u.report_fields
        header = "Here's what I have right now:"

    lines: List[str] = []
    for m in want_metrics:
        label, _ = METRIC_LABELS.get(m, (m, ""))
        lines.append(f"• {label}: **{_format_metric_value(m, telemetry)}**")
    for f in want_model:
        line = _model_value(f, telemetry, analysis)
        if line:
            lines.append("• " + line)
        elif not u.report_all:
            lines.append(f"• {f.capitalize()}: not available right now")

    if not lines:
        return _say_status(u, telemetry, analysis, session)

    body = header + "\n" + "\n".join(lines) + _source_note(telemetry)
    suggestions = ["What does my risk level mean?",
                   "Why is my stress like that?", "How am I doing overall?"]
    return body, suggestions


def _say_device(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    """Answer 'is my bracelet connected?' / 'why is my data stale?'."""
    t = telemetry or {}
    status = t.get("device_status")
    secs = t.get("last_seen_seconds")
    suggestions = ["Summarize my current vitals", "What is my heart rate right now?"]
    if not t or (status in (None, "unknown") and t.get("heart_rate") is None):
        return (
            "I don't have a connection status for your bracelet yet — no "
            "readings have arrived. Once it starts sending data I'll show it "
            "as connected."
        ), suggestions
    if status == "connected":
        return (
            "Your bracelet looks **connected** ✅ — I'm receiving Firebase live "
            f"sensor data, last update {_format_age(secs)} ago."
        ), suggestions
    if status == "stale":
        return (
            "Your bracelet data is **stale** ⚠️ — the last reading arrived "
            f"{_format_age(secs)} ago, which is longer than expected. The "
            "bracelet may have briefly lost connection or stopped sending. "
            "I'm still showing that last known reading, not a fresh one."
        ), suggestions
    if status == "disconnected":
        return (
            "Your bracelet appears **disconnected** ❌ — the last reading was "
            f"{_format_age(secs)} ago. I'm showing the last known reading "
            "until it reconnects; I won't make up new values."
        ), suggestions
    return (
        "I'm not certain of your bracelet's connection state right now."
    ), suggestions


def _say_alert_explain(
    u: Understanding, telemetry, analysis, session, alerts=None,
) -> Tuple[str, List[str]]:
    """Explain the BACKEND-derived current alerts safely. Never invents danger
    — it only relays what the deterministic alert engine flagged."""
    follow = ["What should I do?", "Summarize my current vitals",
              "Is my bracelet connected?"]
    current = [a for a in (alerts or []) if a.get("is_current")]
    actionable = [
        a for a in current
        if a.get("severity") in ("watch", "warning", "critical")
    ]
    if not actionable:
        return (
            "Based on your latest bracelet reading, I don't see any current "
            "alerts — your readings look within the expected range. This is "
            "wellness guidance, not a medical diagnosis."
        ), follow

    order = {"watch": 1, "warning": 2, "critical": 3}
    top = max(actionable, key=lambda a: order.get(a.get("severity"), 0))
    lines = ["Based on your current bracelet alert(s):"]
    for a in actionable[:3]:
        lines.append(f"• **{a.get('title')}** — {a.get('message')}")
    tail = top.get("safe_guidance") or ""
    if top.get("emergency_guidance"):
        tail = f"{tail} {top['emergency_guidance']}".strip()
    body = (
        "\n".join(lines)
        + (f"\n\n{tail}" if tail else "")
        + "\n\n_This is wellness guidance, not a medical diagnosis._"
    )
    return body, follow


def _say_medical_boundary(
    u: Understanding, telemetry, analysis, session, alerts=None,
) -> Tuple[str, List[str]]:
    """Refuse diagnosis / medication advice safely (never diagnose or
    prescribe), and redirect to what the assistant CAN do."""
    txt = u.text
    follow = ["Summarize my current vitals", "Why did I get an alert?",
              "Is my bracelet connected?"]
    med = any(w in txt for w in (
        "medicine", "medication", "medicines", "drug", "pill", "prescri",
        "dose", "dosage", "tablet", "what should i take", "should i take",
    ))
    if med:
        return (
            "I can't recommend or prescribe any medication. I can explain your "
            "live bracelet readings and alerts, and share general wellness "
            "guidance. For anything about medicines or treatment, please ask a "
            "pharmacist or doctor."
        ), follow
    return (
        "I can't diagnose conditions like heart disease — I'm a wellness "
        "assistant, not a doctor. I can explain your bracelet readings and any "
        "current alerts in plain language. If you have chest pain, shortness "
        "of breath, fainting, severe dizziness, or symptoms that worry you, "
        "please seek medical help urgently."
    ), follow


def _say_smalltalk(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    return _pick([
        "Doing great, thanks for asking! Want me to walk through your latest reading?",
        "All good on my end. Anything I can check for you?",
        "Here and listening 🙂 What would you like to know?",
    ]), ["How am I doing?", "Any health tips?"]


def _say_fallback(u: Understanding, telemetry, analysis, session) -> Tuple[str, List[str]]:
    return (
        "I'm not sure I caught that. I can help with your live vitals, common symptoms, "
        "or quick health tips — try asking _'how am I doing?'_, _'is my heart rate normal?'_, "
        "or _'tips for better sleep'_."
    ), ["How am I doing?", "Tips for better sleep", "What does my SpO₂ mean?"]


COMPOSERS = {
    "emergency":      _say_emergency,
    "greeting":       _say_greeting,
    "thanks":         _say_thanks,
    "secret_probe":   _say_secret,
    "device_status":  _say_device,
    "alert_explain":  _say_alert_explain,
    "medical_boundary": _say_medical_boundary,
    "vitals_report":  _say_vitals_report,
    "project":        _say_project,
    "meta":           _say_meta,
    "status_check":   _say_status,
    "metric_query":   _say_metric_query,
    "compare_query":  _say_compare,
    "symptom_query":  _say_symptom,
    "tip_request":    _say_tip,
    "history_query":  _say_history,
    "general_health": _say_general_health,
    "smalltalk":      _say_smalltalk,
    "fallback":       _say_fallback,
}


def compose(u: Understanding,
            telemetry: Optional[Dict[str, Any]],
            analysis: Optional[Dict[str, Any]],
            session: SessionState,
            alerts: Optional[List[Dict[str, Any]]] = None,
            ) -> Tuple[str, List[str]]:
    composer = COMPOSERS.get(u.intent, _say_fallback)
    if u.intent in ("alert_explain", "medical_boundary"):
        text, suggestions = composer(
            u, telemetry or {}, analysis or {}, session, alerts or [],
        )
    else:
        text, suggestions = composer(u, telemetry or {}, analysis or {}, session)

    # Polite continuity: if the user already asked the same thing last turn,
    # add a tiny acknowledgement so the assistant doesn't sound like a parrot.
    if session.last_intent == u.intent and u.intent in ("status_check", "metric_query"):
        text = "As an update — " + text[0].lower() + text[1:]

    # Trim duplicate whitespace.
    text = " ".join(text.split()) if "\n\n" not in text else text.strip()
    return text, suggestions
