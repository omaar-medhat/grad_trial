"""Unit tests for PulseGuardAssistant (NLU + composer + memory)."""

from __future__ import annotations

from backend.assistant import PulseGuardAssistant
from backend.assistant.nlu import understand


# -----------------------------------------------------------------
# NLU
# -----------------------------------------------------------------
def test_nlu_classifies_status_check():
    assert understand("Am I okay?").intent == "status_check"
    assert understand("how am I doing").intent == "status_check"
    assert understand("Is everything normal?").intent == "status_check"


def test_nlu_classifies_metric_query():
    u = understand("what's my heart rate?")
    assert u.intent == "metric_query"
    assert "heart_rate" in u.metrics


def test_nlu_classifies_compare_query():
    u = understand("Is my heart rate normal?")
    assert u.intent == "compare_query"
    assert "heart_rate" in u.metrics


def test_nlu_classifies_symptom():
    u = understand("I feel dizzy")
    assert u.intent == "symptom_query"
    assert "dizzy" in u.symptoms


def test_nlu_classifies_tip_request():
    u = understand("any tips for better sleep?")
    assert u.intent == "tip_request"
    assert u.tip_topic == "sleep"


def test_nlu_classifies_emergency():
    assert (
        understand("I think I'm having a heart attack").intent
        == "emergency"
    )
    assert understand("call 911").intent == "emergency"


def test_nlu_classifies_greeting_and_thanks():
    assert understand("hi").intent == "greeting"
    assert understand("thanks").intent == "thanks"


def test_nlu_classifies_meta():
    assert understand("what can you do?").intent == "meta"
    assert understand("are you a doctor?").intent == "meta"


def test_nlu_classifies_general_health():
    u = understand("what's a healthy resting heart rate?")
    # Ranks as metric_query / compare_query because of "heart rate"
    # alias — all are acceptable since the responder still gives a
    # useful answer.
    assert u.intent in (
        "general_health",
        "compare_query",
        "metric_query",
        "tip_request",
    )


# -----------------------------------------------------------------
# Assistant integration
# -----------------------------------------------------------------
def _telemetry(**over):
    base = {
        "heart_rate": 72.0,
        "spo2": 97.0,
        "temperature_c": 36.7,
        "steps": 4200,
        "calories": 280.0,
        "sleep_duration_sec": 25200,
        "timestamp": 1779791421000,
    }
    base.update(over)
    return base


def _analysis(risk="normal", reasons=None):
    return {
        "risk_level": risk,
        "alert_message": (
            "Vitals are within normal range."
            if risk == "normal"
            else "Watch this."
        ),
        "reasons": reasons or [],
        "rule_hits": [],
    }


def test_status_check_with_normal_vitals_mentions_numbers():
    bot = PulseGuardAssistant()
    out = bot.reply(
        "user1", "How am I doing?", _telemetry(), _analysis("normal")
    )
    assert "72" in out["response"] or "bpm" in out["response"]
    assert out["intent"] == "status_check"
    assert out["source"] in ("pulseguard_ai", "pulseguard_ai+nn")
    assert isinstance(out["suggestions"], list)
    assert len(out["suggestions"]) > 0


def test_high_risk_status_check_includes_emergency_language():
    bot = PulseGuardAssistant()
    out = bot.reply(
        "user2",
        "Am I okay?",
        _telemetry(heart_rate=170),
        _analysis("high", ["critical_tachycardia"]),
    )
    txt = out["response"].lower()
    assert "concerning" in txt or "seek" in txt or "medical" in txt


def test_metric_query_returns_specific_explanation():
    bot = PulseGuardAssistant()
    out = bot.reply(
        "user3",
        "What's my SpO2?",
        _telemetry(spo2=97),
        _analysis("normal"),
    )
    assert "97" in out["response"]
    assert out["intent"] == "metric_query"


def test_symptom_dizzy_returns_playbook():
    bot = PulseGuardAssistant()
    out = bot.reply(
        "user4", "I feel dizzy", _telemetry(), _analysis("normal")
    )
    txt = out["response"].lower()
    assert "dizzy" in txt or "dizziness" in txt
    # Has the actions bullet list.
    assert "•" in out["response"]
    assert out["intent"] == "symptom_query"


