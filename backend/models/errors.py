"""Pydantic models for the SP2 error contract wire shape."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import Field
from .base import JsonModel


class StatusEnum(str, Enum):
    error       = "error"
    success     = "success"
    not_started = "not_started"
    processing  = "processing"
    completed   = "completed"


class ErrorDetail(JsonModel):
    """Structured error payload.

    Intentionally usable without an HTTP request context:
    - `path` is Optional (workers writing Firestore job docs have no path).
    - `timestamp` is an ISO-8601 UTC string; callers use datetime.now(timezone.utc).isoformat().
    - `code` is always a string (ErrorCode.value), not the enum, so it is JSON-serializable
      without extra config and safe to store in Firestore.
    """
    code: str
    message: str
    details: Optional[str] = None
    timestamp: str
    path: str | None = None
    user_hint: Optional[str] = None
    retryable: bool = False


class ApiResponse(JsonModel):
    """Top-level envelope for every HTTP response.

    Success:  ApiResponse(status="success", data={...})
    Error:    ApiResponse(status="error", error=ErrorDetail(...))
    The HTTP status code lives on the HTTP layer, not duplicated here.
    """
    status: StatusEnum
    data: dict[str, Any] | None = None
    error: ErrorDetail | None = None
    requestId: str | None = None
