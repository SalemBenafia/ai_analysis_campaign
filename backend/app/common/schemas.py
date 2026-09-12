"""app/common/schemas.py — shared Pydantic response helpers."""
from __future__ import annotations

from typing import Any


def success(data: Any, message: str = "OK") -> dict:
    return {"success": True, "message": message, "data": data}


def error(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}
