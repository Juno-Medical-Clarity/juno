"""Happy-path SSE test for the care_plan pipeline via HTTP POST /care_plan."""
import json
import pytest
from unittest.mock import patch, MagicMock

from routes.care_plan import RESULT_SENTINEL
from models.care_plan import CarePlan
from models.grading import Grading
from utils.constants import Constants


def parse_sse(response):
    text = response.get_data(as_text=True)
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            events.append(json.loads(block.removeprefix("data: ")))
    return events


def _make_fake_care_plan():
    return CarePlan.from_pipeline_result(Constants.CARE_PLAN_VERSIONS.V1_2.value, {
        "summary": "Patient has high blood pressure.",
        "diagnosis": {"main_conclusion": "Hypertension", "details": []},
        "medications": [],
        "follow_up": [],
        "reason_for_visit": [],
        "terms": {},  # must be a dict, not a list
        "raw": {
            "text": "patient text",
            "simplified_text": "simplified text",
            "clarified_text": "clarified text",
        },
    })


def test_pipeline_happy_path(client, auth_ok, fake_firestore, monkeypatch):
    """Full SSE stream: progress events appear before terminal result event."""
    fake_care_plan = _make_fake_care_plan()
    fake_grading = Grading(enabled=False)

    def fake_pipeline(text, metrics, grading_enabled=True, **kwargs):
        yield f"data: {json.dumps({'step': 2, 'status': 'active'})}\n\n"
        yield f"data: {json.dumps({'step': 2, 'status': 'done'})}\n\n"
        yield f"data: {json.dumps({'step': 3, 'status': 'active'})}\n\n"
        yield f"data: {json.dumps({'step': 3, 'status': 'done'})}\n\n"
        yield (RESULT_SENTINEL, fake_care_plan, fake_grading, text, "")

    # Must patch PIPELINES (the route uses PIPELINES[version], not the bare function name)
    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": fake_pipeline})

    response = client.post("/care_plan", data={"text": "patient text"}, headers=auth_ok)
    assert response.status_code == 200
    assert response.content_type == "text/event-stream"

    events = parse_sse(response)
    assert len(events) > 0

    # Progress events must be present
    progress_events = [e for e in events if isinstance(e.get("step"), int)]
    assert len(progress_events) > 0

    # A terminal result event must be present
    result_events = [e for e in events if e.get("step") == "result"]
    assert len(result_events) == 1

    # Result data must have care_plan and grading keys
    data = result_events[0]["data"]
    assert "care_plan" in data
    assert "grading" in data


def test_pipeline_result_has_metrics(client, auth_ok, fake_firestore, monkeypatch):
    """Result event data must include a metrics key."""
    fake_care_plan = _make_fake_care_plan()
    fake_grading = Grading(enabled=False)

    def fake_pipeline(text, metrics, grading_enabled=True, **kwargs):
        yield (RESULT_SENTINEL, fake_care_plan, fake_grading, text, "")

    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": fake_pipeline})

    response = client.post("/care_plan", data={"text": "patient text"}, headers=auth_ok)
    events = parse_sse(response)
    result = next(e for e in events if e.get("step") == "result")
    assert "metrics" in result["data"]


def test_pipeline_no_error_events_on_success(client, auth_ok, fake_firestore, monkeypatch):
    """On a clean run, no error events must be emitted."""
    fake_care_plan = _make_fake_care_plan()
    fake_grading = Grading(enabled=False)

    def fake_pipeline(text, metrics, grading_enabled=True, **kwargs):
        yield (RESULT_SENTINEL, fake_care_plan, fake_grading, text, "")

    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": fake_pipeline})

    response = client.post("/care_plan", data={"text": "patient text"}, headers=auth_ok)
    events = parse_sse(response)
    error_events = [e for e in events if e.get("step") == "error"]
    assert error_events == []


def test_pipeline_missing_auth_returns_401(client):
    """No Authorization header → 401 (no SSE stream at all)."""
    response = client.post("/care_plan", data={"text": "patient text"})
    assert response.status_code == 401


def test_pipeline_empty_text_returns_error_event(client, auth_ok, fake_firestore, monkeypatch):
    """Empty text → error SSE event (the route's own empty-text guard fires)."""
    # Don't patch PIPELINES — let the route's empty-text guard run before the pipeline call
    # (the guard fires in _care_plan_stream before pipeline is called)
    fake_care_plan = _make_fake_care_plan()
    fake_grading = Grading(enabled=False)

    def fake_pipeline(text, metrics, grading_enabled=True, **kwargs):
        yield (RESULT_SENTINEL, fake_care_plan, fake_grading, text, "")

    monkeypatch.setattr("routes.care_plan.PIPELINES", {"v1-2": fake_pipeline})

    response = client.post("/care_plan", data={"text": "   "}, headers=auth_ok)
    events = parse_sse(response)
    error_events = [e for e in events if e.get("step") == "error"]
    assert len(error_events) >= 1
