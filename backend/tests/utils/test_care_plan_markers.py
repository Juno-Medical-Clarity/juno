"""
SP4 Task 8 — Source-level assertions that care_plan.py uses Markers
instead of the old JunoMetrics / JunoLogger boilerplate.

These tests are "grep the source" tests and run without Flask.
"""

import pathlib
from unittest.mock import MagicMock, patch

import pytest

_SRC = pathlib.Path(__file__).parent.parent.parent / "routes" / "care_plan.py"
_SOURCE = _SRC.read_text()


def test_no_juno_metrics_in_care_plan():
    assert "JunoMetrics" not in _SOURCE, "JunoMetrics must not appear in care_plan.py"


def test_no_log_step_in_care_plan():
    assert "log_step" not in _SOURCE, "log_step must not appear in care_plan.py"


def test_no_monotonic_ms_in_care_plan():
    assert "monotonic_ms" not in _SOURCE, "monotonic_ms must not appear in care_plan.py"


def test_no_step_durations_ms_in_care_plan():
    assert "step_durations_ms" not in _SOURCE, "step_durations_ms must not appear in care_plan.py"


def test_version_constants_imported():
    assert "CARE_PLAN_VERSION" in _SOURCE, "CARE_PLAN_VERSION must be imported in care_plan.py"
    assert "GRADING_VERSION" in _SOURCE, "GRADING_VERSION must be imported in care_plan.py"
    assert "INPUT_VERSION" in _SOURCE, "INPUT_VERSION must be imported in care_plan.py"


def test_markers_used():
    assert "Markers.CarePlan" in _SOURCE, "Markers.CarePlan must be used in care_plan.py"


# ---------------------------------------------------------------------------
# 8a — Three new source-level assertions
# ---------------------------------------------------------------------------

def test_grading_run_marker_called():
    assert "Markers.Grading.Run" in _SOURCE, \
        "Markers.Grading.Run must be called in care_plan.py"


def test_is_batch_param_present():
    assert "is_batch" in _SOURCE, \
        "is_batch parameter must appear in care_plan.py"


def test_source_kind_param_in_pipeline():
    assert "source_kind" in _SOURCE, \
        "source_kind must be added to run_care_plan_pipeline"


# ---------------------------------------------------------------------------
# 8b — Pipeline marker InMemorySink tests
# ---------------------------------------------------------------------------

def _make_pipeline_stub():
    """Return a minimal CarePlanV1_2Pipeline stub with iter_steps support."""
    from models.pipeline_events import PipelineRunResult, StepEvent

    stub = MagicMock()
    care_plan_mock = MagicMock()

    def fake_iter_steps(text, wrap_step=None):
        for step in (2, 3, 4, 5):
            yield StepEvent(step=step, status="active", label=f"Step {step}")
            if wrap_step is not None:
                # Call wrap_step so Markers get triggered for each step
                wrap_step(step, f"Step {step}", lambda s=step: {
                    "substitution_candidates": [],
                    "preserve_and_define_terms": [],
                    "abbreviations": [],
                } if s == 2 else "output")
            yield StepEvent(step=step, status="done", label=f"Step {step}")
        yield PipelineRunResult(
            care_plan=care_plan_mock,
            term_data={
                "substitution_candidates": [],
                "preserve_and_define_terms": [],
                "abbreviations": [],
            },
            simplified="simplified text",
            clarified="clarified text",
            raw_text=text,
        )

    stub.iter_steps.side_effect = fake_iter_steps
    return stub, care_plan_mock


def _make_grading_stub(n_methods=6):
    """Return a Grading stub with n_methods named entries + 'combined'."""
    from models.grading import Grading, GradingEntry
    method_names = ["smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci"][:n_methods]
    entries = []
    for name in method_names:
        for target in ("before", "after"):
            entries.append(GradingEntry(name=name, target=target, grade=75.0))
    entries.append(GradingEntry(name="combined", target="after", grade=80.0))
    return Grading(entries=entries)


def _exhaust(gen):
    """Exhaust a generator, returning all yielded values."""
    return list(gen)


@pytest.fixture(autouse=False)
def _clean_sink():
    """Ensure the marker sink is restored after each InMemorySink test."""
    from utils.markers import register_sink
    yield
    register_sink(None)


def test_pipeline_marker_has_source_kind_grading_enabled_is_batch(_clean_sink):
    """run_care_plan_pipeline fires care_plan.pipeline with source_kind, grading_enabled, is_batch."""
    from utils.markers import InMemorySink, register_sink
    from models.metrics import Metrics
    from routes.care_plan import run_care_plan_pipeline

    sink = InMemorySink()
    register_sink(sink)

    metrics = Metrics.start("sess-1", "v1-2", "text")
    pipeline_stub, _ = _make_pipeline_stub()
    grading_stub = _make_grading_stub()

    with (
        patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=pipeline_stub),
        patch("routes.care_plan._score_or_none", return_value={"composite": 72.5, "dimensions": {}}),
        patch("routes.care_plan.build_grading", return_value=grading_stub),
    ):
        _exhaust(run_care_plan_pipeline(
            "some medical text",
            metrics,
            grading_enabled=True,
            source_kind="upload",
            is_batch=False,
        ))

    pipeline_events = [e for e in sink.events if e["name"] == "care_plan.pipeline"]
    assert pipeline_events, "No care_plan.pipeline event found"
    dims = pipeline_events[0]["dimensions"]
    assert dims.get("source_kind") == "upload", f"Expected source_kind='upload', got {dims.get('source_kind')!r}"
    assert dims.get("grading_enabled") is True, f"Expected grading_enabled=True, got {dims.get('grading_enabled')!r}"
    assert dims.get("is_batch") is False, f"Expected is_batch=False, got {dims.get('is_batch')!r}"


