"""
JunoLogger — centralized structured logger for the Juno backend.

Every log call automatically includes context fields from Flask's g object:
  session_id, user_id, function, service, environment,
  care_plan_version, grading_version, input_version

Usage:
    from utils.juno_logger import JunoLogger, monotonic_ms

    logger = JunoLogger(function="http_request")

    logger.log_request_start(method="POST", path="/care_plan", input_type="file")
    logger.log_request_end(status_code=200, duration_ms=total_ms)

Use `Markers.*.execute()` for operation timing; use JunoLogger only for free-text logs.
"""

import logging
import os
import time
from typing import Any

from utils.constants import Constants

_SERVICE = os.getenv(Constants.EnvVars.K_SERVICE, "juno-backend")
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
      - session_id          (from flask.g, set by the before_request middleware)
      - user_id             (from flask.g, set by @verify_firebase_token)
      - function            (passed at construction time)
      - care_plan_version   (from flask.g)
      - grading_version     (from flask.g)
      - input_version       (from flask.g)
      - service             (K_SERVICE env var, defaults to "juno-backend")
      - environment         ("production" on Cloud Run, "development" locally)

    All log output uses the existing StructuredJsonFormatter pipeline —
    extra fields are merged in via the standard Python `extra` parameter.

    Use `Markers.*.execute()` for operation timing; use JunoLogger only for free-text logs.
    """

    def __init__(self, function: str | None = None):
        """
        Args:
            function: Logical function or handler name for this logger instance,
                      e.g. "http_request". Included in every log entry.
        """
        self._function = function
        self._py_logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_fields(self) -> dict:
        """Build the common context fields for every log entry."""
        return {
            "session_id": _g_field("session_id"),
            "user_id": _g_field("user_id"),
            "function": self._function,
            "care_plan_version": _g_field("care_plan_version"),
            "grading_version": _g_field("grading_version"),
            "input_version": _g_field("input_version"),
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
            path:       Request path, e.g. "/care_plan".
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
