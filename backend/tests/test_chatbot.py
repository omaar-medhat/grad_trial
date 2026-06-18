"""Chatbot endpoint tests — primary path is PulseGuardAssistant."""

from __future__ import annotations


def test_chat_returns_safe_reply_with_no_telemetry(client):
    r = client.post(
        "/api/chat",
        json={"message": "Am I okay?", "user_id": "chat-noctx"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    response = body["data"]["response"]
    assert isinstance(response, str)
    assert body["data"]["source"] in (
        "pulseguard_ai", "pulseguard_ai+nn",
    )
    assert body["data"]["intent"] in (
        "status_check", "meta", "fallback",
    )


def test_chat_uses_latest_telemetry_when_available(client):
    client.post("/api/telemetry", json={
        "user_id": "chat-user",
        "heart_rate": 80, "spo2": 97, "temperature_c": 36.9,
        "steps": 100, "calories": 12,
        "sleep_duration_sec": 25200, "timestamp": 1779716107821,
    })
    r = client.post(
        "/api/chat",
        json={"message": "How am I doing?", "user_id": "chat-user"},
    )
    assert r.status_code == 200
    response = r.get_json()["data"]["response"].lower()
    assert any(
        word in response
        for word in ("normal", "healthy", "good", "bpm")
    )


def test_chat_high_risk_emergency_language(client):
    client.post("/api/telemetry", json={
        "user_id": "chat-high",
        "heart_rate": 160, "spo2": 86, "temperature_c": 39.5,
        "steps": 0, "calories": 0,
        "sleep_duration_sec": 0, "timestamp": 1779716107822,
    })
    r = client.post(
        "/api/chat",
        json={"message": "Is everything fine?", "user_id": "chat-high"},
    )
    response = r.get_json()["data"]["response"].lower()
    assert any(
        t in response
        for t in ("seek", "help", "medical", "stop", "concerning")
    )


def test_chat_empty_message_handled(client):
    r = client.post(
        "/api/chat",
        json={"message": "", "user_id": "chat-empty"},
    )
    assert r.status_code == 200
    response = r.get_json()["data"]["response"].lower()
    assert any(
        t in response for t in ("type a question", "help", "ask")
    )


def test_chat_returns_suggestions(client):
    r = client.post(
        "/api/chat",
        json={"message": "Am I okay?", "user_id": "chat-sugg"},
    )
    body = r.get_json()
    assert isinstance(body["data"]["suggestions"], list)
    assert len(body["data"]["suggestions"]) > 0


def test_chat_intent_is_classified(client):
    r = client.post(
        "/api/chat",
        json={
            "message": "any tips for sleep?",
            "user_id": "chat-intent",
        },
    )
    assert r.get_json()["data"]["intent"] == "tip_request"


def test_chat_symptom_returns_playbook(client):
    r = client.post(
        "/api/chat",
        json={"message": "I feel dizzy", "user_id": "chat-sym"},
    )
    response = r.get_json()["data"]["response"].lower()
    assert "dizz" in response


def test_chat_repeated_text_collapsed():
    from backend.chatbot_service import _clean_text
    cleaned = _clean_text("please help help help help help me")
    assert cleaned.count("help") <= 2


def test_chat_no_doctor_disclaimer_in_reply(client):
    # Per product decision: chat replies no longer carry the doctor
    # disclaimer (the UI surfaces the safety hint elsewhere).
    r = client.post(
        "/api/chat",
        json={"message": "Am I okay?", "user_id": "no-discl"},
    )
    body = r.get_json()
    assert "not a doctor" not in body["data"]["response"].lower()


def test_chat_safety_high_risk_prepends_emergency():
    from backend.chatbot_service import _apply_safety
    safe = _apply_safety(
        "Your readings vary.",
        analysis={"risk_level": "high"},
    )
    assert (
        "seek" in safe.lower()
        or "emergency" in safe.lower()
        or "stop" in safe.lower()
    )


def test_legacy_chat_route_still_works(client):
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
