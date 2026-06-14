import logging
import uuid
import os

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from opentelemetry import trace

from routes import all_blueprints
from config import initialize_firebase
from logging_config import setup_logging
from telemetry import init_telemetry

# ---------------------------------------------------------------------------
# Bootstrap logging FIRST so all subsequent log calls use structured output
# ---------------------------------------------------------------------------
setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialize Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Enable CORS for all routes (expose X-Session-Id so frontends can read it)
CORS(app, expose_headers=["X-Session-Id"])

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
for bp in all_blueprints:
    app.register_blueprint(bp)


# ---------------------------------------------------------------------------
# Session ID middleware
# ---------------------------------------------------------------------------

@app.before_request
def extract_session_id():
    """
    Determine the session_id for this request and store it on flask.g
    for use in route handlers, structured logging, and Cloud Trace.

    Priority:
    1. appointment_id from the URL path  — naturally groups every call
       for the same appointment under one session in Cloud Trace / Logging.
    2. X-Session-Id header sent by the client.
    3. Auto-generated UUID (fallback for non-appointment routes).
    """
    # Prefer the appointment_id embedded in the URL (available for all
    # /appointments/<appointment_id>/… routes) so that every log line
    # and trace span for a given appointment shares the same session_id.
    appointment_id: str = (request.view_args or {}).get("appointment_id", "")
    if appointment_id:
        session_id = appointment_id
    else:
        session_id = request.headers.get("X-Session-Id", "") or str(uuid.uuid4())

    g.session_id = session_id

    # Attach to the current OTel span as a searchable attribute
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("session.id", session_id)
        current_span.set_attribute("http.route", request.path)


@app.after_request
def attach_session_id_header(response):
    """Echo the session ID back to the client on every response."""
    session_id = getattr(g, "session_id", None)
    if session_id:
        response.headers["X-Session-Id"] = session_id
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
            'POST /appointments': 'Create an empty appointment',
            'POST /appointments/{id}/upload-recording-new': 'Upload recording to GCS (no processing)',
            'POST /appointments/{id}/upload-notes': 'Store plain text notes on appointment',
            'POST /appointments/{id}/upload-document': 'Upload PDF document to GCS',
            'POST /appointments/{id}/process': 'Process appointment (transcribe, extract PDF, summarize)',
            'POST /appointments/{id}/audio-chunks': 'Upload audio chunk for transcription',
            'POST /appointments/{id}/generate-questions': 'Generate patient questions',
            'POST /appointments/{id}/finalize': 'Finalize appointment with full audio',
            'POST /appointments/{id}/upload-recording': 'Upload and process full audio (legacy)',
            'DELETE /appointments/{id}': 'Delete appointment and associated files',
            'GET /appointments/search?q=<query>': 'Search appointments',
            'POST /appointments/generate-questions-try': 'Generate questions (no auth)',
            'POST /appointments/upload-recording-try': 'Upload recording + SOAP (no auth)',
            'POST /appointments/upload-notes-try': 'Notes to SOAP (no auth)',
        }
    }), 200


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


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
