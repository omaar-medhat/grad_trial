"""
Train the Risk Classifier MLP.

Architecture:
  Input (6 features) → StandardScaler → MLP(64 → 32 → 16, ReLU) → Softmax(3)

Loss: cross-entropy. Optimizer: Adam. Early stopping with 10% validation
split, patience 10. ~60k samples, trains in ~10–20 seconds on CPU.

Run:
  python -m backend.ml.training.train_risk_classifier
"""

from __future__ import annotations

import json
import os
import time

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .generate_dataset import generate_telemetry_dataset
from ..registry import MODELS_DIR


def main(n_samples: int = 60_000, seed: int = 42) -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"[risk] Generating dataset of {n_samples} samples...")
    X, y, features, classes = generate_telemetry_dataset(n=n_samples, seed=seed)
    print(f"[risk]   dataset: {X.shape}, class distribution: {np.bincount(y).tolist()}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, stratify=y, random_state=seed
    )

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("mlp", MLPClassifier(
            hidden_layer_sizes=(64, 32, 16),
            activation="relu",
            solver="adam",
            alpha=1e-4,
            batch_size=256,
            learning_rate_init=1e-3,
            max_iter=200,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=10,
            random_state=seed,
            verbose=False,
        )),
    ])

    print("[risk] Training MLP(64→32→16) on", X_train.shape[0], "samples...")
    t0 = time.time()
    pipeline.fit(X_train, y_train)
    train_seconds = time.time() - t0

    print(f"[risk] Evaluating on hold-out test set ({X_test.shape[0]} samples)...")
    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=classes, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred).tolist()

    # Save model + metrics
    model_path = os.path.join(MODELS_DIR, "risk_classifier.joblib")
    joblib.dump(pipeline, model_path)
    metrics = {
        "model": "RiskClassifier",
        "architecture": "StandardScaler + MLP(64-32-16, ReLU) + softmax(3)",
        "features": features,
        "classes": classes,
        "training_samples": int(X_train.shape[0]),
        "test_samples": int(X_test.shape[0]),
        "test_accuracy": round(float(acc), 4),
        "per_class": report,
        "confusion_matrix": cm,
        "train_seconds": round(train_seconds, 2),
        "n_iterations": int(pipeline.named_steps["mlp"].n_iter_),
        "loss_curve_final": float(pipeline.named_steps["mlp"].loss_curve_[-1]),
    }
    with open(os.path.join(MODELS_DIR, "risk_classifier_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"[risk] ✓ saved -> {model_path}")
    print(f"[risk] ✓ test accuracy = {acc:.4f}  (trained in {train_seconds:.1f}s, {pipeline.named_steps['mlp'].n_iter_} epochs)")
    return metrics


if __name__ == "__main__":
    main()
