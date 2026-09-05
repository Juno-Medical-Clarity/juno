"""Focused tests for the v1.2 pipeline's Pydantic schema boundary."""

import json

import pytest

from care_plan.v1_2 import pipeline as pipeline_module
from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
from errors import JunoError, ErrorCode
from models.care_plan.versions.v1_2 import CarePlanV1_2
from utils.constants import Constants
from care_plan.v1_2.pipeline import _llm_schema


def test_structuring_schema_is_generated_from_structured_llm_model():
    schema = json.loads(pipeline_module._STRUCTURING_SCHEMA)

    assert schema["properties"]["doc_type"]["default"] == "care_plan"
    assert "summary" in schema["properties"]
    assert "medications" in schema["properties"]


def test_structure_appointment_note_validates_and_returns_json_model_dump():
    pipeline = CarePlanV1_2Pipeline.__new__(CarePlanV1_2Pipeline)
    pipeline._generate_json = lambda *args, **kwargs: {"summary": "You came in for care."}

    structured = pipeline.structure_appointment_note("clarified text")

    assert structured["doc_type"] == "care_plan"
    assert structured["version"] == Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value
    assert structured["summary"] == "You came in for care."
    assert structured["reason_for_visit"] == []


def test_structure_appointment_note_uses_long_form_token_budget():
    """Regression: structure_appointment_note is the last LLM step and emits a
    full structured JSON care plan, so it must use MAX_TOKENS_LONG_FORM (like
    simplify_language_with_term_plan and clarify_and_action) rather than the
    default MAX_TOKENS -- using the smaller default was the root cause of a
    2-page document failing with a misleading "too long" error only after
    every earlier pipeline step had already completed."""
    pipeline = CarePlanV1_2Pipeline.__new__(CarePlanV1_2Pipeline)
    captured_kwargs = {}

    def _fake_generate_json(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {"summary": "You came in for care."}

    pipeline._generate_json = _fake_generate_json
    pipeline.structure_appointment_note("clarified text")

    assert captured_kwargs["max_tokens"] == Constants.Llm.MAX_TOKENS_LONG_FORM


def test_structure_appointment_note_rejects_extra_llm_key():
    pipeline = CarePlanV1_2Pipeline.__new__(CarePlanV1_2Pipeline)
    pipeline._generate_json = lambda *args, **kwargs: {
        "summary": "You came in for care.",
        "unexpected": "drift",
    }

    with pytest.raises(JunoError) as exc_info:
        pipeline.structure_appointment_note("clarified text")
    assert exc_info.value.error_code == ErrorCode.PIPELINE_VALIDATION_FAILED


def test_run_returns_care_plan_model_without_internal_scores(monkeypatch):
    pipeline = CarePlanV1_2Pipeline.__new__(CarePlanV1_2Pipeline)

    monkeypatch.setattr(
        pipeline_module,
        "detect_terms",
        lambda text: {
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        },
    )
    monkeypatch.setattr(
        pipeline_module,
        "build_glossary_from_simplified_text",
        lambda clarified, terms: {},
    )
    pipeline.simplify_language_with_term_plan = lambda *args: "simplified"
    pipeline.clarify_and_action = lambda simplified, abbreviations: "clarified"
    pipeline.structure_appointment_note = lambda clarified: {
        "doc_type": "care_plan",
        "version": Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value,
        "summary": "You came in for care.",
    }

    care_plan = pipeline.run("original note")

    assert isinstance(care_plan, CarePlanV1_2)
    data = care_plan.model_dump(mode="json")
    assert data["raw"] == {
        "text": "original note",
        "simplified_text": "simplified",
        "clarified_text": "clarified",
    }
    assert "before_score" not in data
    assert "after_score" not in data


def test_llm_schema_excludes_terms_and_raw():
    schema = _llm_schema(CarePlanV1_2, {"terms", "raw"})
    props = schema["properties"]

    assert "terms" not in props
    assert "raw" not in props
    expected = set(CarePlanV1_2.model_fields) - {"terms", "raw"}
    assert set(props) == expected


def test_llm_schema_excludes_note():
    schema = _llm_schema(CarePlanV1_2, {"terms", "raw", "note"})
    assert "note" not in schema["properties"]


def test_llm_schema_model_validate_without_terms_and_raw():
    model = CarePlanV1_2.model_validate(
        {"doc_type": "care_plan", "version": "1.2", "summary": "You came in for care."}
    )
    dumped = model.model_dump(mode="json", exclude={"terms", "raw"})

    assert "terms" not in dumped
    assert "raw" not in dumped
    assert dumped["summary"] == "You came in for care."
