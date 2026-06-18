"""
PulseGuard AI - Locust load test (pure Python alternative to k6).

Run:
    pip install locust
    locust -f load_tests/locustfile.py --host http://127.0.0.1:5000
    # then open http://localhost:8089 and start, say, 25 users at spawn-rate 5

Or headless:
    locust -f load_tests/locustfile.py --host http://127.0.0.1:5000 \\
        -u 25 -r 5 -t 1m --headless --print-stats
"""
from __future__ import annotations

import json
import random
import time

from locust import HttpUser, between, task


def payload(uid: str) -> str:
    high = random.random() < 0.1
    return json.dumps({
        "user_id": uid,
        "heart_rate": 160 if high else random.randint(65, 95),
        "spo2": 88 if high else random.randint(95, 100),
        "temperature_c": 39.2 if high else round(36.5 + random.random(), 1),
        "steps": random.randint(0, 5000),
        "calories": random.randint(0, 500),
        "sleep_duration_sec": 25200,
        "timestamp": int(time.time() * 1000),
    })


class PulseGuardUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.uid = f"locust-{self.environment.runner.user_count}-{random.randint(0, 9999)}"

    @task(2)
    def health(self):
        self.client.get("/health", name="GET /health")

    @task(8)
    def post_telemetry(self):
        self.client.post(
            "/api/telemetry",
            data=payload(self.uid),
            headers={"Content-Type": "application/json"},
            name="POST /api/telemetry",
        )

    @task(6)
    def get_latest(self):
        self.client.get(f"/api/latest?uid={self.uid}", name="GET /api/latest")

    @task(3)
    def get_history(self):
        self.client.get(f"/api/history?uid={self.uid}&limit=60", name="GET /api/history")

    @task(2)
    def chat(self):
        self.client.post(
            "/api/chat",
            data=json.dumps({"user_id": self.uid, "message": "How are my vitals?"}),
            headers={"Content-Type": "application/json"},
            name="POST /api/chat",
        )
