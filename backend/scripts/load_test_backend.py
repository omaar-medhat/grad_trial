"""
Lightweight load test for the PulseGuard backend — standard library only.

Fires N concurrent requests at a backend endpoint and reports throughput and
latency percentiles. No external services or pip packages are required; it just
needs the Flask backend running locally:

    flask --app app run --port 8000      # in one terminal
    python scripts/load_test_backend.py  # in another

By default it hammers the lightweight `/health` endpoint (no model load), so it
is safe to run during a demo. Point it at other endpoints with --endpoint and,
for POSTs, --method POST --json '{"...": "..."}'.

Examples:
    python scripts/load_test_backend.py -n 500 -c 50
    python scripts/load_test_backend.py --endpoint /api/health -n 200 -c 20
    python scripts/load_test_backend.py --endpoint /ai/medical-slm \
        --method POST --json '{"question":"hi"}' -n 20 -c 4
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple


def _one_request(
    url: str, method: str, body: Optional[bytes], timeout: float
) -> Tuple[bool, float, int]:
    """Return (success, latency_seconds, status_code)."""
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            code = resp.getcode()
        latency = time.perf_counter() - start
        return (200 <= code < 400, latency, code)
    except urllib.error.HTTPError as exc:
        # A 4xx/5xx is a completed request with a status — record it.
        return (False, time.perf_counter() - start, exc.code)
    except Exception:
        return (False, time.perf_counter() - start, 0)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * len(ordered) + 0.5)) - 1))
    return ordered[k]


def main() -> int:
    p = argparse.ArgumentParser(description="Lightweight backend load test.")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--endpoint", default="/health")
    p.add_argument("--method", default="GET", choices=["GET", "POST"])
    p.add_argument("--json", dest="json_body", default=None,
                   help="JSON string body for POST requests.")
    p.add_argument("-n", "--requests", type=int, default=200,
                   help="Total number of requests.")
    p.add_argument("-c", "--concurrency", type=int, default=20,
                   help="Number of concurrent workers.")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    url = args.base_url.rstrip("/") + args.endpoint
    body = args.json_body.encode("utf-8") if args.json_body else None

    print("=" * 60)
    print("PulseGuard backend load test")
    print("=" * 60)
    print(f"Target      : {args.method} {url}")
    print(f"Requests    : {args.requests}  (concurrency {args.concurrency})")

    # Fail fast with a clear message if the server is not up.
    ok0, _, code0 = _one_request(url, args.method, body, args.timeout)
    if code0 == 0:
        print(f"\n[ERROR] Could not reach {url}. Is the backend running?")
        print("        Start it with:  flask --app app run --port 8000")
        return 2

    latencies: list[float] = []
    successes = 0
    failures = 0
    statuses: dict[int, int] = {}

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(_one_request, url, args.method, body, args.timeout)
            for _ in range(args.requests)
        ]
        for fut in as_completed(futures):
            ok, latency, code = fut.result()
            latencies.append(latency)
            statuses[code] = statuses.get(code, 0) + 1
            if ok:
                successes += 1
            else:
                failures += 1
    wall = time.perf_counter() - wall_start

    ms = [x * 1000 for x in latencies]
    print("-" * 60)
    print(f"Total requests   : {len(latencies)}")
    print(f"Successful       : {successes}")
    print(f"Failed           : {failures}")
    print(f"Status codes     : {dict(sorted(statuses.items()))}")
    print(f"Total wall time  : {wall:.2f} s")
    print(f"Requests / sec   : {len(latencies) / wall:.1f}")
    if ms:
        print(f"Latency avg      : {statistics.mean(ms):.1f} ms")
        print(f"Latency median   : {statistics.median(ms):.1f} ms")
        print(f"Latency p95      : {_percentile(ms, 95):.1f} ms")
        print(f"Latency p99      : {_percentile(ms, 99):.1f} ms")
        print(f"Latency max      : {max(ms):.1f} ms")
    print("-" * 60)
    # Non-zero exit if any request failed, so it is CI/script friendly.
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
