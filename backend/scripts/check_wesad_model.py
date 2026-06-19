"""
Quick verification for the WESAD VS Code model package.

Loads the package's bundled `sample_input.json`, runs a prediction through
`predict_stress()` and prints the result. Exits 0 on success and raises a
clear error if loading or prediction fails.

Run it from the backend/ folder:

    cd backend && python scripts/check_wesad_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make `ml` importable whether this is run as `python scripts/check_wesad_model.py`
# from backend/, or from anywhere else.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ml.stress_classifier import (  # noqa: E402
    WESAD_PACKAGE_DIR,
    missing_package_files,
    predict_stress,
)


def main() -> int:
    print(f"WESAD package dir: {WESAD_PACKAGE_DIR}")

    missing = missing_package_files()
    if missing:
        raise FileNotFoundError(
            "WESAD model package is incomplete — missing: "
            + ", ".join(missing)
        )

    sample_path = WESAD_PACKAGE_DIR / "sample_input.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        sample_features = json.load(f)
    print(f"Loaded {len(sample_features)} sample features from {sample_path.name}")

    print("Running predict_stress() ...")
    result = predict_stress(sample_features)

    if not isinstance(result, dict):
        raise RuntimeError(
            f"predict_stress returned {type(result).__name__}, expected dict."
        )
    for key in ("prediction", "prediction_id", "threshold", "model_name"):
        if key not in result:
            raise RuntimeError(f"Prediction result is missing key: {key!r}")

    print("Prediction result:")
    print(json.dumps(result, indent=2))
    print("OK — WESAD model package loaded and predicted successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
