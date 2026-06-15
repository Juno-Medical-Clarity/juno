"""
JunoLogger — centralized structured logger for the Juno backend.

Every log call automatically includes context fields from Flask's g object:
  session_id, user_id, api_version, service, environment

Usage:
    from utils.juno_logger import JunoLogger, monotonic_ms

    logger = JunoLogger(api_version="v1-2")

    logger.log_request_start(method="POST", path="/simplify/v1-2", input_type="file")
    t0 = monotonic_ms()
    logger.log_step("find_medical_terms", "start")
    # ... do work ...
    logger.log_step("find_medical_terms", "done", duration_ms=monotonic_ms() - t0)
    logger.log_request_end(status_code=200, duration_ms=total_ms)
"""

import logging
import os
import time
from typing import Any

_SERVICE = os.getenv("K_SERVICE", "juno-backend")
_ENVIRONMENT = "production" if os.getenv("K_SERVICE") else "development"


def _g_field(name: str, default: Any = None) -> Any:
    """Safely read a field from Flask's g context; returns default outside request context."""
    try:
        from flask import g
        return getattr(g, name, default)
    except RuntimeError:
        return default


class JunoLogger:
    """
    Structured logger with Juno-specific context fields.

    Wraps a standard Python logger and enriches every call with:
      - session_id  (from flask.g, set by the before_request middleware)
      - user_id     (from flask.g, set by @verify_firebase_token)
      - api_version (passed at construction time or from flask.g)
      - service     (K_SERVICE env var, defaults to "juno-backend")
      - environment ("production" on Cloud Run, "development" locally)

    All log output uses the existing StructuredJsonFormatter pipeline —
    extra fields are merged in via the standard Python `extra` parameter.

    Adding logging to a new version pipeline requires zero changes here:
    just instantiate JunoLogger(api_version="v1-3") in the new route file
    and call the same methods.
    """

    def __init__(self, api_version: str | None = None):
        """
        Args:
            api_version: The pipeline version handling this request, e.g. "v1-2".
                         If None, reads from flask.g.api_version at log time.
        """
        self._api_version = api_version
        self._py_logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_fields(self) -> dict:
        """Build the common context fields for every log entry."""
        return {
            "session_id": _g_field("session_id"),
            "user_id": _g_field("user_id"),
            "api_version": self._api_version or _g_field("api_version"),
            "service": _SERVICE,
            "environment": _ENVIRONMENT,
        }

    def _log(self, level: int, message: str, extra_fields: dict | None = None) -> None:
        """Emit a log line at `level` with all base fields merged in."""
        fields = self._base_fields()
        if extra_fields:
            fields.update(extra_fields)
        # Filter out None values to keep log entries clean
        fields = {k: v for k, v in fields.items() if v is not None}
        self._py_logger.log(level, message, extra=fields)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_step(
        self,
        step_name: str,
        status: str,
        duration_ms: float | None = None,
        extra: dict | None = None,
    ) -> None:
        """
        Log a pipeline step event.

        Args:
            step_name:   Stable snake_case identifier, e.g. "find_medical_terms".
            status:      "start" | "done" | "error"
            duration_ms: Elapsed milliseconds (only meaningful when status="done").
            extra:       Any additional fields to include in this log entry.

        Example output:
            {
              "severity": "INFO",
              "message": "pipeline_step",
              "step_name": "find_medical_terms",
              "status": "done",
              "duration_ms": 42.3,
              "session_id": "abc-123",
              "user_id": "firebase-uid",
              "api_version": "v1-2",
              "service": "juno-backend",
              "environment": "production"
            }
        """
        fields: dict = {"step_name": step_name, "status": status}
        if duration_ms is not None:
            fields["duration_ms"] = round(duration_ms, 1)
        if extra:
            fields.update(extra)
        level = logging.ERROR if status == "error" else logging.INFO
        self._log(level, "pipeline_step", fields)

    def log_request_start(
        self,
        method: str,
        path: str,
        input_type: str | None = None,
        extra: dict | None = None,
    ) -> None:
        """
        Log the beginning of an HTTP request.

        Args:
            method:     HTTP method, e.g. "POST".
            path:       Request path, e.g. "/simplify/v1-2".
            input_type: Resolved input kind — "file", "text", "doc_id", or None.
            extra:      Any additional fields.
        """
        fields: dict = {
            "step_name": "request_start",
            "http_method": method,
            "http_path": path,
        }
        if input_type is not None:
            fields["input_type"] = input_type
        if extra:
            fields.update(extra)
        self._log(logging.INFO, "request_start", fields)

    def log_request_end(
        self,
        status_code: int,
        duration_ms: float,
        error: str | None = None,
        extra: dict | None = None,
    ) -> None:
        """
        Log the completion of an HTTP request.

        Args:
            status_code: HTTP response status code.
            duration_ms: Total request duration in milliseconds.
            error:       Error message if the request failed, else None.
            extra:       Any additional fields.
        """
        fields: dict = {
            "step_name": "request_end",
            "http_status_code": status_code,
            "total_duration_ms": round(duration_ms, 1),
            "status": "error" if error or status_code >= 400 else "ok",
        }
        if error:
            fields["error"] = error
        if extra:
            fields.update(extra)
        level = logging.ERROR if status_code >= 500 else (
            logging.WARNING if status_code >= 400 else logging.INFO
        )
        self._log(level, "request_end", fields)

    # ------------------------------------------------------------------
    # Convenience pass-throughs for plain log calls
    # ------------------------------------------------------------------

    def info(self, message: str, extra: dict | None = None) -> None:
        self._log(logging.INFO, message, extra)

    def warning(self, message: str, extra: dict | None = None) -> None:
        self._log(logging.WARNING, message, extra)

    def error(self, message: str, extra: dict | None = None) -> None:
        self._log(logging.ERROR, message, extra)

    def exception(self, message: str, extra: dict | None = None) -> None:
        """Log an ERROR with the current exception traceback attached."""
        fields = self._base_fields()
        if extra:
            fields.update(extra)
        fields = {k: v for k, v in fields.items() if v is not None}
        self._py_logger.exception(message, extra=fields)


def monotonic_ms() -> float:
    """Return current time in milliseconds (monotonic clock). Use for measuring elapsed durations."""
    return time.monotonic() * 1000
