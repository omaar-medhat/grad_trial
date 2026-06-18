# PulseGuard AI — Bracelet Firmware (reference)

This folder is the **hardware bridge** for PulseGuard AI: a reference firmware
that turns the sensors from the project plan into the exact JSON telemetry the
existing backend already accepts. With it flashed, a physical bracelet becomes a
drop-in replacement for the Python/in-browser simulators.

> **Wellness / educational prototype — not a medical device.** Heart-rate and
> SpO₂ maths derived from the MAX30102 must be validated against a reference
> pulse oximeter before any real-world reliance. See the FDA General Wellness
> guidance referenced in the project brief.

## What it does

1. Reads the sensors over I²C (MAX30102 PPG, MAX30205 skin temp, LSM6DSOX IMU)
   and a LiPo battery level via an ADC divider.
2. Summarizes them into one reading every `POST_INTERVAL_MS` (raw PPG is **not**
   streamed — that's the power-saving choice from the plan's Step 10).
3. `POST`s the reading to the backend `/api/telemetry`, using the same schema
   documented in [../docs/api.md](../docs/api.md):

   ```json
   {
     "user_id": "demo-user-001",
     "heart_rate": 78,
     "spo2": 97,
     "temperature_c": 36.6,
     "steps": 1240,
     "battery_level": 82,
     "timestamp": 1781356800000
   }
   ```

The backend validates, runs the rule engine + ML, persists to Firebase, and
raises alerts — including the **low-battery device alert** — with no changes.

## Two MCU paths (from the plan)

| Path | MCU | Transport | Use |
|---|---|---|---|
| **This sketch** (WiFi + REST) | ESP32-C3 | HTTP `POST` to backend | Fastest demo; works with the whole stack today |
| BLE peripheral | nRF52840 | GATT (HRS + Battery + custom) | Closer to a real wearable; phone reads vitals over BLE |

The BLE GATT layout (standard Heart Rate + Battery services plus a custom
PulseGuard service) is specified in [../docs/ble_spec.md](../docs/ble_spec.md).
A phone can verify it with nRF Connect / LightBlue before any app work.

## Build & flash (PlatformIO)

```bash
# 1. Put real values in src/config.h (WiFi + your machine's LAN IP).
# 2. Start the backend on your machine:  python -m backend.app
pio run               # compile
pio run -t upload     # flash over USB
pio device monitor    # watch the [post] lines and HTTP status codes
```

Then open the web dashboard — the new reading (and a Battery card) appears live.

## Wiring & power

See [../docs/hardware.md](../docs/hardware.md) for the bill of materials, the
I²C address map, the battery-divider math behind `config.h`, and enclosure /
PCB notes.
