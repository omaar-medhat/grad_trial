"""
Train + compare Activity Recognition models on the UCI HAR dataset.

This is the plan's "Model 1: Activity Recognition" — trained on a REAL public
wearable dataset (UCI Human Activity Recognition Using Smartphones), not
synthetic data. It downloads the dataset, trains several algorithms on the
official train split, evaluates them on the official test split, writes a
model-comparison table, and saves the best model.

Dataset: https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones
  561 engineered features from a waist-worn accelerometer + gyroscope,
  6 activities: WALKING, WALKING_UPSTAIRS, WALKING_DOWNSTAIRS, SITTING,
  STANDING, LAYING.

Run:
  python -m backend.ml.training.train_activity_classifier

Note on live serving: the model consumes 561 IMU-derived features, so it
activates once the bracelet streams raw accelerometer/gyroscope windows
(BLE motion characteristic — see docs/ble_spec.md). Until the hardware
provides that stream, the dashboard shows the deterministic activity label
from backend/anomaly_detection.classify_activity. This script proves the
recognition pipeline on real data and is ready to wire in.
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.request
import zipfile

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from ..registry import MODELS_DIR

DATA_URL = (
    "https://archive.ics.uci.edu/static/public/240/"
    "human+activity+recognition+using+smartphones.zip"
)
DATASET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets"
)
HAR_ROOT = os.path.join(DATASET_DIR, "UCI HAR Dataset")


# ---------------------------------------------------------------------------
# Data loading (download + extract, cached)
# ---------------------------------------------------------------------------
def _ensure_dataset() -> str:
    """Download + extract UCI HAR (handles the nested-zip layout). Cached."""
    if os.path.exists(os.path.join(HAR_ROOT, "train", "X_train.txt")):
        return HAR_ROOT
    os.makedirs(DATASET_DIR, exist_ok=True)
    print(f"[activity] downloading UCI HAR from {DATA_URL} ...")
    raw = urllib.request.urlopen(DATA_URL, timeout=600).read()
    outer = zipfile.ZipFile(io.BytesIO(raw))
    # The outer archive contains a nested "UCI HAR Dataset.zip".
    nested_name = next(
        (n for n in outer.namelist() if n.endswith(".zip")), None
    )
    if nested_name:
        inner = zipfile.ZipFile(io.BytesIO(outer.read(nested_name)))
        inner.extractall(DATASET_DIR)
    else:
        outer.extractall(DATASET_DIR)
    if not os.path.exists(os.path.join(HAR_ROOT, "train", "X_train.txt")):
        raise FileNotFoundError(
            "UCI HAR layout unexpected after extraction; check " + DATASET_DIR
        )
    print(f"[activity] dataset ready at {HAR_ROOT}")
    return HAR_ROOT


def _load_split(root: str):
    def _read(path):
        return np.loadtxt(path)

    X_train = _read(os.path.join(root, "train", "X_train.txt"))
    y_train = _read(os.path.join(root, "train", "y_train.txt")).astype(int)
    X_test = _read(os.path.join(root, "test", "X_test.txt"))
    y_test = _read(os.path.join(root, "test", "y_test.txt")).astype(int)
    labels = {}
    with open(os.path.join(root, "activity_labels.txt"), encoding="utf-8") as f:
        for line in f:
            idx, name = line.strip().split(" ", 1)
            labels[int(idx)] = name
    classes = [labels[i] for i in sorted(labels)]
    return X_train, y_train, X_test, y_test, classes


# ---------------------------------------------------------------------------
# Training + comparison
# ---------------------------------------------------------------------------
def _candidates(seed: int):
    """The algorithms to compare (plan: LogReg, RF, SVM, KNN, MLP)."""
    return {
        "logistic_regression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, C=1.0, random_state=seed)),
        ]),
        "random_forest": Pipeline([
            ("clf", RandomForestClassifier(
                n_estimators=200, n_jobs=-1, random_state=seed)),
        ]),
        "linear_svm": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LinearSVC(C=1.0, random_state=seed)),
        ]),
        "knn": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", KNeighborsClassifier(n_neighbors=15)),
        ]),
        "mlp": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", MLPClassifier(
                hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
                alpha=1e-4, max_iter=300, early_stopping=True,
                n_iter_no_change=10, random_state=seed)),
        ]),
    }


def main(seed: int = 42) -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)
    root = _ensure_dataset()
    X_train, y_train, X_test, y_test, classes = _load_split(root)
    print(
        f"[activity] train={X_train.shape} test={X_test.shape} "
        f"classes={len(classes)}"
    )

    comparison = []
    fitted = {}
    for name, model in _candidates(seed).items():
        t0 = time.time()
        model.fit(X_train, y_train)
        secs = time.time() - t0
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        macro_f1 = f1_score(y_test, y_pred, average="macro")
        fitted[name] = model
        comparison.append({
            "model": name,
            "accuracy": round(float(acc), 4),
            "macro_f1": round(float(macro_f1), 4),
            "train_seconds": round(secs, 2),
        })
        print(f"[activity]   {name:<20} acc={acc:.4f} f1={macro_f1:.4f} ({secs:.1f}s)")

    comparison.sort(key=lambda r: r["macro_f1"], reverse=True)
    best_name = comparison[0]["model"]
    best = fitted[best_name]
    print(f"[activity] best = {best_name} (macro-F1 {comparison[0]['macro_f1']})")

    y_pred = best.predict(X_test)
    report = classification_report(
        y_test, y_pred, target_names=classes, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_test, y_pred).tolist()

    model_path = os.path.join(MODELS_DIR, "activity_classifier.joblib")
    joblib.dump(best, model_path)
    metrics = {
        "model": "ActivityClassifier",
        "dataset": "UCI HAR (Human Activity Recognition Using Smartphones)",
        "dataset_url": (
            "https://archive.ics.uci.edu/dataset/240/"
            "human+activity+recognition+using+smartphones"
        ),
        "n_features": int(X_train.shape[1]),
        "classes": classes,
        "training_samples": int(X_train.shape[0]),
        "test_samples": int(X_test.shape[0]),
        "best_model": best_name,
        "test_accuracy": comparison[0]["accuracy"],
        "test_macro_f1": comparison[0]["macro_f1"],
        "comparison": comparison,
        "per_class": report,
        "confusion_matrix": cm,
        "serving_note": (
            "Consumes 561 IMU features; activates with the bracelet's raw "
            "accel/gyro stream (BLE motion characteristic). Until then the "
            "deterministic classify_activity label is shown."
        ),
    }
    with open(
        os.path.join(MODELS_DIR, "activity_classifier_metrics.json"),
        "w", encoding="utf-8",
    ) as f:
        json.dump(metrics, f, indent=2)

    print(f"[activity] saved -> {model_path}")
    print(f"[activity] test accuracy = {comparison[0]['accuracy']}")
    return metrics


if __name__ == "__main__":
    main()
