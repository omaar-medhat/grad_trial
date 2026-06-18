"""
Synthetic dataset generator for the PulseGuard ML models.

Samples are drawn from clinically-grounded distributions (means and standard
deviations loosely derived from MIMIC-III / WHO / AHA published values),
then labeled by the same rule engine the backend uses in production. This
is **knowledge distillation** — we're teaching a small neural network the
behaviour of the expert rules, with the bonus that the network generalises
smoothly between rule boundaries and gives a calibrated probability.

Public API:
  generate_telemetry_dataset(n=60_000, seed=42)
      → (X: np.ndarray, y: np.ndarray, feature_names: list, class_names: list)
"""

from __future__ import annotations

import random
from typing import List, Tuple

import numpy as np

from ...anomaly_detection import analyze, validate_telemetry, TelemetryValidationError

FEATURES = [
    "heart_rate",
    "spo2",
    "temperature_c",
    "steps",
    "calories",
    "sleep_duration_sec",
]
CLASSES = ["normal", "warning", "high"]
LABEL_TO_IDX = {c: i for i, c in enumerate(CLASSES)}


# Clinical-ish scenarios used to draw realistic samples. Each scenario gives
# a (mean, std) tuple per feature.
SCENARIOS = [
    # name,           hr_mean,std,  spo2,std,  temp,std,  steps,std,    cal,std,  sleep,std
    ("resting",       (72, 10),   (97, 1.5),  (36.6, 0.3),  (3500, 1800),  (250, 100),  (25200, 3600)),
    ("light_walk",    (95, 12),   (96, 1.8),  (36.9, 0.3),  (7500, 2200),  (380, 120),  (25200, 3600)),
    ("workout",       (135, 18),  (95, 2.0),  (37.3, 0.4),  (4800, 2400),  (520, 180),  (25200, 3600)),
    ("sleep",         (58, 6),    (96, 1.0),  (36.4, 0.2),  (200, 200),    (40, 30),    (28800, 3600)),
    ("mild_fever",    (95, 12),   (95, 2.0),  (38.1, 0.3),  (1000, 800),   (120, 80),   (25200, 3600)),
    ("high_fever",    (115, 14),  (93, 2.5),  (39.2, 0.4),  (500, 500),    (60, 50),    (25200, 3600)),
    ("hypoxia",       (110, 16),  (88, 3.0),  (37.0, 0.3),  (1500, 1200),  (180, 100),  (25200, 3600)),
    ("stress",        (108, 13),  (96, 1.5),  (36.9, 0.3),  (800, 600),    (90, 60),    (18000, 3600)),
    ("bradycardia",   (48, 5),    (95, 2.0),  (36.5, 0.3),  (1500, 1200),  (180, 100),  (25200, 3600)),
    ("tachycardia",   (148, 14),  (92, 3.0),  (37.0, 0.4),  (500, 400),    (60, 40),    (18000, 3600)),
    ("dehydrated",    (98, 11),   (96, 1.5),  (37.4, 0.3),  (2000, 1500),  (200, 100),  (21600, 3600)),
]


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _draw_sample(rng: random.Random) -> dict:
    scenario = rng.choice(SCENARIOS)
    _, hr, spo2, temp, steps, cal, sleep = scenario
    return {
        "heart_rate": _clip(rng.gauss(*hr), 30, 230),
        "spo2": _clip(rng.gauss(*spo2), 60, 100),
        "temperature_c": _clip(rng.gauss(*temp), 33, 42),
        "steps": int(_clip(rng.gauss(*steps), 0, 100_000)),
        "calories": _clip(rng.gauss(*cal), 0, 5_000),
        "sleep_duration_sec": int(_clip(rng.gauss(*sleep), 0, 60_000)),
        "timestamp": 0,
    }


def generate_telemetry_dataset(n: int = 60_000, seed: int = 42) -> Tuple[np.ndarray, np.ndarray, List[str], List[str]]:
    """Draw n labeled samples. Labels come from the production rule engine."""
    rng = random.Random(seed)
    X: List[List[float]] = []
    y: List[int] = []
    for _ in range(n):
        s = _draw_sample(rng)
        try:
            clean = validate_telemetry(s)
            analysis = analyze(clean)
        except TelemetryValidationError:
            continue
        X.append([clean[f] for f in FEATURES])
        y.append(LABEL_TO_IDX[analysis["risk_level"]])
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int64), FEATURES, CLASSES


