"""
JunoMetrics — log-based metrics for Cloud Monitoring integration.

Metrics are recorded as structured log entries with a `metric: true` field.
Cloud Monitoring log-based metrics can filter on this field and extract
numeric values (e.g. duration_ms) as distribution metrics for charting.

Usage:
    from utils.juno_metrics import JunoMetrics

    metrics = JunoMetrics()
    metrics.record_counter("simplify_request", labels={"version": "v1-2"})
    metrics.record_latency("simplify_pipeline", duration_ms=8432,
                           labels={"version": "v1-2", "input_type": "file"})
    # on error:
    metrics.record_error("ValueError", "simplify_pipeline",
                         labels={"version": "v1-2"})

Log-based metric filter to use in Cloud Monitoring Console:
    resource.type="cloud_run_revision"
    jsonPayload.metric=true AND jsonPayload.metric_type="latency"

    resource.type="cloud_run_revision"
    jsonPayload.metric=true AND jsonPayload.metric_type="counter"
"""

import logging
import os
from typing import Any

_SERVICE = os.getenv("K_SERVICE", "juno-backend")
_ENVIRONMENT = "production" if os.getenv("K_SERVICE") else "development"

_metrics_logger = logging.getLogger(__name__)


def _g_field(name: str, default: Any = None) -> Any:
    """Safely read a field from Flask's g context."""
    try:
        from flask import g
        return getattr(g, name, default)
    except RuntimeError:
        return default


class JunoMetrics:
    """
    Records metrics as structured log entries consumed by Cloud Monitoring log-based metrics.

    Every entry includes `metric: true` (boolean) so Cloud Monitoring filters
    can target metric entries without matching on free-text message fields.

    Labels are extensible — new pipeline versions can pass any key/value pairs
    (e.g. {"version": "v1-3", "input_type": "text", "urgency_level": "high"})
    without changing this class.

    Example metric log entry:
        {
          "severity": "INFO",
          "message": "juno_metric",
          "metric": true,
          "metric_type": "latency",
          "operation": "simplify_pipeline",
          "duration_ms": 8432,
          "labels": {"version": "v1-2", "input_type": "file"},
          "session_id": "abc-123",
          "service": "juno-backend",
          "environment": "production"
        }
    """

    def _base_extra(self) -> dict:
        extra: dict = {
            "metric": True,
            "service": _SERVICE,
            "environment": _ENVIRONMENT,
        }
        session_id = _g_field("session_id")
        if session_id:
            extra["session_id"] = session_id
        user_id = _g_field("user_id")
        if user_id:
            extra["user_id"] = user_id
        return extra

    def record_latency(
        self,
        operation: str,
        duration_ms: float,
        labels: dict | None = None,
    ) -> None:
        """
        Record a latency observation for `operation`.

        Args:
            operation:   Stable name for the operation being timed, e.g. "simplify_pipeline".
            duration_ms: Elapsed time in milliseconds.
            labels:      Optional dict of dimension labels — e.g. {"version": "v1-2", "input_type": "file"}.

        Cloud Monitoring setup:
            Filter:  jsonPayload.metric=true AND jsonPayload.metric_type="latency"
                     AND jsonPayload.operation="simplify_pipeline"
            Value:   jsonPayload.duration_ms  (type: Distribution)
        """
        extra = self._base_extra()
        extra.update({
            "metric_type": "latency",
            "operation": operation,
            "duration_ms": round(duration_ms, 1),
        })
        if labels:
            extra["labels"] = labels
        _metrics_logger.info("juno_metric", extra=extra)

    def record_counter(
        self,
        metric_name: str,
        labels: dict | None = None,
    ) -> None:
        """
        Increment a counter metric by 1.

        Args:
            metric_name: Stable name for the counter, e.g. "simplify_request".
            labels:      Optional dict of dimension labels.

        Cloud Monitoring setup:
            Filter:  jsonPayload.metric=true AND jsonPayload.metric_type="counter"
                     AND jsonPayload.metric_name="simplify_request"
            Value:   jsonPayload.value  (type: Counter)
        """
        extra = self._base_extra()
        extra.update({
            "metric_type": "counter",
            "metric_name": metric_name,
            "value": 1,
        })
        if labels:
            extra["labels"] = labels
        _metrics_logger.info("juno_metric", extra=extra)

    def record_error(
        self,
        error_type: str,
        operation: str,
        labels: dict | None = None,
    ) -> None:
        """
        Record an error occurrence for `operation`.

        Args:
            error_type: Exception class name, e.g. "ValueError", "TimeoutError".
            operation:  The operation that failed, e.g. "simplify_pipeline".
            labels:     Optional dict of dimension labels.

        Cloud Monitoring setup:
            Filter:  jsonPayload.metric=true AND jsonPayload.metric_type="error"
            Labels:  jsonPayload.error_type, jsonPayload.operation
            Value:   Count  (type: Counter)
        """
        extra = self._base_extra()
        extra.update({
            "metric_type": "error",
            "error_type": error_type,
            "operation": operation,
        })
        if labels:
            extra["labels"] = labels
        _metrics_logger.warning("juno_metric", extra=extra)
