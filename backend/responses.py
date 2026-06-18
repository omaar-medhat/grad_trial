"""Consistent JSON response envelope used by every endpoint."""

from __future__ import annotations

from typing import Any, Optional

from flask import jsonify


def ok(data: Any = None, message: str = "Success", status: int = 200):
    return jsonify({"ok": True, "data": data, "message": message}), status


def err(code: str, message: str, status: int = 400, details: Optional[Any] = None):
    payload: dict = {"ok": False, "error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status
