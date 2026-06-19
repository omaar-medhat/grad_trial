"""Lightweight tests for the medical SLM integration.

These deliberately do NOT load the full Phi-3 model (that needs torch +
transformers and is slow). They only check the adapter files are present and
that the prompt builder produces the expected instruction layout.
"""

from __future__ import annotations

import pytest

from backend.ml.medical_slm import (
    ADAPTER_DIR,
    DegenerateGenerationError,
    _effective_rope_scaling,
    _is_degenerate,
    _is_phi3,
    _normalize_rope_scaling,
    _resolve_base_model,
    build_prompt,
    demo_mode_enabled,
    missing_adapter_files,
    model_label,
    safe_fallback_answer,
)


def test_default_adapter_is_lightweight_folder():
    # The default must be the lightweight adapter, NOT the heavy Phi-3 one
    # (Phi-3 OOMs on a 16 GB machine, so it is opt-in via env override).
    assert ADAPTER_DIR.name == "medical_slm_adapter"


def test_adapter_path_exists():
    assert ADAPTER_DIR.is_dir(), f"adapter folder not found at {ADAPTER_DIR}"


def test_model_label_is_truthful_for_default_adapter():
    # model_label() must report the actually-loaded base, not always Phi-3.
    base = _resolve_base_model(ADAPTER_DIR)
    label = model_label()
    if "phi-3" in base.lower() or "phi3" in base.lower():
        assert label == "phi-3-mini-4k-instruct-lora-medical"
    else:
        # e.g. TinyLlama -> "tinyllama-1.1b-chat-v1.0-lora-medical"
        assert label.endswith("-lora-medical")
        assert "phi-3" not in label


def test_required_adapter_files_exist():
    missing = missing_adapter_files()
    assert missing == [], f"missing adapter files: {missing}"


@pytest.mark.parametrize("context", [None, "", "Patient is 40, non-smoker."])
def test_prompt_builder_has_instruction_sections(context):
    prompt = build_prompt("I have a headache, what should I do?", context)
    # Headers use the colon style the adapter was trained on.
    assert "### Instruction:" in prompt
    assert "### Input:" in prompt
    assert "### Response:" in prompt


def test_prompt_builder_includes_question():
    prompt = build_prompt("why do I feel dizzy when I stand up?")
    assert "dizzy when I stand up" in prompt


def test_rope_scaling_mirrors_rope_type_to_type():
    out = _normalize_rope_scaling({"rope_type": "longrope"})
    assert out["type"] == "longrope"
    assert out["rope_type"] == "longrope"


def test_rope_scaling_mirrors_type_to_rope_type():
    out = _normalize_rope_scaling({"type": "longrope"})
    assert out["type"] == "longrope"
    assert out["rope_type"] == "longrope"


def test_rope_scaling_keeps_both_and_does_not_mutate_original():
    original = {"type": "su", "rope_type": "su", "short_factor": [1.0]}
    out = _normalize_rope_scaling(original)
    assert out["type"] == "su"
    assert out["rope_type"] == "su"
    assert out["short_factor"] == [1.0]
    # The helper must copy, never mutate the caller's dict.
    assert out is not original


def test_rope_scaling_passthrough_for_non_dict():
    assert _normalize_rope_scaling(None) is None


def test_effective_rope_scaling_collapses_default_to_none():
    # The standardized no-scaling value newer transformers injects for the 4k
    # model must become None (else _init_rope raises "Unknown ... default").
    assert _effective_rope_scaling({"rope_type": "default"}) is None
    assert _effective_rope_scaling({"type": "default"}) is None


def test_effective_rope_scaling_keeps_real_phi3_type():
    out = _effective_rope_scaling({"rope_type": "longrope", "short_factor": [1.0]})
    assert out is not None
    assert out["type"] == "longrope"
    assert out["rope_type"] == "longrope"
    assert out["short_factor"] == [1.0]


def test_effective_rope_scaling_none_for_non_dict():
    assert _effective_rope_scaling(None) is None
    assert _effective_rope_scaling("nope") is None


# -----------------------------------------------------------------
# Phi-3 vs TinyLlama gating — the rope/config surgery must NOT be applied
# to TinyLlama (doing so set config.rope_parameters=None and broke loading
# on transformers 5.x with "TypeError: 'NoneType' object is not subscriptable").
# -----------------------------------------------------------------
def test_is_phi3_detection():
    assert _is_phi3("microsoft/Phi-3-mini-4k-instruct") is True
    assert _is_phi3("microsoft/phi3-mini") is True
    assert _is_phi3("TinyLlama/TinyLlama-1.1B-Chat-v1.0") is False
    assert _is_phi3("") is False


def test_default_tinyllama_base_is_not_treated_as_phi3():
    # The default adapter's base must NOT trigger the Phi-3 rope surgery.
    base = _resolve_base_model(ADAPTER_DIR)
    assert _is_phi3(base) is False, base


# -----------------------------------------------------------------
# Safe fallback content.
# -----------------------------------------------------------------
def test_safe_fallback_answer_is_conservative():
    text = safe_fallback_answer().lower()
    assert "not a doctor" in text
    assert "emergency" in text
    assert len(text) > 100


# -----------------------------------------------------------------
# Endpoint behaviour (uses the Flask test client; never loads a real model).
# -----------------------------------------------------------------
def test_endpoint_rejects_empty_question(client):
    r = client.post("/ai/medical-slm", json={"question": "", "context": ""})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "INVALID_INPUT"


