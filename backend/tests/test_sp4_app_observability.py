"""
SP4 Tasks 5, 6, 7, 9 — observability integration tests for app.py / batch.py.

TDD: these tests were written before the implementation.
"""
import sys
import importlib


# ---------------------------------------------------------------------------
# Task 5 — JunoSink registered at startup
# ---------------------------------------------------------------------------

def test_register_sink_called():
    """After importing app, the global sink must be a JunoSink instance."""
    # Ensure app is imported (it may already be cached from another test run)
    if "app" not in sys.modules:
        import app  # noqa: F401

    from utils.markers import resolve_sink, JunoSink
    assert isinstance(resolve_sink(), JunoSink), (
        "Expected a JunoSink to be registered at app startup"
    )


# ---------------------------------------------------------------------------
# Task 5/7 — JunoMetrics import is gone from app.py
# ---------------------------------------------------------------------------

def test_junometrics_not_imported_in_app():
    """app.py must not import JunoMetrics (it has been replaced by Markers)."""
    app_source = open(__file__.replace(
        "tests/test_sp4_app_observability.py", "app.py"
    )).read()
    assert "from utils.juno_metrics import JunoMetrics" not in app_source, (
        "JunoMetrics import should have been removed from app.py"
    )


# ---------------------------------------------------------------------------
# Task 6 — batch.py: no getattr(g, "session_id", user_id) fallback
# ---------------------------------------------------------------------------

def test_session_id_batch_no_user_id_fallback():
    """batch.py must not fall back to user_id when looking up session_id."""
    batch_source = open(__file__.replace(
        "tests/test_sp4_app_observability.py", "routes/batch.py"
    )).read()
    assert 'getattr(g, "session_id", user_id)' not in batch_source, (
        'batch.py still falls back to user_id for session_id — remove the fallback'
    )
    # Also confirm the string "user_id" does not appear as a session_id fallback
    import re
    # Reject patterns like: getattr(g, "session_id", user_id)
    bad = re.search(r'getattr\s*\(\s*g\s*,\s*["\']session_id["\']\s*,\s*user_id\s*\)', batch_source)
    assert bad is None, f"Found user_id session_id fallback in batch.py: {bad.group()}"


# ---------------------------------------------------------------------------
# Task 9 — X-Trace-Id is in the CORS expose_headers
# ---------------------------------------------------------------------------

def test_x_trace_id_cors_exposed():
    """app.py must expose X-Trace-Id via CORS."""
    app_source = open(__file__.replace(
        "tests/test_sp4_app_observability.py", "app.py"
    )).read()
    assert "X-Trace-Id" in app_source, (
        "X-Trace-Id should appear in app.py CORS expose_headers"
    )
    # Confirm it's in the expose_headers list (not just a comment)
    import re
    match = re.search(r'expose_headers\s*=\s*\[([^\]]*)\]', app_source)
    assert match, "Could not find expose_headers list in app.py"
    exposed = match.group(1)
    assert "X-Trace-Id" in exposed, (
        f"X-Trace-Id not found in expose_headers list: {exposed!r}"
    )


# ---------------------------------------------------------------------------
# Task 7 — http.request marker emitted (not for /health)
# ---------------------------------------------------------------------------

def test_http_request_marker_emitted():
    """GET / must emit an http.request marker with duration_ms_observed."""
    from utils.markers import register_sink, InMemorySink

    sink = InMemorySink()
    register_sink(sink)

    if "app" in sys.modules:
        app_module = sys.modules["app"]
    else:
        import app as app_module  # noqa: F401

    client = app_module.app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200

    events = [e for e in sink.events if e["name"] == "http.request"]
    assert len(events) >= 1, (
        f"Expected at least one http.request marker event, got: {sink.events}"
    )
    event = events[-1]
    assert "duration_ms_observed" in event["dimensions"], (
        f"http.request event missing duration_ms_observed: {event}"
    )
    assert event["dimensions"].get("function") == "http_request", (
        f"Expected function='http_request', got: {event['dimensions']}"
    )


def test_health_check_no_marker():
    """GET /health must NOT emit an http.request marker."""
    from utils.markers import register_sink, InMemorySink

    sink = InMemorySink()
    register_sink(sink)

    if "app" in sys.modules:
        app_module = sys.modules["app"]
    else:
        import app as app_module  # noqa: F401

    client = app_module.app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200

    events = [e for e in sink.events if e["name"] == "http.request"]
    assert len(events) == 0, (
        f"/health should not emit http.request markers, got: {events}"
    )
