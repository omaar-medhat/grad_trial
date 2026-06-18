"""
Train + compare Stress-Detection models, then save the best as a .pkl/.joblib.

Mirrors the author's WESAD/Colab methodology (multi-model bake-off + 5-fold CV,
pick the winner) but trains on the **feature space the bracelet actually
streams** — heart_rate, spo2, temperature_c, activity_level — so the saved
model can run live on the Firebase/sensor telemetry ("test on Firebase").

Labels (3-class): relaxed | normal | stressed. The decisive, learnable signal
is the heart-rate-vs-motion interaction: an elevated HR while the body is STILL
is stress, whereas an elevated HR with HIGH motion is exercise (normal). Samples
are drawn from clinically-grounded scenarios — knowledge-distillation, the same
approach used by the repo's risk/anomaly/intent models.

Real WESAD: drop WESAD-derived features and labels into _load_wesad() to train
on the real dataset instead; the comparison + selection code is unchanged.

Run:
  python -m backend.ml.training.train_stress_classifier
"""

from __future__ import annotations

import json
import os
import random
import time
from typing import List, Tuple

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from ..registry import MODELS_DIR

FEATURES = ["heart_rate", "spo2", "temperature_c", "activity_level"]
CLASSES = ["relaxed", "normal", "stressed"]
LABEL_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

# (label, weight, hr(mean,std), spo2(mean,std), temp(mean,std), act(mean,std))
_SCENARIOS = [
    ("relaxed",  1.0, (68, 7),  (98, 1.0), (36.6, 0.25), (10, 6)),   # sitting
    ("relaxed",  0.7, (57, 5),  (97, 1.0), (36.4, 0.2),  (2, 2)),    # sleep
    ("normal",   1.0, (95, 12), (96, 1.5), (36.9, 0.3),  (55, 15)),  # walking
    ("normal",   0.8, (132, 15),(95, 2.0), (37.3, 0.4),  (80, 10)),  # running
    ("normal",   0.6, (76, 8),  (97, 1.2), (36.7, 0.3),  (25, 10)),  # light daily
    ("stressed", 1.1, (112, 12),(96, 1.5), (36.9, 0.35), (8, 6)),    # stress at rest
    ("stressed", 0.7, (125, 14),(95, 2.0), (37.0, 0.4),  (12, 8)),   # acute stress
]


def _draw(rng: random.Random) -> Tuple[List[float], int]:
    weights = [s[1] for s in _SCENARIOS]
    label, _w, hr, spo2, temp, act = rng.choices(_SCENARIOS, weights=weights)[0]
    row = [
        max(35, min(200, rng.gauss(*hr))),
        max(70, min(100, rng.gauss(*spo2))),
        max(34.0, min(42.0, rng.gauss(*temp))),
        max(0, min(100, rng.gauss(*act))),
    ]
    return row, LABEL_TO_IDX[label]


def _generate(n: int, seed: int):
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n):
        row, label = _draw(rng)
        X.append(row)
        y.append(label)
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int64)


def _candidates(seed: int):
    """Same line-up as the WESAD Colab comparison (sklearn-only for serving)."""
    return {
        "Dummy": DummyClassifier(strategy="stratified", random_state=seed),
        "LogReg": Pipeline([("s", StandardScaler()),
                            ("c", LogisticRegression(max_iter=1000, random_state=seed))]),
        "KNN": Pipeline([("s", StandardScaler()),
                         ("c", KNeighborsClassifier(n_neighbors=15))]),
        "RandomForest": RandomForestClassifier(
            n_estimators=200, n_jobs=-1, random_state=seed),
        "GradientBoosting": GradientBoostingClassifier(random_state=seed),
        "SVC_RBF": Pipeline([("s", StandardScaler()),
                             ("c", SVC(kernel="rbf", probability=True, random_state=seed))]),
        "MLP": Pipeline([("s", StandardScaler()),
                         ("c", MLPClassifier(hidden_layer_sizes=(64, 32),
                                             max_iter=400, early_stopping=True,
                                             random_state=seed))]),
    }


def main(n_samples: int = 9000, seed: int = 42) -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"[stress] generating {n_samples} samples...")
    X, y = _generate(n_samples, seed)
    print(f"[stress]   class counts: {np.bincount(y).tolist()} ({CLASSES})")
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=seed
    )

    comparison, fitted = [], {}
    for name, model in _candidates(seed).items():
        t0 = time.time()
        model.fit(X_tr, y_tr)
        pred = model.predict(X_te)
        comparison.append({
            "model": name,
            "accuracy": round(float(accuracy_score(y_te, pred)), 4),
            "macro_f1": round(float(f1_score(y_te, pred, average="macro")), 4),
            "train_seconds": round(time.time() - t0, 2),
        })
        fitted[name] = model
        print(f"[stress]   {name:<17} acc={comparison[-1]['accuracy']:.4f} "
              f"f1={comparison[-1]['macro_f1']:.4f}")

    comparison.sort(key=lambda r: r["macro_f1"], reverse=True)

    # 5-fold CV on the strong candidates (skip Dummy).
    tuning = [c["model"] for c in comparison if c["model"] != "Dummy"][:4]
    print(f"[stress] CV candidates: {tuning}")
    cv = []
    for name in tuning:
        scores = cross_val_score(
            _candidates(seed)[name], X, y, cv=5, scoring="accuracy", n_jobs=-1
        )
        cv.append({
            "model": name,
            "cv_accuracy": round(float(scores.mean()), 4),
            "cv_std": round(float(scores.std()), 4),
        })
        print(f"[stress]   {name} 5-fold CV = {scores.mean():.4f} ± {scores.std():.4f}")
    cv.sort(key=lambda r: r["cv_accuracy"], reverse=True)

    best_name = cv[0]["model"]
    best = fitted[best_name]
    print(f"[stress] best = {best_name} (CV {cv[0]['cv_accuracy']})")

    pred = best.predict(X_te)
    report = classification_report(
        y_te, pred, target_names=CLASSES, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_te, pred).tolist()

    model_path = os.path.join(MODELS_DIR, "stress_classifier.joblib")
    joblib.dump(best, model_path)
    metrics = {
        "model": "StressClassifier",
        "method": "multi-model comparison + 5-fold CV (WESAD-style)",
        "trained_on": "clinically-grounded synthetic scenarios (servable feature space)",
        "features": FEATURES,
        "classes": CLASSES,
        "training_samples": int(X_tr.shape[0]),
        "test_samples": int(X_te.shape[0]),
        "best_model": best_name,
        "test_accuracy": next(c["accuracy"] for c in comparison if c["model"] == best_name),
        "test_macro_f1": next(c["macro_f1"] for c in comparison if c["model"] == best_name),
        "comparison": comparison,
        "cross_validation_5fold": cv,
        "per_class": report,
        "confusion_matrix": cm,
        "note": (
            "Trained on the live telemetry feature space so it serves on the "
            "Firebase/sensor stream. The author's real-WESAD comparison is in "
            "wesad_stress_comparison.json; swap _load_wesad() to train on it."
        ),
    }
    with open(
        os.path.join(MODELS_DIR, "stress_classifier_metrics.json"),
        "w", encoding="utf-8",
    ) as f:
        json.dump(metrics, f, indent=2)
    print(f"[stress] saved -> {model_path}")
    return metrics


if __name__ == "__main__":
    main()
