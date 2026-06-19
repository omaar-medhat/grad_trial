
import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

try:
    import tensorflow as tf
except Exception:
    tf = None


def get_positive_proba(model, X_data):
    if not hasattr(model, "predict_proba"):
        return None

    proba = model.predict_proba(X_data)
    proba = np.asarray(proba)

    if proba.ndim == 1:
        return proba

    if proba.ndim == 2 and proba.shape[1] == 1:
        return proba[:, 0]

    if proba.ndim == 2 and proba.shape[1] >= 2:
        return proba[:, 1]

    return None


class LoadedKerasWithPreprocessor:
    def __init__(self, keras_model, imputer, scaler):
        self.keras_model = keras_model
        self.imputer = imputer
        self.scaler = scaler
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X):
        X_imp = self.imputer.transform(X)
        X_scaled = self.scaler.transform(X_imp)

        p1 = self.keras_model.predict(X_scaled, verbose=0).reshape(-1)
        p1 = np.clip(p1, 0.0, 1.0)

        return np.vstack([1.0 - p1, p1]).T

    def predict(self, X):
        p1 = self.predict_proba(X)[:, 1]
        return (p1 >= 0.5).astype(int)


class LoadedSoftVoting:
    def __init__(self, estimators):
        self.estimators = estimators
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X):
        probs = []

        for name, model in self.estimators:
            p1 = get_positive_proba(model, X)

            if p1 is not None:
                probs.append(np.asarray(p1).reshape(-1))

        if len(probs) == 0:
            raise RuntimeError("No model produced probabilities.")

        p1_mean = np.mean(np.vstack(probs), axis=0)
        p1_mean = np.clip(p1_mean, 0.0, 1.0)

        return np.vstack([1.0 - p1_mean, p1_mean]).T

    def predict(self, X):
        p1 = self.predict_proba(X)[:, 1]
        return (p1 >= 0.5).astype(int)


def load_model_from_spec(spec, package_dir):
    package_dir = Path(package_dir)

    if spec["type"] == "joblib_model":
        return joblib.load(package_dir / spec["model_path"])

    if spec["type"] == "keras_with_preprocessor":
        if tf is None:
            raise RuntimeError("TensorFlow is required to load this Keras model.")

        keras_model = tf.keras.models.load_model(
            package_dir / spec["keras_model_path"],
            compile=False
        )

        prep = joblib.load(package_dir / spec["preprocessor_path"])

        return LoadedKerasWithPreprocessor(
            keras_model=keras_model,
            imputer=prep["imputer"],
            scaler=prep["scaler"]
        )

    if spec["type"] == "soft_voting":
        members = []

        for member in spec["members"]:
            member_model = load_model_from_spec(
                member["spec"],
                package_dir
            )

            members.append((member["name"], member_model))

        return LoadedSoftVoting(members)

    raise ValueError("Unknown model spec type: " + str(spec["type"]))


class WESADStressPredictor:
    def __init__(self, package_dir):
        self.package_dir = Path(package_dir)

        with open(self.package_dir / "metadata.json", "r") as f:
            self.metadata = json.load(f)

        with open(self.package_dir / "feature_names.json", "r") as f:
            self.feature_names = json.load(f)

        with open(self.package_dir / "models" / "model_spec.json", "r") as f:
            self.model_spec = json.load(f)

        self.model = load_model_from_spec(
            self.model_spec,
            self.package_dir
        )

        self.threshold = float(self.metadata["best_threshold"])
        self.label_mapping = self.metadata["label_mapping"]
        self.model_name = self.metadata["best_model_name"]

    def predict_from_features(self, features):
        row = pd.DataFrame([features])
        row = row.reindex(columns=self.feature_names, fill_value=0.0)
        row = row.replace([np.inf, -np.inf], np.nan)

        p1 = get_positive_proba(self.model, row)

        if p1 is not None:
            stress_probability = float(np.asarray(p1).reshape(-1)[0])
            stress_probability = float(np.clip(stress_probability, 0.0, 1.0))

            pred_id = int(stress_probability >= self.threshold)

            return {
                "prediction": self.label_mapping[str(pred_id)],
                "prediction_id": pred_id,
                "stress_probability": stress_probability,
                "non_stress_probability": float(1.0 - stress_probability),
                "confidence": float(max(stress_probability, 1.0 - stress_probability)),
                "threshold": self.threshold,
                "model_name": self.model_name
            }

        pred_raw = self.model.predict(row)
        pred_id = int(np.asarray(pred_raw).reshape(-1)[0])

        return {
            "prediction": self.label_mapping[str(pred_id)],
            "prediction_id": pred_id,
            "stress_probability": None,
            "non_stress_probability": None,
            "confidence": None,
            "threshold": self.threshold,
            "model_name": self.model_name
        }

    def predict_from_json(self, json_path):
        with open(json_path, "r") as f:
            features = json.load(f)

        return self.predict_from_features(features)

    def predict_from_csv_row(self, csv_path, row_index=0):
        df = pd.read_csv(csv_path)
        features = df.iloc[row_index].to_dict()

        return self.predict_from_features(features)
