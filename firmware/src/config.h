// PulseGuard AI - firmware configuration
// Copy real values here before flashing. Do NOT commit your WiFi password.
#pragma once

// ---- WiFi -----------------------------------------------------------------
#define WIFI_SSID       "your-wifi-ssid"
#define WIFI_PASSWORD   "your-wifi-password"

// ---- Backend --------------------------------------------------------------
// The Flask backend's /api/telemetry endpoint (same contract as docs/api.md).
// Use your machine's LAN IP, not 127.0.0.1 — the bracelet is a separate host.
#define API_BASE_URL    "http://192.168.1.100:5000"
#define DEVICE_USER_ID  "demo-user-001"

// ---- Sampling -------------------------------------------------------------
// How often a summarized reading is POSTed. The plan (Step 10) recommends
// sending summaries, not raw PPG, to save battery — so we sample fast locally
// but transmit at a slower cadence.
#define POST_INTERVAL_MS   5000

// ---- Battery sense --------------------------------------------------------
// ADC pin tied to the LiPo through a divider. Tune the divider ratio and the
// empty/full voltages to your hardware (see docs/hardware.md).
#define BATTERY_ADC_PIN    2
#define BATTERY_DIVIDER    2.0f      // (R1+R2)/R2
#define BATTERY_FULL_V     4.20f
#define BATTERY_EMPTY_V    3.30f
