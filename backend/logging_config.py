"""Structured-ish logging setup for the Flask backend.

Each request gets an X-Request-ID (echoed back to the client) so logs can be
correlated end-to-end during a defense demo.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from typing import Optional

from flask import Flask, g, request

REQUEST_ID_HEADER = "X-Request-ID"


def configure_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        for h in root.handlers:
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.setLevel(log_level)
    root.addHandler(handler)
    # Quiet noisy libs.
    for noisy in ("werkzeug", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def install_request_logging(app: Flask) -> None:
    logger = logging.getLogger("pulseguard.access")

    @app.before_request
    def _before():
        g.request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        g.start_time = time.time()

    @app.after_request
    def _after(response):
        latency_ms = int((time.time() - getattr(g, "start_time", time.time())) * 1000)
        request_id: Optional[str] = getattr(g, "request_id", None)
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "rid=%s method=%s path=%s status=%s latency_ms=%s ip=%s",
            request_id,
            request.method,
            request.path,
            response.status_code,
            latency_ms,
            request.headers.get("X-Forwarded-For", request.remote_addr),
        )
        return response

    @app.errorhandler(Exception)
    def _on_error(exc):
        logger.exception("rid=%s unhandled error: %s", getattr(g, "request_id", "?"), exc)
        # Re-raise so Flask's default handler returns 500; our wrapper in app.py
        # converts known exceptions into the standard JSON envelope first.
        raise exc
