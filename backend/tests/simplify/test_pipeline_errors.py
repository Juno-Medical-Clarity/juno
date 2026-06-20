"""Error-path SSE tests for the care_plan pipeline via HTTP POST /care_plan."""
import json
import pytest
from unittest.mock import patch, MagicMock

from routes.care_plan import RESULT_SENTINEL


def parse_sse(response):
    text = response.get_data(as_text=True)
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            events.append(json.loads(block.removeprefix("data: ")))
    return events


def test_pipeline_emits_error_event_on_failure(client, auth_ok, fake_firestore, monkeypatch):
    """If the pipeline emits an error event, it is relayed in the SSE stream."""
    def failing_pipeline(text, metrics, grading_enabled=True):
        yield f"data: {json.dumps({'step': 2, 'status': 'active'})}\n\n"
        yield f"data: {json.dumps({'step': 'error', 'error': 'boom'})}\n\n"

    # Must patch PIPELINES (the route looks up pipeline via PIPELINES[version])
    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": failing_pipeline})
    response = client.post("/care_plan", data={"text": "x"}, headers=auth_ok)
    events = parse_sse(response)
    error_events = [e for e in events if e.get("step") == "error"]
    assert len(error_events) >= 1
    assert "error" in error_events[0]


def test_pipeline_error_event_has_no_result(client, auth_ok, fake_firestore, monkeypatch):
    """If the pipeline emits an error event, no result event is present."""
    def failing_pipeline(text, metrics, grading_enabled=True):
        yield f"data: {json.dumps({'step': 'error', 'error': 'failure'})}\n\n"

    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": failing_pipeline})
    response = client.post("/care_plan", data={"text": "x"}, headers=auth_ok)
    events = parse_sse(response)
    result_events = [e for e in events if e.get("step") == "result"]
    assert result_events == []


def test_pipeline_raises_exception_yields_error(client, auth_ok, fake_firestore, monkeypatch):
    """If the pipeline raises an unhandled exception, an error SSE event is streamed."""
    def raising_pipeline(text, metrics, grading_enabled=True):
        yield f"data: {json.dumps({'step': 2, 'status': 'active'})}\n\n"
        raise RuntimeError("Unexpected crash")

    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": raising_pipeline})
    response = client.post("/care_plan", data={"text": "x"}, headers=auth_ok)
    events = parse_sse(response)
    error_events = [e for e in events if e.get("step") == "error"]
    assert len(error_events) >= 1


def test_pipeline_progress_before_error(client, auth_ok, fake_firestore, monkeypatch):
    """Progress events streamed before the error event are preserved in the stream."""
    def failing_pipeline(text, metrics, grading_enabled=True):
        yield f"data: {json.dumps({'step': 2, 'status': 'active'})}\n\n"
        yield f"data: {json.dumps({'step': 2, 'status': 'done'})}\n\n"
        yield f"data: {json.dumps({'step': 'error', 'error': 'step 3 failed'})}\n\n"

    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": failing_pipeline})
    response = client.post("/care_plan", data={"text": "x"}, headers=auth_ok)
    events = parse_sse(response)
    step2_events = [e for e in events if e.get("step") == 2]
    assert len(step2_events) > 0
    error_events = [e for e in events if e.get("step") == "error"]
    assert len(error_events) >= 1
