"""Tests for the WESAD VS Code model package integration.

These exercise the new package-backed `predict_stress()` API. The heavy model
(DeepDNN + tensorflow) is only loaded when the package and its runtime deps are
present, so the suite is skipped cleanly on a minimal install.
"""

from __future__ import annotations

import json

import pytest

from backend.ml.stress_classifier import (
    WESAD_PACKAGE_DIR,
    missing_package_files,
    predict_stress,
)

PACKAGE_EXISTS = WESAD_PACKAGE_DIR.is_dir() and not missing_package_files()


def test_package_folder_exists():
    assert WESAD_PACKAGE_DIR.is_dir(), (
        f"WESAD package folder not found at {WESAD_PACKAGE_DIR}"
    )


def test_sample_input_exists():
    sample = WESAD_PACKAGE_DIR / "sample_input.json"
    assert sample.exists(), f"sample_input.json missing under {WESAD_PACKAGE_DIR}"


def _runtime_available() -> bool:
    """True only if both the package files and tensorflow are importable."""
    if not PACKAGE_EXISTS:
        return False
    try:
        import tensorflow  # noqa: F401
    except Exception:
        return False
    return True


needs_runtime = pytest.mark.skipif(
    not _runtime_available(),
    reason="WESAD package or its runtime (tensorflow) is not installed.",
)


@needs_runtime
def test_predict_stress_returns_expected_dict():
    sample = WESAD_PACKAGE_DIR / "sample_input.json"
    with open(sample, "r", encoding="utf-8") as f:
        sample_input = json.load(f)

    result = predict_stress(sample_input)

    assert isinstance(result, dict)
    for key in ("prediction", "prediction_id", "threshold", "model_name"):
        assert key in result, f"missing key: {key}"
