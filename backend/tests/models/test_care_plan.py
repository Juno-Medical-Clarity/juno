"""Tests for the strict CarePlan v1.2 model family."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from models.care_plan import CarePlan
from utils.constants import Constants
from models.care_plan.versions.v1_2 import CarePlanV1_2, Diagnosis

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "care_plan_v1_2.json"


@pytest.fixture
def full_v12_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_care_plan_v1_2_round_trips_full_fixture(full_v12_fixture):
    model = CarePlanV1_2.model_validate(full_v12_fixture)

    assert model.model_dump(mode="json") == full_v12_fixture


def test_care_plan_v1_2_rejects_extra_top_level_key(full_v12_fixture):
    with pytest.raises(ValidationError):
        CarePlanV1_2.model_validate({**full_v12_fixture, "extra": "drift"})


def test_care_plan_v1_2_rejects_extra_nested_key(full_v12_fixture):
    fixture = full_v12_fixture.copy()
    fixture["medications"] = [{**fixture["medications"][0], "extra": "drift"}]

    with pytest.raises(ValidationError):
        CarePlanV1_2.model_validate(fixture)


def test_care_plan_v1_2_minimal_payload_uses_pipeline_defaults():
    model = CarePlanV1_2.model_validate(
        {"version": Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, "doc_type": "care_plan"}
    )

    assert model.version == Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value
    assert model.doc_type == "care_plan"
    assert model.urgency == "normal"
    assert model.summary == ""
    assert model.reason_for_visit == []
    assert model.diagnosis == Diagnosis()
    assert model.medications == []
    assert model.tests == []
    assert model.procedures == []
    assert model.other == []
    assert model.follow_up == []
    assert model.warning_signs == []
    assert model.questions == []
    assert model.low_priority == []
    assert model.terms == {}
    assert model.raw is None


def test_care_plan_v1_2_rejects_appointment_note_doc_type():
    with pytest.raises(ValidationError):
        CarePlanV1_2.model_validate(
            {"version": Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, "doc_type": "appointment_note"}
        )


def test_care_plan_from_dict_dispatches_to_v1_2():
    model = CarePlan.from_dict({"version": Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, "doc_type": "care_plan"})

    assert isinstance(model, CarePlanV1_2)


def test_care_plan_from_pipeline_result_merges_version_and_validates():
    model = CarePlan.from_pipeline_result(Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, {"doc_type": "care_plan"})

    assert isinstance(model, CarePlanV1_2)
    assert model.version == Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value


def test_care_plan_from_pipeline_result_validates_drift():
    with pytest.raises(ValidationError):
        CarePlan.from_pipeline_result(
            Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, {"doc_type": "care_plan", "extra": "drift"}
        )


def test_structured_llm_schema_properties_match_care_plan_structured_fields():
    from care_plan.v1_2.pipeline import _llm_schema
    from models.care_plan.versions.v1_2 import CarePlanV1_2

    care_plan_fields = set(CarePlanV1_2.model_fields)
    structured_fields = care_plan_fields - {"terms", "raw"}
    schema_properties = set(_llm_schema(CarePlanV1_2, {"terms", "raw"})["properties"])

    assert schema_properties == structured_fields
