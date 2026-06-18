# BLE Specification — PulseGuard AI Bracelet

This is the Bluetooth Low Energy contract for the bracelet (project plan
Step 4). It reuses **adopted Bluetooth SIG services** where they exist and adds
one **custom service** for the data the standard profiles don't cover. A phone
running [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile)
or [LightBlue](https://punchthrough.com/lightblue/) should be able to discover
and read everything below before any mobile-app work begins.

> Wellness / educational prototype — not a medical device.

## Advertising

- **Device name:** `PulseGuard`
- **Advertised service UUID:** Heart Rate Service `0x180D` (lets generic BLE
  health apps find it) plus the custom service UUID below in the scan response.

## Standard services

### Heart Rate Service — `0x180D`
| Characteristic | UUID | Props | Notes |
|---|---|---|---|
| Heart Rate Measurement | `0x2A37` | Notify | Byte 0 flags, byte 1 = BPM (uint8) |
| Body Sensor Location | `0x2A38` | Read | `0x02` = wrist |

### Battery Service — `0x180F`
| Characteristic | UUID | Props | Notes |
|---|---|---|---|
| Battery Level | `0x2A19` | Read / Notify | uint8 percent, 0–100 |

### Health Thermometer Service — `0x1809`
| Characteristic | UUID | Props | Notes |
|---|---|---|---|
| Temperature Measurement | `0x2A1C` | Indicate | IEEE-11073 FLOAT, °C |

## Custom service — PulseGuard

For SpO₂, motion/steps, fall flag and a single consolidated JSON reading that
mirrors the REST contract.

- **Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`

| Characteristic | UUID | Props | Format |
|---|---|---|---|
| SpO₂ | `6e400002-…` | Notify | uint8 percent, 50–100 |
| Steps | `6e400003-…` | Read / Notify | uint32 LE |
| Motion / activity | `6e400004-…` | Notify | uint8 enum: `0`=still `1`=walking `2`=running `3`=fall |
| Reading (JSON) | `6e400005-…` | Notify | UTF-8 JSON, ≤180 bytes (see below) |

### Consolidated JSON characteristic

Identical in spirit to the REST body in [api.md](./api.md), so the mobile app
can share one parser across BLE and cloud paths:

```json
{
  "bpm": 78,
  "spo2": 97,
  "skin_temp_c": 36.6,
  "motion": "walking",
  "steps": 1240,
  "battery_percent": 82,
  "timestamp": 1781356800
}
```

> Keep it under one BLE MTU (≤180 bytes after the default 23-byte MTU is
> negotiated up) so it fits a single notification.

## Phone ↔ cloud bridge

The mobile app subscribes to the notifications above, maps them to the backend
schema (`bpm`→`heart_rate`, `skin_temp_c`→`temperature_c`,
`battery_percent`→`battery_level`, seconds→ms `timestamp`) and `POST`s to
`/api/telemetry`. From there the existing pipeline (rules → ML → Firebase →
dashboard + alerts) is unchanged.

## Power notes (plan Step 10)

- Notify, don't poll.
- Transmit summaries (BPM/SpO₂/temp), never continuous raw PPG.
- Reduce MAX30102 LED current; widen the sampling/transmit interval.
- Drop the BLE connection interval when idle; sleep the MCU between windows.
