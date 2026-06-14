"""
OpenTelemetry setup for Google Cloud Trace integration.

Initializes:
- TracerProvider with GCP Cloud Trace exporter (production) or console exporter (dev)
- Flask auto-instrumentation (creates a span per HTTP request)
- Requests library auto-instrumentation (traces outgoing HTTP calls)

Usage:
    from telemetry import init_telemetry, get_tracer
    init_telemetry(app)  # call once at startup
    tracer = get_tracer()
"""

import os
import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

logger = logging.getLogger(__name__)

_initialized = False


def init_telemetry(flask_app):
    """
    Initialize OpenTelemetry tracing and instrument the Flask app.

    In production (on Cloud Run / GCP), traces are exported to Cloud Trace.
    In development, traces are printed to the console.

    Must be called once at application startup, before any requests are served.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    gcp_project_id = os.getenv("GCP_PROJECT_ID", "")
    is_production = os.getenv("K_SERVICE") is not None  # K_SERVICE is set on Cloud Run

    # Resource identifies this service in Cloud Trace
    resource = Resource.create({
        "service.name": os.getenv("K_SERVICE", "backend-processing"),
        "service.version": "1.1.0",
    })

    provider = TracerProvider(resource=resource)

    if is_production and gcp_project_id:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            cloud_trace_exporter = CloudTraceSpanExporter(project_id=gcp_project_id)
            provider.add_span_processor(BatchSpanProcessor(cloud_trace_exporter))
            logger.info("OpenTelemetry: Cloud Trace exporter configured (project=%s)", gcp_project_id)
        except Exception as e:
            logger.warning("OpenTelemetry: Failed to initialize Cloud Trace exporter: %s. Falling back to console.", e)
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # Development: print spans to console
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OpenTelemetry: Console exporter configured (dev mode)")

    trace.set_tracer_provider(provider)

    # Auto-instrument Flask — creates a span for every incoming HTTP request
    FlaskInstrumentor().instrument_app(flask_app)

    # Auto-instrument the `requests` library — traces outgoing HTTP calls
    RequestsInstrumentor().instrument()

    logger.info("OpenTelemetry: Initialization complete")


def get_tracer(name: str = "backend-processing"):
    """Return an OpenTelemetry tracer for manual span creation."""
    return trace.get_tracer(name)