def generate_healthy_only_dataset(n: int = 20_000, seed: int = 7) -> np.ndarray:
    """Draw n samples drawn ONLY from resting/walk/sleep scenarios. Used as
    the training set for the autoencoder so it learns what 'healthy' looks
    like; anomalies are detected as samples it cannot reconstruct well.
    """
    rng = random.Random(seed)
    healthy = [s for s in SCENARIOS if s[0] in {"resting", "light_walk", "sleep"}]
    out = []
    for _ in range(n):
        sc = rng.choice(healthy)
        _, hr, spo2, temp, steps, cal, sleep = sc
        out.append([
            _clip(rng.gauss(*hr), 50, 110),
            _clip(rng.gauss(*spo2), 92, 100),
            _clip(rng.gauss(*temp), 35.8, 37.5),
            int(_clip(rng.gauss(*steps), 0, 30_000)),
            _clip(rng.gauss(*cal), 0, 1_500),
            int(_clip(rng.gauss(*sleep), 0, 40_000)),
        ])
    return np.asarray(out, dtype=np.float32)


# ----------------------------------------------------------------------
# Intent dataset for the chatbot NLU. We hand-author seeds per intent and
# augment with simple paraphrases so the trained classifier can generalise.
# ----------------------------------------------------------------------
INTENT_SEEDS = {
    "status_check": [
        "how am i", "am i okay", "am i ok", "is everything fine",
        "what is my status", "how am i doing", "are my vitals ok",
        "is everything normal", "am i healthy", "how are my readings",
        "do i look healthy", "is anything wrong", "give me my status",
    ],
    "metric_query": [
        "what is my heart rate", "what's my pulse", "tell me my hr",
        "what is my spo2", "what is my oxygen", "what's my blood oxygen",
        "what is my temperature", "what's my temp", "do i have a fever",
        "how many steps today", "how many calories", "how much did i sleep",
        "show me my heart rate", "tell me my temperature",
    ],
    "compare_query": [
        "is my heart rate normal", "is my hr high",
        "is my temperature normal", "is my spo2 healthy",
        "is my oxygen low", "is this a good heart rate",
        "is my pulse elevated", "is my temp ok",
    ],
    "symptom_query": [
        "i feel dizzy", "i'm dizzy", "i feel lightheaded",
        "i have a headache", "my head hurts",
        "i feel tired", "i'm exhausted", "no energy",
        "i feel nauseous", "i want to throw up",
        "i'm short of breath", "i cant breathe well",
        "i feel anxious", "i'm panicking", "i'm stressed",
        "i feel hot", "i'm shivering", "i have chills",
        "my chest hurts", "i have chest pain",
    ],
    "tip_request": [
        "tips for better sleep", "how do i sleep better",
        "tips to lower stress", "how to relax",
        "tips for hydration", "how to drink more water",
        "how to lower heart rate", "tips for heart health",
        "exercise tips", "diet tips", "any advice for me",
        "what should i do for stress", "how can i improve my health",
    ],
    "history_query": [
        "how was i earlier", "what was my heart rate yesterday",
        "show me my trend", "how was my day",
        "how was my sleep last night", "what about earlier today",
    ],
    "general_health": [
        "what is a normal heart rate", "what is a healthy spo2",
        "what is normal body temperature", "how many steps a day",
        "how much sleep do i need", "how much water should i drink",
        "what causes high heart rate", "what is hypoxia",
    ],
    "emergency": [
        "i think i'm having a heart attack",
        "call 911", "call an ambulance",
        "i'm dying", "i can't breathe", "i'm passing out",
        "emergency", "i need help right now",
    ],
    "greeting": [
        "hi", "hello", "hey", "good morning", "good evening",
        "good afternoon", "hey there", "hi there",
    ],
    "thanks": [
        "thanks", "thank you", "thx", "appreciate it", "cheers",
    ],
    "smalltalk": [
        "how's it going", "what's up", "you there",
        "nice to meet you",
    ],
    "meta": [
        "what can you do", "who are you", "are you a doctor",
        "are you an ai", "how do you work", "what is pulseguard",
        "are you real",
    ],
    "fallback": [
        "asdf", "lorem ipsum", "blah", "qwerty",
        "i don't know", "nothing", "random text",
    ],
}


def generate_intent_dataset(seed: int = 13) -> Tuple[List[str], List[str]]:
    rng = random.Random(seed)
    X: List[str] = []
    y: List[str] = []
    for intent, seeds in INTENT_SEEDS.items():
        for s in seeds:
            X.append(s)
            y.append(intent)
            # Augment with simple variants.
            for prefix in ("hey ", "please ", "", "ok ", "so "):
                if rng.random() < 0.4:
                    X.append(prefix + s)
                    y.append(intent)
            for suffix in ("?", "!", " please", " right now", " for me"):
                if rng.random() < 0.4:
                    X.append(s + suffix)
                    y.append(intent)
    return X, y
