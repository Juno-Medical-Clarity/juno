"""
SP4 Task 8 — Source-level assertions that care_plan.py uses Markers
instead of the old JunoMetrics / JunoLogger boilerplate.

These tests are "grep the source" tests and run without Flask.
"""

import pathlib

_SRC = pathlib.Path(__file__).parent.parent / "routes" / "care_plan.py"
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
