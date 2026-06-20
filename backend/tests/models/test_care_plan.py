"""Tests for the strict CarePlan v1.2 model family."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from models.care_plan import (
    CARE_PLAN_VERSION,
    CarePlan,
    CarePlanV1_2,
    CarePlanV1_2StructuredLLM,
    Diagnosis,
)


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
        {"version": CARE_PLAN_VERSION, "doc_type": "care_plan"}
    )

    assert model.version == CARE_PLAN_VERSION
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
            {"version": CARE_PLAN_VERSION, "doc_type": "appointment_note"}
        )


def test_care_plan_from_dict_dispatches_to_v1_2():
    model = CarePlan.from_dict({"version": CARE_PLAN_VERSION, "doc_type": "care_plan"})

    assert isinstance(model, CarePlanV1_2)


def test_care_plan_from_pipeline_result_merges_version_and_validates():
    model = CarePlan.from_pipeline_result(CARE_PLAN_VERSION, {"doc_type": "care_plan"})

    assert isinstance(model, CarePlanV1_2)
    assert model.version == CARE_PLAN_VERSION


def test_care_plan_from_pipeline_result_validates_drift():
    with pytest.raises(ValidationError):
        CarePlan.from_pipeline_result(
            CARE_PLAN_VERSION, {"doc_type": "care_plan", "extra": "drift"}
        )


def test_structured_llm_schema_properties_match_care_plan_structured_fields():
    care_plan_fields = set(CarePlanV1_2.model_fields)
    structured_fields = care_plan_fields - {"terms", "raw"}
    schema_properties = set(CarePlanV1_2StructuredLLM.model_json_schema()["properties"])

    assert schema_properties == structured_fields
