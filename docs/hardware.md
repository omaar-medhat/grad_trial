# Hardware — PulseGuard AI Bracelet

The bill of materials, wiring, and power notes for the physical bracelet. The
software stack (backend, web, mobile, ML) works today against simulators; this
document plus [../firmware/](../firmware/) and [ble_spec.md](./ble_spec.md) are
the path to a real device.

> Wellness / educational prototype — not a medical device.

## Bill of materials

| Function | Part | Interface | Notes |
|---|---|---|---|
| MCU (demo, low-cost) | **ESP32-C3** | — | WiFi+BLE; runs the reference firmware |
| MCU (wearable-grade) | **Nordic nRF52840** | — | Best BLE/low-power; use nRF Connect SDK / Zephyr |
| Heart rate + SpO₂ | **MAX30102** | I²C `0x57` | Optical PPG; keep against the skin |
| Skin temperature | **MAX30205** | I²C `0x48` | Human body-temp range, 0.1 °C |
| Motion / steps / fall | **LSM6DSOX** | I²C `0x6A` | 6-axis IMU; HW step counter + tap/free-fall |
| Battery charger | **MCP73831** (simple) / **BQ24074** (power-path) | — | LiPo charging |
| Haptic alerts | **DRV2605** + LRA/ERM motor | I²C `0x5A` | Vibration on alerts |
| Battery | LiPo ~100–250 mAh | — | Sized to enclosure |

## I²C bus map

All sensors share one I²C bus (SDA/SCL + pull-ups). Addresses are distinct, so
no multiplexer is needed:

```
ESP32-C3  SDA ─┬─ MAX30102 (0x57)
          SCL ─┼─ MAX30205 (0x48)
               ├─ LSM6DSOX (0x6A)
               └─ DRV2605  (0x5A)
```

Battery sense is **analog**: LiPo+ → resistor divider → `BATTERY_ADC_PIN`.

## Battery divider math (matches `firmware/src/config.h`)

A 4.2 V full LiPo exceeds the ESP32's safe ADC input, so halve it:

```
R1 = R2  →  BATTERY_DIVIDER = (R1 + R2) / R2 = 2.0
v_batt  = adc_volts * BATTERY_DIVIDER
percent = (v_batt - BATTERY_EMPTY_V) / (BATTERY_FULL_V - BATTERY_EMPTY_V) * 100
```

Calibrate `BATTERY_FULL_V` / `BATTERY_EMPTY_V` to your cell. The firmware clamps
to 0–100 and the backend treats ≤20 % as a low-battery alert, ≤5 % as critical
(`BATTERY_LOW` / `BATTERY_CRIT` in `backend/anomaly_detection.py`).

## Power optimization (plan Step 10)

- MCU sleeps between sampling windows; wake on timer/IMU interrupt.
- Reduce MAX30102 LED drive current.
- Transmit **summaries** (BPM/SpO₂/temp/battery), never raw PPG.
- Prefer BLE notifications; widen connection interval when idle.

## Enclosure (plan Step 8)

- Optical window holds the MAX30102 flush against the wrist (skin contact is the
  #1 signal-quality factor).
- Room for PCB + LiPo; no sharp edges; comfortable strap.
- Magnetic pogo-pin or USB charging; access to programming/test pads.

## PCB (plan Step 9)

- Keep the MAX30102 on the skin-facing side, away from noisy power traces.
- Test pads for I²C (SDA/SCL), 3V3, GND, and RESET.
- Don't shrink the first revision — leave room to probe and rework.
- Deliverables: schematic, layout, Gerbers (KiCad).

## Bring-up order (de-risks debugging)

1. Power + charger (verify 3V3 rail, safe charge).
2. I²C scan — confirm `0x48 / 0x57 / 0x5A / 0x6A` all ACK.
3. Each sensor alone over serial (temp, then IMU, then PPG).
4. Battery ADC reading vs. a multimeter; tune the divider constants.
5. Flash [../firmware/](../firmware/), confirm `/api/telemetry` returns `200`.
6. Watch the reading + Battery card appear on the dashboard.
