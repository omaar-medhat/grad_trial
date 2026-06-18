"""
PulseGuard ML — real trained neural networks used in production.

Three models, all trained from scratch on synthetic-but-realistic data,
saved to disk, and loaded by the Flask backend at startup:

  * Risk Classifier      — MLP, predicts normal/warning/high from vitals
  * Anomaly Autoencoder  — bottleneck MLP, flags telemetry deviations
  * Intent Classifier    — TF-IDF + MLP, replaces regex NLU in the chatbot

Public API:
  from backend.ml import get_models
  models = get_models()
  models.risk.predict(vitals_dict)
  models.anomaly.score(vitals_dict)
  models.intent.predict(message)
"""

from .registry import get_models, MODELS_DIR

__all__ = ["get_models", "MODELS_DIR"]
