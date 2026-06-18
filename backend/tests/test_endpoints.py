"""End-to-end tests for the Flask backend (in-memory Firebase fallback)."""

from __future__ import annotations

import json


def _valid_payload(**overrides):
    base = {
        "heart_rate": 72, "spo2": 97, "temperature_c": 36.8,
        "steps": 1200, "calories": 45.5, "sleep_duration_sec": 25200,
        "timestamp": 1779716107821, "user_id": "test-user",
    }
    base.update(overrides)
    return base


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"
    assert "version" in body["data"]
    assert body["data"]["services"]["firebase"] in (
        "admin_sdk", "rest", "memory", "admin_error",
    )
    assert "firebase_mode" in body["data"]
    assert "firebase_read_ok" in body["data"]
    assert "firebase_error" in body["data"]


def test_metrics_endpoint(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["data"]["requests_total"] >= 1


def test_post_telemetry_valid(client):
    r = client.post("/api/telemetry", json=_valid_payload())
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["data"]["analysis"]["risk_level"] == "normal"
    # latest endpoint should now return it
    r2 = client.get("/api/latest?uid=test-user")
    assert r2.status_code == 200
    latest = r2.get_json()["data"]
    assert latest["heart_rate"] == 72
    assert latest["temperature_c"] == 36.8


def test_post_telemetry_invalid_input(client):
    r = client.post("/api/telemetry", json=_valid_payload(heart_rate=500))
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_INPUT"


def test_post_telemetry_missing_field(client):
    payload = _valid_payload()
    del payload["spo2"]
    r = client.post("/api/telemetry", json=payload)
    assert r.status_code == 400
    assert "spo2" in r.get_json()["error"]["message"].lower()


def test_high_risk_creates_alert(client):
    r = client.post("/api/telemetry", json=_valid_payload(
        user_id="alert-user", heart_rate=160, spo2=88, temperature_c=39.2
    ))
    assert r.status_code == 200
    assert r.get_json()["data"]["analysis"]["risk_level"] == "high"

    # New Firebase-backed /api/alerts: current vs historical, deterministic.
    body = client.get("/api/alerts?uid=alert-user").get_json()["data"]
    assert body["has_current_critical"] is True
    assert any(a["severity"] in ("high", "critical") for a in body["current"])


def test_history_returns_inserts(client):
    for hr in (70, 72, 74):
        client.post("/api/telemetry", json=_valid_payload(user_id="hist-user", heart_rate=hr))
    r = client.get("/api/history?uid=hist-user&limit=10")
    assert r.status_code == 200
    history = r.get_json()["data"]
    assert len(history) >= 3
    assert all("timestamp" in h for h in history)


def test_low_battery_creates_device_alert(client):
    r = client.post("/api/telemetry", json=_valid_payload(
        user_id="batt-user", battery_level=4,
    ))
    assert r.status_code == 200
    # Vitals are fine — only the battery alert should fire on the vitals side.
    assert r.get_json()["data"]["analysis"]["risk_level"] == "normal"

    body = client.get("/api/alerts?uid=batt-user").get_json()["data"]
    assert any(a["type"] == "low_battery" for a in body["current"])


def test_healthy_battery_raises_no_low_battery_alert(client):
    import time
    client.post("/api/telemetry", json=_valid_payload(
        user_id="batt97", battery_level=97, timestamp=int(time.time() * 1000),
    ))
    body = client.get("/api/alerts?uid=batt97").get_json()["data"]
    # No CURRENT low-battery alert should exist for a 97% reading.
    assert not any(a["type"] == "low_battery" for a in body["current"])
    # And the normalized latest reflects the healthy battery.
    v = client.get("/api/vitals/latest?uid=batt97").get_json()["data"]
    assert v["battery_level"] == 97


def test_simulate_endpoint(client):
    r = client.post("/api/simulate", json={"user_id": "sim-user"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "telemetry" in body["data"]
    assert "analysis" in body["data"]


def test_simulate_modes_listed(client):
    r = client.get("/api/simulate/modes")
    assert r.status_code == 200
    modes = r.get_json()["data"]["modes"]
    assert "low_battery" in modes and "resting" in modes


def test_simulate_with_mode(client):
    r = client.post("/api/simulate", json={"user_id": "mode-user", "mode": "running"})
    assert r.status_code == 200
    t = r.get_json()["data"]["telemetry"]
    assert t["source"] == "simulator"
    assert "wellness_score" in t


def test_simulate_low_battery_mode_triggers_device_alert(client):
    client.post(
        "/api/simulate",
        json={"user_id": "lowbatt-sim", "mode": "low_battery"},
    )
    body = client.get("/api/alerts?uid=lowbatt-sim").get_json()["data"]
    assert any(a["type"] == "low_battery" for a in body["current"])


def test_simulate_invalid_mode_rejected(client):
    r = client.post("/api/simulate", json={"mode": "teleport"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "INVALID_INPUT"


def test_reports_daily_summarizes_history(client):
    import time
    now = int(time.time() * 1000)
    for hr in (70, 80, 90):
        client.post("/api/telemetry", json=_valid_payload(
            user_id="rep-user", heart_rate=hr, timestamp=now,
        ))
    r = client.get("/api/reports/daily?uid=rep-user")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["available"] is True
    assert data["period"] == "daily"
    assert data["count"] >= 3
    assert data["source"] == "firebase"
    assert data["heart_rate"]["min"] <= 70 <= data["heart_rate"]["max"]
    assert "diagnosis" in data["disclaimer"]  # safety wording present


def test_reports_weekly_empty_user(client):
    r = client.get("/api/reports/weekly?uid=nobody-here")
    assert r.status_code == 200
    assert r.get_json()["data"]["count"] == 0


def test_reports_export_csv(client):
    client.post("/api/telemetry", json=_valid_payload(user_id="csv-user"))
    r = client.get("/api/reports/export.csv?uid=csv-user")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv")
    body = r.get_data(as_text=True)
    assert body.splitlines()[0].startswith("timestamp,heart_rate")
    assert "csv-user" in r.headers["Content-Disposition"]


def test_predict_stress_endpoint(client):
    from backend.ml import get_models
    stress = get_models().stress
    if stress.status != "trained":
        r = client.post("/api/ml/predict/stress", json={"vector": [0.0]})
        assert r.status_code == 503
        assert r.get_json()["error"]["code"] == "MODEL_UNAVAILABLE"
        return
    # Post a full-length WESAD feature vector.
    r = client.post("/api/ml/predict/stress", json={
        "vector": [0.0] * len(stress.feature_names),
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()["data"]
    assert d["prediction"] in stress.label_mapping.values()  # prediction
    assert d["prediction_id"]                                 # prediction_id
    assert 0.0 <= d["confidence"] <= 1.0                      # confidence
    assert isinstance(d["probabilities"], dict)              # probabilities
    assert d["model_name"]                                    # model_name


def test_predict_stress_rejects_bad_input(client):
    from backend.ml import get_models
    if get_models().stress.status != "trained":
        return
    r = client.post("/api/ml/predict/stress", json={"vector": [0.0, 1.0]})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "INVALID_INPUT"


def _chat(client, message, uid="chat-user", telemetry=None):
    body = {"message": message, "user_id": uid}
    if telemetry is not None:
        body["telemetry"] = telemetry
    return client.post("/api/chat", json=body).get_json()["data"]


def _live(**over):
    base = {
        "heart_rate": 83, "spo2": 97, "temperature_c": 36.8,
        "steps": 4200, "battery_level": 91, "activity_level": 12,
        "wellness_score": 85, "activity": "running",
        "stress_label": "non_stress", "stress_score": 4,
        "risk_level": "high", "source": "simulator",
        "timestamp": 1779716107821,
    }
    base.update(over)
    return base


def test_chat_uses_client_live_vitals_for_current_hr(client):
    # The HR in the answer must match the vitals the UI sent (not a stale store).
    d = _chat(client, "what is my heart rate right now", telemetry=_live(heart_rate=83))
    assert "83" in d["response"]
    assert "98" not in d["response"]


def test_chat_typo_write_now_is_understood(client):
    d = _chat(client, "what is my heart rate write now", telemetry=_live(heart_rate=83))
    assert "83" in d["response"]


def test_chat_discloses_simulated_source(client):
    d = _chat(client, "what is my heart rate right now", telemetry=_live(heart_rate=83))
    assert "simulator" in d["response"].lower()


def test_chat_no_vitals_clear_fallback(client):
    # Fresh uid, no stored data and no telemetry sent → graceful fallback.
    d = _chat(client, "what is my heart rate right now", uid="no-vitals-user")
    assert "don't have a current" in d["response"].lower()


def test_chat_repeated_prompt_uses_latest_not_cached(client):
    first = _chat(client, "current heart rate", telemetry=_live(heart_rate=83))
    second = _chat(client, "current heart rate", telemetry=_live(heart_rate=61))
    assert "83" in first["response"]
    assert "61" in second["response"]


def test_chat_spo2_matches_live(client):
    d = _chat(client, "what is my oxygen level right now", telemetry=_live(spo2=94))
    assert "94" in d["response"]


def test_chat_temperature_typo_matches_live(client):
    d = _chat(client, "what is my temprature right now", telemetry=_live(temperature_c=37.4))
    assert "37.4" in d["response"]


def test_chat_oxegen_typo_understood(client):
    d = _chat(client, "what is my oxegen right now", telemetry=_live(spo2=96))
    assert "96" in d["response"]


def test_chat_battery_matches_live(client):
    d = _chat(client, "what is my battery right now", telemetry=_live(battery_level=42))
    assert "42" in d["response"]


def test_chat_activity_matches_live(client):
    d = _chat(client, "what is my activity right now", telemetry=_live(activity="walking"))
    assert "walking" in d["response"].lower()


def test_chat_stress_matches_model(client):
    d = _chat(client, "what is my stress right now",
              telemetry=_live(stress_label="stressed", stress_score=72))
    assert "stressed" in d["response"].lower()


def test_chat_risk_matches_dashboard_value(client):
    d = _chat(client, "what is my risk level right now", telemetry=_live(risk_level="high"))
    assert "high" in d["response"].lower()


def test_chat_summarize_uses_live_values(client):
    d = _chat(client, "summarize my current vitals",
              telemetry=_live(heart_rate=77, spo2=98, battery_level=63))
    r = d["response"]
    assert "77" in r and "98" in r and "63" in r
    assert "simulator" in r.lower()


def test_vitals_latest_normalized_contract(client):
    import time
    now = int(time.time() * 1000)
    client.post("/api/telemetry", json=_valid_payload(
        user_id="norm-user", heart_rate=88, spo2=96, temperature_c=37.1,
        battery_level=55, activity_level=70, source="simulator", timestamp=now,
    ))
    d = client.get("/api/vitals/latest?uid=norm-user").get_json()["data"]
    assert d["available"] is True
    # ONE Firebase-backed normalized contract: sensor + model-derived +
    # device-status fields.
    for k in ("heart_rate", "spo2", "temperature_c", "steps", "activity",
              "battery_level", "source", "is_simulated", "wellness_score",
              "risk_level", "stress_label", "anomaly_status", "timestamp",
              "device_status", "last_seen_seconds"):
        assert k in d, f"missing {k}"
    assert d["heart_rate"] == 88
    # Read FROM Firebase → labelled firebase, not simulated, fresh now.
    assert d["source"] == "firebase"
    assert d["is_simulated"] is False
    assert d["device_status"] == "connected"


def test_vitals_latest_no_data_is_unavailable(client):
    d = client.get("/api/vitals/latest?uid=ghost-user").get_json()["data"]
    assert d["available"] is False
    assert d["source"] == "firebase"
    assert d["is_simulated"] is False


def test_chat_reports_telemetry_origin_client_live(client):
    d = _chat(client, "what is my heart rate right now", telemetry=_live(heart_rate=83))
    assert d["telemetry_origin"] == "client_live"
    assert d["telemetry_source"] == "simulator"


def test_chat_telemetry_origin_none_when_no_data(client):
    d = _chat(client, "what is my heart rate right now", uid="origin-none-user")
    assert d["telemetry_origin"] == "none"


def test_unknown_route_returns_envelope(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_request_id_header_present(client):
    r = client.get("/health")
    assert "X-Request-ID" in r.headers