def test_endpoint_returns_safe_fallback_on_generation_error(client, monkeypatch):
    # Simulate a model load/generation failure on weak hardware.
    import backend.ml.medical_slm as slm

    def _boom(*a, **k):
        raise RuntimeError("simulated CPU load failure")

    monkeypatch.setattr(slm, "generate_medical_answer", _boom)
    r = client.post("/ai/medical-slm", json={"question": "I feel unwell"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["fallback"] is True
    assert data["model"] == "safe-fallback"
    assert "not a doctor" in data["answer"].lower()


def test_endpoint_returns_503_when_adapter_missing(client, monkeypatch):
    import backend.ml.medical_slm as slm

    def _missing(*a, **k):
        raise FileNotFoundError("adapter files missing")

    monkeypatch.setattr(slm, "generate_medical_answer", _missing)
    r = client.post("/ai/medical-slm", json={"question": "I feel unwell"})
    assert r.status_code == 503
    assert r.get_json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_endpoint_success_path_with_mocked_model(client, monkeypatch):
    import backend.ml.medical_slm as slm

    monkeypatch.setattr(
        slm, "generate_medical_answer", lambda q, c=None: "Rest and hydrate."
    )
    monkeypatch.setattr(
        slm, "model_label", lambda *a, **k: "test-model-lora-medical"
    )
    r = client.post("/ai/medical-slm", json={"question": "sore throat?"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["fallback"] is False
    assert data["demo_mode"] is False
    assert data["answer"] == "Rest and hydrate."
    assert data["model"] == "test-model-lora-medical"


# -----------------------------------------------------------------
# Demo mode — MEDICAL_SLM_DEMO_MODE=true returns the safe fallback instantly
# WITHOUT loading the model (fast + reliable for a live demo).
# -----------------------------------------------------------------
@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE", "On"])
def test_demo_mode_enabled_truthy(monkeypatch, value):
    monkeypatch.setenv("MEDICAL_SLM_DEMO_MODE", value)
    assert demo_mode_enabled() is True


@pytest.mark.parametrize("value", ["", "false", "0", "no", "off"])
def test_demo_mode_disabled_for_falsey(monkeypatch, value):
    monkeypatch.setenv("MEDICAL_SLM_DEMO_MODE", value)
    assert demo_mode_enabled() is False


def test_demo_mode_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("MEDICAL_SLM_DEMO_MODE", raising=False)
    assert demo_mode_enabled() is False


def test_endpoint_demo_mode_returns_fallback_without_loading(client, monkeypatch):
    import backend.ml.medical_slm as slm

    # If the model were touched, this would raise — proving demo mode skips it.
    def _must_not_be_called(*a, **k):
        raise AssertionError("generate_medical_answer must NOT run in demo mode")

    monkeypatch.setenv("MEDICAL_SLM_DEMO_MODE", "true")
    monkeypatch.setattr(slm, "generate_medical_answer", _must_not_be_called)

    r = client.post("/ai/medical-slm", json={"question": "I have a headache"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["demo_mode"] is True
    assert data["fallback"] is True
    assert data["model"] == "safe-fallback"
    assert "not a doctor" in data["answer"].lower()


def test_endpoint_demo_mode_still_rejects_empty_question(client, monkeypatch):
    monkeypatch.setenv("MEDICAL_SLM_DEMO_MODE", "true")
    r = client.post("/ai/medical-slm", json={"question": "", "context": ""})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "INVALID_INPUT"


# -----------------------------------------------------------------
# Degenerate-output detection — repetitive/garbage model text must be hidden
# behind the safe fallback rather than returned to the API caller.
# -----------------------------------------------------------------
@pytest.mark.parametrize("bad", [
    "",
    "   ",
    "Rome Rome Rome Rome Rome",
    "Rome Rome Rome Rome Rome Rome Rome Rome",
    "the the the the the the the the the the",
    ".....  ---- ;;;; ....",
    "ok ok ok ok ok ok ok done",
])
def test_is_degenerate_flags_bad_output(bad):
    assert _is_degenerate(bad) is True


@pytest.mark.parametrize("good", [
    "Rest, stay hydrated, and monitor your symptoms. If the fever lasts more "
    "than a few days or you have trouble breathing, please see a doctor.",
    "A sore throat and mild fever are often caused by a viral infection. Drink "
    "fluids, rest, and consider over-the-counter pain relief. See a doctor if "
    "symptoms worsen.",
    "This could be a common cold. Monitor for high fever or difficulty "
    "breathing and seek care if they appear.",
])
def test_is_degenerate_passes_normal_answers(good):
    assert _is_degenerate(good) is False


def test_endpoint_degenerate_output_returns_safe_fallback(client, monkeypatch):
    import backend.ml.medical_slm as slm

    def _degenerate(*a, **k):
        raise slm.DegenerateGenerationError("degenerate_generation")

    monkeypatch.delenv("MEDICAL_SLM_DEMO_MODE", raising=False)
    monkeypatch.setattr(slm, "generate_medical_answer", _degenerate)
    r = client.post("/ai/medical-slm", json={"question": "I feel unwell"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["fallback"] is True
    assert data["model"] == "safe-fallback"
    assert "not a doctor" in data["answer"].lower()


def test_degenerate_error_is_runtime_error_subclass():
    # So the endpoint's generic failure handling also covers it if needed.
    assert issubclass(DegenerateGenerationError, RuntimeError)
