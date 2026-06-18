"""
PulseGuard AI - Telemetry simulator.

Produces realistic synthetic health readings for demo / load-test purposes.
Distributions are loosely derived from public physiological references
(MIMIC-III / WHO resting ranges). The simulator deliberately injects
occasional anomalies so the rule engine and dashboard have something to react
to during a defense demo.

Usage (as a module):
    from backend.simulator import generate_reading
    reading = generate_reading()

Usage (as a CLI, sends readings to the backend at a steady cadence):
    python -m backend.simulator --uid demo-user-001 --interval 2 --count 60
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from typing import Dict

# Scenario probabilities — adjust if you want more frequent anomalies for demo.
SCENARIOS = [
    ("resting",        0.55, dict(hr=(72, 8),  spo2=(97, 1.2), temp=(36.7, 0.3),  act=(15, 10))),
    ("light_walk",     0.18, dict(hr=(95, 10), spo2=(96, 1.5), temp=(36.9, 0.3),  act=(55, 15))),
    ("moderate_run",   0.08, dict(hr=(130,12), spo2=(95, 2.0), temp=(37.4, 0.4),  act=(75, 10))),
    ("sleep",          0.08, dict(hr=(58, 5),  spo2=(96, 1.0), temp=(36.4, 0.2),  act=(2, 2))),
    ("mild_fever",     0.05, dict(hr=(95, 10), spo2=(95, 2.0), temp=(38.1, 0.3),  act=(10, 8))),
    ("stress",         0.03, dict(hr=(105,12), spo2=(96, 1.5), temp=(36.9, 0.3),  act=(8, 5))),
    ("high_fever",     0.015,dict(hr=(115,12), spo2=(93, 2.5), temp=(39.0, 0.4),  act=(5, 4))),
    ("hypoxia",        0.012,dict(hr=(110,15), spo2=(88, 2.5), temp=(37.0, 0.3),  act=(20,15))),
    ("bradycardia",    0.003,dict(hr=(45, 4),  spo2=(95, 2.0), temp=(36.5, 0.3),  act=(10, 8))),
]


_SCENARIO_BY_NAME = {name: params for name, _p, params in SCENARIOS}

# Friendly demo "modes" (plan §25) → internal scenario name. The simulator
# already models these physiologies; this just lets the caller *pick* one
# instead of relying on the random weighting.
MODE_TO_SCENARIO = {
    "resting": "resting",
    "walking": "light_walk",
    "running": "moderate_run",
    "sleep": "sleep",
    "fever": "mild_fever",
    "high_fever": "high_fever",
    "stress": "stress",
}
# Modes that aren't a single scenario.
_ANOMALY_SCENARIOS = ["hypoxia", "bradycardia", "high_fever"]
# Public, ordered list for the API / UI (low_battery + anomaly are special).
AVAILABLE_MODES = [
    "resting", "walking", "running", "sleep",
    "fever", "high_fever", "stress", "anomaly", "low_battery",
]


def _gauss(mean: float, std: float) -> float:
    return random.gauss(mean, std)


def _pick_scenario() -> Dict:
    r = random.random()
    acc = 0.0
    for name, p, params in SCENARIOS:
        acc += p
        if r <= acc:
            return {"name": name, **params}
    return {"name": SCENARIOS[0][0], **SCENARIOS[0][2]}


def _scenario_for_mode(mode: str) -> Dict:
    """Resolve a demo mode to a concrete scenario dict (raises on unknown)."""
    if mode == "anomaly":
        name = random.choice(_ANOMALY_SCENARIOS)
        return {"name": name, **_SCENARIO_BY_NAME[name]}
    if mode == "low_battery":
        # Normal vitals — the point is the battery, forced low below.
        return {"name": "resting", **_SCENARIO_BY_NAME["resting"]}
    scenario = MODE_TO_SCENARIO.get(mode)
    if scenario is None:
        raise ValueError(
            f"Unknown simulator mode '{mode}'. "
            f"Valid modes: {', '.join(AVAILABLE_MODES)}"
        )
    return {"name": scenario, **_SCENARIO_BY_NAME[scenario]}


# Per-process running counters so demo dashboards see steps/calories grow.
# `battery` slowly drains from full and recharges once it hits the floor, so a
# long-running demo eventually exercises the low-battery device alert.
_state = {"steps": 0, "calories": 0.0, "sleep_sec": 7 * 3600, "battery": 100.0}


def generate_reading(mode: "str | None" = None) -> Dict:
    """Generate one synthetic reading.

    ``mode`` (optional) forces a demo scenario from ``AVAILABLE_MODES``; when
    omitted, a scenario is drawn from the weighted random distribution.
    """
    s = _scenario_for_mode(mode) if mode else _pick_scenario()
    hr = max(35, min(220, _gauss(*s["hr"])))
    spo2 = max(70, min(100, _gauss(*s["spo2"])))
    temp = max(34.0, min(42.0, _gauss(*s["temp"])))
    act = max(0, min(100, _gauss(*s["act"])))

    # Accumulate activity-driven counters.
    if act > 30:
        _state["steps"] += int(act * 0.1)
        _state["calories"] += act * 0.02
    else:
        _state["steps"] += random.randint(0, 1)
        _state["calories"] += random.random() * 0.1

    # Drain the battery a touch each reading; recharge once it bottoms out so a
    # long demo loops through the low/critical battery alerts.
    _state["battery"] -= random.uniform(0.1, 0.4)
    if _state["battery"] <= 2:
        _state["battery"] = 100.0
    # The low_battery mode forces a depleted cell regardless of drain state.
    battery = random.randint(3, 18) if mode == "low_battery" else int(round(_state["battery"]))

    return {
        "heart_rate": round(hr, 1),
        "spo2": round(spo2, 1),
        "temperature_c": round(temp, 2),
        "steps": _state["steps"],
        "calories": round(_state["calories"], 2),
        "sleep_duration_sec": _state["sleep_sec"],
        "battery_level": battery,
        "activity_level": int(round(act)),
        "source": "simulator",
        "scenario": s["name"],            # debug-only field; backend ignores unknowns
        "timestamp": int(time.time() * 1000),
    }


# ---------------------------------------------------------------------------
# CLI: pump readings into the backend
# ---------------------------------------------------------------------------
def _send(api_base: str, uid: str, reading: Dict) -> int:
    try:
        import urllib.error
        import urllib.request
        import json

        body = dict(reading)
        body["user_id"] = uid
        req = urllib.request.Request(
            f"{api_base.rstrip('/')}/api/telemetry",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
        return exc.code
    except Exception as exc:  # noqa: BLE001
        print(f"  -> network error: {exc}", file=sys.stderr)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PulseGuard AI telemetry simulator")
    parser.add_argument("--api", default=os.environ.get("PULSE_API", "http://127.0.0.1:5000"))
    parser.add_argument("--uid", default=os.environ.get("PULSE_UID", "demo-user-001"))
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between readings")
    parser.add_argument("--count", type=int, default=0, help="0 = run forever")
    parser.add_argument(
        "--mode", default=None,
        help=f"force a scenario ({', '.join(AVAILABLE_MODES)}); default random",
    )
    args = parser.parse_args()

    print(f"Simulator → {args.api} as uid={args.uid} every {args.interval}s")
    i = 0
    try:
        while True:
            reading = generate_reading(args.mode)
            status = _send(args.api, args.uid, reading)
            print(
                f"[{i:>4}] {reading['scenario']:<14} "
                f"HR={reading['heart_rate']:>5} SpO2={reading['spo2']:>4} "
                f"T={reading['temperature_c']:>4}°C  -> {status}"
            )
            i += 1
            if args.count and i >= args.count:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
