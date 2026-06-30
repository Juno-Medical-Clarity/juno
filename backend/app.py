import logging
import time  # noqa: F401
import uuid
import os

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from opentelemetry import trace

import os as _os
from routes import API_BLUEPRINTS, WORKER_BLUEPRINTS
from errors import make_error_response, ErrorCode
from utils.firebase import initialize_firebase
from observability import setup_logging, init_telemetry
from utils.juno_logger import JunoLogger, monotonic_ms

# ---------------------------------------------------------------------------
# Bootstrap logging FIRST so all subsequent log calls use structured output
# ---------------------------------------------------------------------------
setup_logging()
from utils.markers import register_sink, JunoSink, Markers, JunoContext
register_sink(JunoSink())
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialize Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Enable CORS for all routes with explicit origin/header/method allow-lists
CORS(
    app,
    origins=[
        "https://juno-medical-clarity.web.app",
        "https://juno-medical-clarity.firebaseapp.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Session-Id"],
    expose_headers=["X-Session-Id", "X-Trace-Id"],
    supports_credentials=False,
    max_age=600,
)

# ---------------------------------------------------------------------------
# Initialize OpenTelemetry (instruments Flask + outgoing HTTP)
# ---------------------------------------------------------------------------
init_telemetry(app)

# ---------------------------------------------------------------------------
# Initialize Firebase
# ---------------------------------------------------------------------------
initialize_firebase()

# ---------------------------------------------------------------------------
# Register all route blueprints
# ---------------------------------------------------------------------------
JUNO_MODE = _os.environ.get("JUNO_MODE", "api")
if JUNO_MODE == "worker":
    _blueprints = WORKER_BLUEPRINTS
elif JUNO_MODE == "combined":
    # Combined mode (used by ephemeral PR previews): a single service serves
    # both the API routes (which enqueue Cloud Tasks) and the worker routes
    # (which execute them), enqueuing tasks that call back into itself.
    # Dedupe in case any blueprint is shared between the two lists.
    _seen: set = set()
    _blueprints = []
    for bp in (*API_BLUEPRINTS, *WORKER_BLUEPRINTS):
        if id(bp) not in _seen:
            _seen.add(id(bp))
            _blueprints.append(bp)
else:
    _blueprints = API_BLUEPRINTS
for bp in _blueprints:
    app.register_blueprint(bp)

# Sweep stale GCS dataset temp dirs left by any previous container instance
if JUNO_MODE in ("worker", "combined"):
    try:
        from utils.gcs_datasets import sweep_stale_dataset_dirs
        sweep_stale_dataset_dirs()
    except Exception:
        logger.exception("app: stale dataset dir sweep failed at startup")


# ---------------------------------------------------------------------------
# Session ID middleware
# ---------------------------------------------------------------------------

@app.before_request
def extract_session_id():
    """
    Determine the session_id for this request and store it on flask.g
    for use in route handlers, structured logging, and Cloud Trace.

    Source: X-Session-Id request header, or a generated UUID if absent.
    SP4 boundary: session_id never falls back to user_id.
    """
    session_id = request.headers.get("X-Session-Id", "") or str(uuid.uuid4())
    g.session_id = session_id

    # Record start time for request duration logging in after_request
    g.request_start_ms = monotonic_ms()

    # Attach to the current OTel span as a searchable attribute
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("session.id", session_id)
        current_span.set_attribute("http.route", request.path)

    # Log the start of every request (health checks excluded to avoid noise)
    if request.path != "/health":
        juno_logger = JunoLogger(function="http_request")
        juno_logger.log_request_start(
            method=request.method,
            path=request.path,
        )


@app.after_request
def attach_session_id_header(response):
    """Echo the session ID back to the client on every response."""
    session_id = getattr(g, "session_id", None)
    if session_id:
        response.headers["X-Session-Id"] = session_id

    # Attach X-Trace-Id header from the current OTel span
    span_ctx = trace.get_current_span().get_span_context()
    if span_ctx and span_ctx.is_valid:
        response.headers["X-Trace-Id"] = format(span_ctx.trace_id, "032x")

    # Log request completion with total duration (skip health checks)
    if request.path != "/health":
        start_ms = getattr(g, "request_start_ms", None)
        duration_ms = (monotonic_ms() - start_ms) if start_ms is not None else 0.0
        juno_logger = JunoLogger(function="http_request")
        juno_logger.log_request_end(
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        # Record request-level metrics via Markers (skip SSE routes — they emit their own)
        if request.path != "/health" and response.content_type != "text/event-stream":
            def _emit(scope):
                JunoContext.from_g(function="http_request").apply(scope)
                scope.add("http_method", request.method)
                scope.add("http_path", request.path)
                scope.add("http_status", str(response.status_code))
                scope.add("duration_ms_observed", round(duration_ms, 1))
                if response.status_code >= 500:
                    scope.mark_failed()
            Markers.Http.Request.execute(_emit)

    return response


# ---------------------------------------------------------------------------
# Health check endpoint
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify API is running"""
    return jsonify({
        'status': 'healthy',
        'message': 'Medical Scribe Processing API is running'
    }), 200


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API information"""
    return jsonify({
        'name': 'Medical Scribe Processing API',
        'version': '1.1.0',
        'endpoints': {
            'POST /care_plan/grade': 'Re-run grading on a saved or ephemeral care plan',
            'POST /care_plan/jobs': 'Create a single async care-plan job',
            'POST /care_plan/batch/jobs': 'Create async batch care-plan jobs',
            'GET /care_plan/datasets': 'List preset datasets',
            'GET /care_plan/saved': "List the user's saved care plans",
            'GET /health': 'Health check',
        }
    }), 200


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return make_error_response(
        ErrorCode.ENDPOINT_NOT_FOUND,
        request.path,
        {"method": request.method, "path": request.path},
    ).to_dict(), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return make_error_response(
        ErrorCode.ENDPOINT_NOT_FOUND,
        request.path,
        {"method": request.method, "path": request.path},
    ).to_dict(), 405

@app.errorhandler(500)
def internal_error(error):
    return make_error_response(
        ErrorCode.INTERNAL_ERROR,
        request.path,
    ).to_dict(), 500


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('FLASK_ENV') == 'development'
    )