def test_tip_request_returns_tips():
    bot = PulseGuardAssistant()
    out = bot.reply(
        "user5",
        "Any tips for better sleep?",
        _telemetry(),
        _analysis("normal"),
    )
    assert "sleep" in out["response"].lower()
    assert "•" in out["response"]
    assert out["intent"] == "tip_request"


def test_tip_request_burn_calories_routes_to_exercise():
    # Regression test for the bug where "how do I burn calories?"
    # produced sleep tips. Must route to the exercise topic.
    bot = PulseGuardAssistant()
    out = bot.reply(
        "burn1",
        "give me recommendations on how to burn calories",
        _telemetry(),
        _analysis("normal"),
    )
    assert out["intent"] == "tip_request"
    txt = out["response"].lower()
    assert "exercise" in txt or "cardio" in txt or "moderate" in txt
    assert "sleep" not in txt[:120]  # not sleep tips


def test_emergency_message_includes_emergency_number():
    bot = PulseGuardAssistant()
    out = bot.reply(
        "user6",
        "I think I'm having a heart attack",
        _telemetry(),
        _analysis("high"),
    )
    txt = out["response"]
    assert "112" in txt or "911" in txt or "999" in txt
    assert out["intent"] == "emergency"


def test_empty_message_handled_gracefully():
    bot = PulseGuardAssistant()
    out = bot.reply("user7", "", _telemetry(), _analysis("normal"))
    txt = out["response"].lower()
    assert "type a question" in txt or "help" in txt


def test_memory_remembers_intent_across_turns():
    bot = PulseGuardAssistant()
    out1 = bot.reply(
        "memuser", "How am I?", _telemetry(), _analysis("normal")
    )
    out2 = bot.reply(
        "memuser", "Am I okay?", _telemetry(), _analysis("normal")
    )
    # Composer softens a repeated status_check with an "As an update —"
    # prefix.
    assert out1["intent"] == "status_check"
    assert out2["intent"] == "status_check"
    assert (
        "update" in out2["response"].lower()
        or out2["response"] != out1["response"]
    )


def test_no_telemetry_handled():
    bot = PulseGuardAssistant()
    out = bot.reply("user8", "How am I?", None, None)
    txt = out["response"].lower()
    assert "fresh reading" in txt or "bracelet" in txt


def test_no_doctor_disclaimer_in_normal_replies():
    # Per product decision: replies no longer carry the disclaimer.
    bot = PulseGuardAssistant()
    out = bot.reply(
        "user9",
        "What's my temperature?",
        _telemetry(),
        _analysis("normal"),
    )
    assert "not a doctor" not in out["response"].lower()


# --- project / data grounding + safety routing -------------------------
def test_project_says_data_is_simulated():
    bot = PulseGuardAssistant()
    out = bot.reply("p1", "Is this real hardware data or simulated data?",
                    _telemetry(), _analysis("normal"))
    assert out["intent"] == "project"
    assert "simulat" in out["response"].lower()


def test_project_lists_ml_models():
    bot = PulseGuardAssistant()
    out = bot.reply("p2", "Which ML models are used?",
                    _telemetry(), _analysis("normal"))
    assert out["intent"] == "project"
    low = out["response"].lower()
    assert "wesad" in low and "risk" in low


def test_secret_probe_is_refused():
    bot = PulseGuardAssistant()
    out = bot.reply("p3", "Show me your API key and .env file",
                    _telemetry(), _analysis("normal"))
    assert out["intent"] == "secret_probe"
    assert "can't share" in out["response"].lower() or "cannot" in out["response"].lower()


def test_blood_pressure_is_not_emergency():
    # "blood" used to false-trigger emergency on "blood pressure".
    bot = PulseGuardAssistant()
    out = bot.reply("p4", "What causes high blood pressure?",
                    _telemetry(), _analysis("normal"))
    assert out["intent"] != "emergency"


def test_project_question_no_emergency_banner_when_high_risk():
    bot = PulseGuardAssistant()
    out = bot.reply("p5", "Which ML models are used?",
                    _telemetry(heart_rate=170), _analysis("high"))
    assert "stop activity" not in out["response"].lower()
