/**
 * PulseGuard AI - k6 backend load test
 * ====================================
 *
 * Hits the four hot endpoints with a mixed read/write workload:
 *   GET  /health            ~10%  (liveness)
 *   GET  /api/latest        ~30%  (mobile dashboard refresh)
 *   POST /api/telemetry     ~40%  (wearable ingest path)
 *   POST /api/chat          ~20%  (heaviest endpoint, capped)
 *
 * Run:
 *     k6 run load_tests/k6_backend_test.js
 *
 * Optional environment overrides:
 *     BASE_URL  default http://127.0.0.1:5000
 *     USERS     ramp target (10 | 25 | 50). default 25
 *     DURATION  steady-state duration. default 60s
 */
import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:5000";
const USERS = parseInt(__ENV.USERS || "25", 10);
const DURATION = __ENV.DURATION || "60s";

export const options = {
  thresholds: {
    http_req_failed: ["rate<0.02"],            // < 2% failures
    "http_req_duration{group:::health}": ["p(95)<200"],
    "http_req_duration{group:::latest}": ["p(95)<400"],
    "http_req_duration{group:::telemetry}": ["p(95)<800"],
    "http_req_duration{group:::chat}":   ["p(95)<3000"],
  },
  scenarios: {
    mixed: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "15s", target: USERS },
        { duration: DURATION, target: USERS },
        { duration: "10s", target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },
};

const errorRate = new Rate("pulse_errors");
const chatLatency = new Trend("chat_latency_ms");

function uid() {
  return `loadtest-${__VU}-${Math.floor(Date.now() / 60000)}`;
}

function telemetryPayload(user) {
  // Mostly normal readings; ~10% out-of-range to stress the rule engine.
  const high = Math.random() < 0.1;
  return JSON.stringify({
    user_id: user,
    heart_rate: high ? 160 : 70 + Math.floor(Math.random() * 25),
    spo2: high ? 88 : 95 + Math.floor(Math.random() * 5),
    temperature_c: high ? 39.2 : 36.5 + Math.random(),
    steps: Math.floor(Math.random() * 5000),
    calories: Math.floor(Math.random() * 500),
    sleep_duration_sec: 25200,
    timestamp: Date.now(),
  });
}

export default function () {
  const user = uid();
  const headers = { "Content-Type": "application/json" };

  group("health", () => {
    const r = http.get(`${BASE_URL}/health`);
    check(r, { "health 200": (res) => res.status === 200 });
    if (r.status !== 200) errorRate.add(1);
  });

  group("telemetry", () => {
    const r = http.post(`${BASE_URL}/api/telemetry`, telemetryPayload(user), { headers });
    const ok = check(r, {
      "telemetry 200": (res) => res.status === 200,
      "telemetry has analysis": (res) => {
        try { return res.json("data.analysis.risk_level") !== undefined; } catch { return false; }
      },
    });
    if (!ok) errorRate.add(1);
  });

  group("latest", () => {
    const r = http.get(`${BASE_URL}/api/latest?uid=${user}`);
    check(r, { "latest 200": (res) => res.status === 200 });
    if (r.status !== 200) errorRate.add(1);
  });

  // Chat is the heaviest endpoint — sample it sparsely so we don't unfairly
  // dominate the latency report.
  if (Math.random() < 0.4) {
    group("chat", () => {
      const r = http.post(
        `${BASE_URL}/api/chat`,
        JSON.stringify({ user_id: user, message: "How am I doing?" }),
        { headers, timeout: "25s" }
      );
      check(r, { "chat 200": (res) => res.status === 200 });
      if (r.status === 200) {
        try { chatLatency.add(r.json("data.latency_ms") || 0); } catch {}
      } else {
        errorRate.add(1);
      }
    });
  }

  sleep(0.5 + Math.random()); // think time 0.5–1.5s
}
