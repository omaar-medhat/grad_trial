"""
Lightweight backend environment check.

Run it after creating the gp-backend (Python 3.11) environment:

    cd backend && python scripts/check_environment.py

It reports the Python version + interpreter path, warns if you are not on
Python 3.11, and checks that the required and optional backend packages import.
Exit code is non-zero only when a REQUIRED package is missing, so it is safe to
use in CI / setup scripts.

It never downloads models and never imports the heavy AI stack eagerly beyond a
plain `import` (which is enough to confirm the package is installed).
"""

from __future__ import annotations

import importlib
import sys
import warnings

# (import name, pip/display name). Required = base requirements.txt deps.
REQUIRED_PACKAGES = [
    ("flask", "Flask"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("sklearn", "scikit-learn"),
    ("joblib", "joblib"),
]

# Optional = requirements-ai.txt (WESAD DeepDNN + medical SLM). Missing ones
# are reported but do NOT fail the check — install them only when you need
# the heavy models.
OPTIONAL_PACKAGES = [
    ("tensorflow", "tensorflow (WESAD DeepDNN)"),
    ("torch", "torch (medical SLM)"),
    ("transformers", "transformers (medical SLM)"),
    ("peft", "peft (medical SLM)"),
]

TARGET_PY = (3, 11)


def _try_import(module: str) -> str | None:
    """Return a version string if importable, else None."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mod = importlib.import_module(module)
            return getattr(mod, "__version__", "unknown")
    except Exception:
        return None


def main() -> int:
    print("=" * 60)
    print("Backend environment check")
    print("=" * 60)

    v = sys.version_info
    print(f"Python version : {v.major}.{v.minor}.{v.micro}")
    print(f"Executable     : {sys.executable}")

    ok = True

    target_str = f"{TARGET_PY[0]}.{TARGET_PY[1]}"
    if (v.major, v.minor) != TARGET_PY:
        print(
            f"\n[WARN] This backend targets Python {target_str}."
            f" You are on {v.major}.{v.minor}."
        )
        print(
            "       Python 3.13/base often fails to build pydantic-core from "
            "source on Windows. See backend/SETUP_WINDOWS.md to create the "
            "'gp-backend' (Python 3.11) conda environment."
        )

    print("\nRequired packages (base requirements.txt):")
    missing_required = []
    for module, name in REQUIRED_PACKAGES:
        ver = _try_import(module)
        if ver is None:
            missing_required.append(name)
            print(f"  [MISSING] {name}")
        else:
            print(f"  [ok]      {name} ({ver})")

    print("\nOptional packages (requirements-ai.txt — heavy models):")
    missing_optional = []
    for module, name in OPTIONAL_PACKAGES:
        ver = _try_import(module)
        if ver is None:
            missing_optional.append(name)
            print(f"  [absent]  {name}")
        else:
            print(f"  [ok]      {name} ({ver})")

    print("\n" + "-" * 60)
    if missing_required:
        ok = False
        print(
            "[FAIL] Missing required packages: "
            + ", ".join(missing_required)
        )
        print("       Run:  python -m pip install -r requirements.txt")
    else:
        print("[OK]   All required backend packages are importable.")

    if missing_optional:
        print(
            "[INFO] Optional AI packages not installed: "
            + ", ".join(missing_optional)
        )
        print(
            "       Install when needed:  python -m pip install "
            "-r requirements-ai.txt"
        )

    print("-" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
