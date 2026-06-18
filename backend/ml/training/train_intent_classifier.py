"""
Train the IntentClassifier for the chatbot NLU.

Pipeline:
  TF-IDF (word 1–2-grams + char 2–4-grams, lowercased) → MLP(64→32) → Softmax

We use a LabelEncoder + a custom wrapper that exposes the underlying class
labels via `classes_` so downstream inference code is unchanged.
"""

from __future__ import annotations

import json
import os
import time

import joblib
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import LabelEncoder

from .generate_dataset import generate_intent_dataset
from ..registry import MODELS_DIR


class StringLabelMLP(BaseEstimator, ClassifierMixin):
    """Wraps MLPClassifier so it can train on string labels safely under
    sklearn 1.8 + numpy 2.x (which rejects np.isnan on string arrays during
    early-stopping validation)."""

    def __init__(self, **mlp_kwargs):
        self.mlp_kwargs = mlp_kwargs

    def fit(self, X, y):
        self._encoder = LabelEncoder().fit(y)
        y_int = self._encoder.transform(y)
        self._mlp = MLPClassifier(**self.mlp_kwargs)
        self._mlp.fit(X, y_int)
        self.classes_ = self._encoder.classes_
        self.n_iter_ = self._mlp.n_iter_
        self.loss_curve_ = self._mlp.loss_curve_
        return self

    def predict(self, X):
        return self._encoder.inverse_transform(self._mlp.predict(X))

    def predict_proba(self, X):
        return self._mlp.predict_proba(X)


def main(seed: int = 13) -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)

    print("[intent] Generating intent training data...")
    X, y = generate_intent_dataset(seed=seed)
    print(f"[intent]   dataset: {len(X)} examples across {len(set(y))} intents")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, stratify=y, random_state=seed
    )

    features = FeatureUnion([
        ("word", TfidfVectorizer(
            lowercase=True, ngram_range=(1, 2), min_df=1, max_df=0.95,
            sublinear_tf=True,
        )),
        ("char", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4),
            lowercase=True, min_df=1, max_df=0.95,
            sublinear_tf=True,
        )),
    ])

    pipeline = Pipeline([
        ("features", features),
        ("mlp", StringLabelMLP(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            solver="adam",
            alpha=1e-4,
            batch_size=64,
            learning_rate_init=1e-3,
            max_iter=400,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
            random_state=seed,
            verbose=False,
        )),
    ])

    print("[intent] Training TF-IDF + MLP(64→32)...")
    t0 = time.time()
    pipeline.fit(X_train, y_train)
    train_seconds = time.time() - t0

    print(f"[intent] Evaluating on {len(X_test)} held-out examples...")
    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    # Pipeline.classes_ proxies the final step's classes_ automatically.
    model_path = os.path.join(MODELS_DIR, "intent_classifier.joblib")
    joblib.dump(pipeline, model_path)
    metrics = {
        "model": "IntentClassifier",
        "architecture": "TF-IDF (word 1-2 + char 2-4) + MLP(64-32) + softmax",
        "intents": sorted(set(y)),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "test_accuracy": round(float(acc), 4),
        "per_class": report,
        "train_seconds": round(train_seconds, 2),
        "n_iterations": int(pipeline.named_steps["mlp"].n_iter_),
        "loss_curve_final": float(pipeline.named_steps["mlp"].loss_curve_[-1]),
    }
    with open(os.path.join(MODELS_DIR, "intent_classifier_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"[intent] ✓ saved -> {model_path}")
    print(f"[intent] ✓ test accuracy = {acc:.4f}  (trained in {train_seconds:.1f}s, {pipeline.named_steps['mlp'].n_iter_} epochs)")
    return metrics


if __name__ == "__main__":
    main()