def test_pipeline_marker_batch_dimensions(_clean_sink):
    """Dimensions track passed values — source_kind=batch_dataset, is_batch=True."""
    from utils.markers import InMemorySink, register_sink
    from models.metrics import Metrics
    from routes.care_plan import run_care_plan_pipeline

    sink = InMemorySink()
    register_sink(sink)

    metrics = Metrics.start("sess-2", "v1-2", "text")
    pipeline_stub, _ = _make_pipeline_stub()

    with (
        patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=pipeline_stub),
        patch("routes.care_plan._score_or_none", return_value=None),
        patch("routes.care_plan.build_grading", return_value=MagicMock()),
    ):
        _exhaust(run_care_plan_pipeline(
            "batch medical text",
            metrics,
            grading_enabled=False,
            source_kind="batch_dataset",
            is_batch=True,
        ))

    pipeline_events = [e for e in sink.events if e["name"] == "care_plan.pipeline"]
    assert pipeline_events, "No care_plan.pipeline event found"
    dims = pipeline_events[0]["dimensions"]
    assert dims.get("source_kind") == "batch_dataset", f"Expected source_kind='batch_dataset', got {dims.get('source_kind')!r}"
    assert dims.get("grading_enabled") is False, f"Expected grading_enabled=False, got {dims.get('grading_enabled')!r}"
    assert dims.get("is_batch") is True, f"Expected is_batch=True, got {dims.get('is_batch')!r}"


# ---------------------------------------------------------------------------
# 8c — Read-input marker dimensions (source-level)
# ---------------------------------------------------------------------------

def test_file_count_in_source():
    assert "file_count" in _SOURCE, "file_count dimension must appear in care_plan.py"


def test_file_types_in_source():
    assert "file_types" in _SOURCE, "file_types dimension must appear in care_plan.py"


# ---------------------------------------------------------------------------
# 8d — Find-medical-terms marker dimensions (source-level)
# ---------------------------------------------------------------------------

def test_term_count_in_source():
    assert "term_count" in _SOURCE, "term_count dimension must appear in care_plan.py"


def test_substitution_count_in_source():
    assert "substitution_count" in _SOURCE, "substitution_count dimension must appear in care_plan.py"


# ---------------------------------------------------------------------------
# 8e — Grading.Run marker InMemorySink tests
# ---------------------------------------------------------------------------

def test_grading_run_marker_fired_when_grading_enabled(_clean_sink):
    """Markers.Grading.Run fires with before/after composite and method count."""
    from utils.markers import InMemorySink, register_sink
    from models.metrics import Metrics
    from routes.care_plan import run_care_plan_pipeline

    sink = InMemorySink()
    register_sink(sink)

    metrics = Metrics.start("sess-3", "v1-2", "text")
    pipeline_stub, _ = _make_pipeline_stub()
    grading_stub = _make_grading_stub(n_methods=6)

    with (
        patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=pipeline_stub),
        patch("routes.care_plan._score_or_none", return_value={"composite": 85.0, "dimensions": {}}),
        patch("routes.care_plan.build_grading", return_value=grading_stub),
    ):
        _exhaust(run_care_plan_pipeline(
            "text for grading",
            metrics,
            grading_enabled=True,
            source_kind="upload",
            is_batch=False,
        ))

    grading_events = [e for e in sink.events if e["name"] == "grading.run"]
    assert grading_events, "No grading.run event found — Markers.Grading.Run did not fire"
    dims = grading_events[0]["dimensions"]
    assert "before_composite" in dims, "grading.run event missing before_composite dimension"
    assert "after_composite" in dims, "grading.run event missing after_composite dimension"
    assert "grading_method_count" in dims, "grading.run event missing grading_method_count dimension"
    assert dims["grading_method_count"] == 6, \
        f"Expected grading_method_count=6, got {dims['grading_method_count']!r}"


def test_grading_run_marker_not_fired_when_grading_disabled(_clean_sink):
    """Markers.Grading.Run must not fire when grading_enabled=False."""
    from utils.markers import InMemorySink, register_sink
    from models.metrics import Metrics
    from routes.care_plan import run_care_plan_pipeline

    sink = InMemorySink()
    register_sink(sink)

    metrics = Metrics.start("sess-4", "v1-2", "text")
    pipeline_stub, _ = _make_pipeline_stub()

    with (
        patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=pipeline_stub),
        patch("routes.care_plan._score_or_none", return_value=None),
        patch("routes.care_plan.build_grading", return_value=MagicMock()),
    ):
        _exhaust(run_care_plan_pipeline(
            "text without grading",
            metrics,
            grading_enabled=False,
            source_kind="upload",
            is_batch=False,
        ))

    grading_events = [e for e in sink.events if e["name"] == "grading.run"]
    assert not grading_events, \
        f"grading.run marker fired unexpectedly when grading_enabled=False: {grading_events}"


# ---------------------------------------------------------------------------
# 8f — Batch route source-level check
# ---------------------------------------------------------------------------

def test_batch_passes_is_batch_true_and_source_kind():
    """worker.py passes is_batch and source_kind (incl. 'batch_dataset') to run_care_plan_pipeline."""
    worker_src = pathlib.Path(__file__).parent.parent.parent / "routes" / "worker.py"
    worker_source = worker_src.read_text()
    # The pipeline is called with the dynamic is_batch kwarg derived from _is_batch_item.
    assert "is_batch=is_batch" in worker_source
    # 'batch_dataset' must remain a recognised source_kind value in the worker.
    assert "batch_dataset" in worker_source
