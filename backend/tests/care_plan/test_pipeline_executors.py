"""Tests for run_care_plan_pipeline — the thin adapter over CarePlanV1_2Pipeline.iter_steps()."""
from unittest.mock import patch, MagicMock

from models.metrics import Metrics
from routes.care_plan import run_care_plan_pipeline
from models.pipeline_events import (
    StepEvent,
    PipelineRunResult,
    PipelineStepError,
    AdapterStepEvent,
    AdapterResult,
    AdapterError,
)
from models.grading import Grading


def _make_metrics():
    return Metrics.start(session_id="session-1", pipeline_version="v1-2", input_type="text")


def _make_run_result(text="plain note"):
    """Return a PipelineRunResult with a minimal stub care_plan."""
    return PipelineRunResult(
        care_plan=MagicMock(),
        term_data={"substitution_candidates": [], "preserve_and_define_terms": [], "abbreviations": []},
        simplified="simplified",
        clarified="clarified",
        raw_text=text,
    )


class FakePipeline:
    """Fake pipeline that yields typed events from iter_steps without calling wrap_step."""

    def iter_steps(self, text, wrap_step=None):
        for step in (2, 3, 4, 5):
            yield StepEvent(step=step, status="active", label=f"Step {step}")
            yield StepEvent(step=step, status="done", label=f"Step {step}")
        yield _make_run_result(text)


class FailingPipeline:
    """Fake pipeline that yields a step error."""

    def iter_steps(self, text, wrap_step=None):
        yield PipelineStepError(step=3, exc=RuntimeError("fail"))


def _mock_markers():
    """Return a mock_scope and side_effect setter for Markers.CarePlan.Pipeline.execute."""
    mock_scope = MagicMock()
    return mock_scope


def test_run_care_plan_pipeline_yields_typed_step_events():
    metrics = _make_metrics()
    mock_scope = _mock_markers()

    with patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FakePipeline()), \
         patch("routes.care_plan.Markers") as mock_markers:
        mock_markers.CarePlan.Pipeline.execute.side_effect = lambda fn: fn(mock_scope)

        events = list(run_care_plan_pipeline("plain note", metrics, grading_enabled=False))

    step_events = [e for e in events if isinstance(e, AdapterStepEvent)]
    assert [(e.step, e.status) for e in step_events] == [
        (2, "active"), (2, "done"),
        (3, "active"), (3, "done"),
        (4, "active"), (4, "done"),
        (5, "active"), (5, "done"),
    ]


def test_run_care_plan_pipeline_yields_adapter_result():
    metrics = _make_metrics()
    mock_scope = _mock_markers()

    with patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FakePipeline()), \
         patch("routes.care_plan.Markers") as mock_markers:
        mock_markers.CarePlan.Pipeline.execute.side_effect = lambda fn: fn(mock_scope)

        events = list(run_care_plan_pipeline("plain note", metrics, grading_enabled=False))

    result_events = [e for e in events if isinstance(e, AdapterResult)]
    assert len(result_events) == 1
    result = result_events[0]
    assert result.raw_text == "plain note"
    assert result.care_plan is not None
    assert isinstance(result.grading, Grading)
    assert result.grading.enabled is False


def test_run_care_plan_pipeline_step_error_yields_adapter_error():
    metrics = _make_metrics()
    mock_scope = _mock_markers()

    with patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FailingPipeline()), \
         patch("routes.care_plan.Markers") as mock_markers:
        mock_markers.CarePlan.Pipeline.execute.side_effect = lambda fn: fn(mock_scope)

        events = list(run_care_plan_pipeline("text", metrics, grading_enabled=False))

    error_events = [e for e in events if isinstance(e, AdapterError)]
    assert len(error_events) == 1
