"""Tests for the strict internal care-plan envelope model."""

import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.care_plan_versions.v1_2 import CarePlanV1_2
from models.grading import Grading
from models.input import TextInput
from models.metrics import Metrics


def _metrics() -> Metrics:
    return Metrics(
        session_id="session-1",
        pipeline_version="v1-2",
        input_type="text",
        created_at="2026-06-20T00:00:00+00:00",
    )


def _care_plan() -> CarePlanV1_2:
    return CarePlanV1_2(
        summary="Take blood pressure medicine daily.",
        terms={
            "hypertension": {
                "definition": "High blood pressure.",
                "source": "provider note",
            }
        },
    )


def _envelope_dict() -> dict:
    return {
        "metrics": _metrics().to_dict(),
        "input": TextInput(text="Patient note").to_dict(),
        "grading": Grading().to_dict(),
        "care_plan": _care_plan().to_dict(),
    }


def test_care_plan_internal_serializes_with_care_plan_key_and_scores_absent():
    from models.envelope import CarePlanInternal

    model = CarePlanInternal(
        metrics=_metrics(),
        input=TextInput(text="Patient note"),
        grading=Grading(),
        care_plan=_care_plan(),
    )

    data = model.to_dict()

    assert set(data) == {
        "metrics",
        "input",
        "grading",
        "care_plan",
    }
    assert "before_score" not in data
    assert "after_score" not in data
    assert "simplified_care_plan" not in data
    assert "before_score" not in data["care_plan"]
    assert "after_score" not in data["care_plan"]


def test_care_plan_internal_rejects_extra_score_kwargs():
    from models.envelope import CarePlanInternal

    with pytest.raises((ValidationError, TypeError)):
        CarePlanInternal(
            metrics=_metrics(),
            input=TextInput(text="Patient note"),
            grading=Grading(),
            care_plan=_care_plan(),
            before_score={"composite": 60},
            after_score={"composite": 90},
        )


def test_care_plan_internal_from_dict_requires_care_plan_key_without_alias():
    from models.envelope import CarePlanInternal

    legacy_key_payload = {
        **_envelope_dict(),
        "simplified_care_plan": _care_plan().to_dict(),
    }
    legacy_key_payload.pop("care_plan")

    with pytest.raises(ValidationError):
        CarePlanInternal.from_dict(legacy_key_payload)


def test_care_plan_internal_scores_are_absent_from_envelope():
    from models.envelope import CarePlanInternal

    model = CarePlanInternal(
        metrics=_metrics(),
        input=TextInput(text="Patient note"),
        grading=Grading(),
        care_plan=_care_plan(),
    )
    data = model.to_dict()

    assert "before_score" not in data
    assert "after_score" not in data
    assert "before_score" not in data["care_plan"]
    assert "after_score" not in data["care_plan"]


def test_simplify_output_import_fails():
    envelope = importlib.import_module("models.envelope")

    with pytest.raises(ImportError):
        from models.envelope import SimplifyOutput  # noqa: F401

    assert not hasattr(envelope, "SimplifyOutput")


def test_model_consuming_routes_import_without_removed_aliases():
    import routes.batch  # noqa: F401
    import routes.care_plan  # noqa: F401
    import routes.grading  # noqa: F401
    import routes.saved_outputs  # noqa: F401

    routes_dir = Path(__file__).resolve().parents[2] / "routes"
    for route_file in routes_dir.glob("*.py"):
        text = route_file.read_text()
        assert "SimplifiedCarePlan" not in text
        assert "SimplifyOutput" not in text
        assert "simplified_care_plan" not in text
