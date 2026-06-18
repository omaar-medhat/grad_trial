"""
Server clock with an optional skew correction.

Most hosts have a correct clock and ``now_ms()`` is just ``time.time()`` in
milliseconds (offset 0). On a clock-skewed host (sandbox / RTC-less IoT
gateway), the Firebase layer can measure the offset from an HTTP ``Date``
header and register it here, so device-status freshness (which compares the
server "now" to the sensor's real-time timestamp) stays accurate.

offset_ms = host_clock - real_time  (positive when the host clock is ahead).
corrected now = host_now - offset_ms ≈ real time.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_offset_ms = 0


def set_offset_ms(offset_ms: int) -> None:
    global _offset_ms
    with _lock:
        _offset_ms = int(offset_ms)


def get_offset_ms() -> int:
    with _lock:
        return _offset_ms


def now_ms() -> int:
    """Current epoch milliseconds, corrected for measured host clock skew."""
    return int(time.time() * 1000) - get_offset_ms()
