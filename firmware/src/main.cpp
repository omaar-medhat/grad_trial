/*
 * PulseGuard AI - bracelet firmware (reference implementation)
 * ============================================================
 * Reads the project's sensors over I2C, derives a summarized health reading,
 * and POSTs it as JSON to the existing Flask backend (/api/telemetry). The
 * payload matches the contract in docs/api.md exactly, so the physical
 * bracelet, the Python simulator, and the in-browser simulator are
 * interchangeable telemetry sources.
 *
 * Sensors (per the project plan):
 *   - MAX30102  heart rate + SpO2   (I2C 0x57)   SparkFun MAX3010x library
 *   - MAX30205  skin temperature    (I2C 0x48)   read directly over Wire
 *   - LSM6DSOX  IMU / step counter   (I2C 0x6A)   SparkFun LSM6DSO library
 *   - LiPo gauge via ADC divider     (battery %)
 *
 * This is a REFERENCE sketch: the wiring/threshold constants in config.h must
 * be matched to your board, and the HR/SpO2 maths from the MAX30102 should be
 * validated against a reference pulse oximeter before any real use. It is a
 * wellness/educational prototype, not a medical device.
 */

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#include "MAX30105.h"
#include "spo2_algorithm.h"
#include "SparkFunLSM6DSO.h"

#include "config.h"

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------
static MAX30105 ppg;          // MAX30102 is driven by the MAX3010x library
static LSM6DSO  imu;

static const uint8_t  MAX30205_ADDR = 0x48;   // body-temperature sensor
static uint32_t       lastPostMs    = 0;
static uint32_t       stepCount     = 0;

// SpO2 algorithm buffers (100 samples @ 100Hz = 1s window).
#define SAMPLE_COUNT 100
static uint32_t irBuffer[SAMPLE_COUNT];
static uint32_t redBuffer[SAMPLE_COUNT];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[wifi] connecting");
  uint8_t tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries++ < 40) {
    delay(250);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED
                   ? "\n[wifi] connected"
                   : "\n[wifi] FAILED (will retry in loop)");
}

// MAX30205 returns temperature in 0.00390625 C steps across two bytes.
static float readSkinTempC() {
  Wire.beginTransmission(MAX30205_ADDR);
  Wire.write(0x00);                       // temperature register
  if (Wire.endTransmission(false) != 0) return NAN;
  Wire.requestFrom((int)MAX30205_ADDR, 2);
  if (Wire.available() < 2) return NAN;
  int16_t raw = (Wire.read() << 8) | Wire.read();
  return raw * 0.00390625f;
}

// Convert the divided LiPo voltage on the ADC into a 0-100% estimate.
static int readBatteryPercent() {
  // ESP32 ADC is 12-bit (0..4095) over ~3.3V full-scale.
  float v = (analogRead(BATTERY_ADC_PIN) / 4095.0f) * 3.3f * BATTERY_DIVIDER;
  float pct = (v - BATTERY_EMPTY_V) / (BATTERY_FULL_V - BATTERY_EMPTY_V) * 100.0f;
  return (int)constrain(pct, 0.0f, 100.0f);
}

// Collect one 1s window and run SpO2/HR estimation from the MAX30102.
static void readPpg(int32_t &heartRate, int32_t &spo2) {
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    while (!ppg.available()) ppg.check();
    redBuffer[i] = ppg.getRed();
    irBuffer[i]  = ppg.getIR();
    ppg.nextSample();
  }
  int8_t hrValid = 0, spo2Valid = 0;
  maxim_heart_rate_and_oxygen_saturation(
      irBuffer, SAMPLE_COUNT, redBuffer,
      &spo2, &spo2Valid, &heartRate, &hrValid);
  if (!hrValid)   heartRate = -1;
  if (!spo2Valid) spo2 = -1;
}

static bool postReading(int32_t hr, int32_t spo2, float tempC,
                        uint32_t steps, int battery) {
  if (WiFi.status() != WL_CONNECTED) return false;

  JsonDocument doc;
  doc["user_id"]       = DEVICE_USER_ID;
  doc["heart_rate"]    = hr;
  doc["spo2"]          = spo2;
  doc["temperature_c"] = tempC;
  doc["steps"]         = steps;
  doc["battery_level"] = battery;
  doc["source"]        = "real_bracelet";
  doc["timestamp"]     = (uint64_t)time(nullptr) * 1000ULL;

  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.begin(String(API_BASE_URL) + "/api/telemetry");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  Serial.printf("[post] %s -> %d\n", body.c_str(), code);
  http.end();
  return code == 200;
}

// ---------------------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nPulseGuard AI bracelet " PULSE_FW_VERSION);

  Wire.begin();

  if (!ppg.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[ppg] MAX30102 not found — check wiring");
  } else {
    // Lower LED current saves battery (plan Step 10) while staying readable.
    ppg.setup(0x1F, 4, 2, 100, 411, 4096);
  }

  if (!imu.begin()) {
    Serial.println("[imu] LSM6DSOX not found — check wiring");
  } else {
    imu.initialize(BASIC_SETTINGS);
  }

  connectWifi();
  configTime(0, 0, "pool.ntp.org");   // epoch for the timestamp field
}

void loop() {
  // A real build feeds IMU samples into the LSM6DSOX hardware step counter or
  // a simple peak detector; here we approximate so the field is populated.
  if (imu.getAccelZ() > 1.2f) stepCount++;

  if (millis() - lastPostMs >= POST_INTERVAL_MS) {
    lastPostMs = millis();

    int32_t hr = -1, spo2 = -1;
    readPpg(hr, spo2);
    float tempC = readSkinTempC();
    int battery = readBatteryPercent();

    // Only transmit physiologically plausible readings; the backend also
    // validates, but skipping junk locally saves radio energy.
    if (hr > 0 && spo2 > 0 && !isnan(tempC)) {
      postReading(hr, spo2, tempC, stepCount, battery);
    } else {
      Serial.println("[skip] incomplete reading (finger off sensor?)");
    }

    if (WiFi.status() != WL_CONNECTED) connectWifi();
  }
}
