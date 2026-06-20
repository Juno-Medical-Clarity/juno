"""Focused tests for the v1.2 pipeline's Pydantic schema boundary."""

import json

import pytest

from models.care_plan import CARE_PLAN_VERSION, CarePlanV1_2
from simplify.v1_2 import pipeline as pipeline_module
from simplify.v1_2.pipeline import V1_2Pipeline


def test_structuring_schema_is_generated_from_structured_llm_model():
    schema = json.loads(pipeline_module._STRUCTURING_SCHEMA)

    assert schema["properties"]["doc_type"]["default"] == "care_plan"
    assert "summary" in schema["properties"]
    assert "medications" in schema["properties"]


def test_structure_appointment_note_validates_and_returns_json_model_dump():
    pipeline = V1_2Pipeline.__new__(V1_2Pipeline)
    pipeline._generate_json = lambda *args, **kwargs: {"summary": "You came in for care."}

    structured = pipeline.structure_appointment_note("clarified text")

    assert structured["doc_type"] == "care_plan"
    assert structured["version"] == CARE_PLAN_VERSION
    assert structured["summary"] == "You came in for care."
    assert structured["reason_for_visit"] == []


def test_structure_appointment_note_rejects_extra_llm_key():
    pipeline = V1_2Pipeline.__new__(V1_2Pipeline)
    pipeline._generate_json = lambda *args, **kwargs: {
        "summary": "You came in for care.",
        "unexpected": "drift",
    }

    with pytest.raises(ValueError, match="LLM structure output failed validation"):
        pipeline.structure_appointment_note("clarified text")


def test_run_returns_care_plan_model_without_internal_scores(monkeypatch):
    pipeline = V1_2Pipeline.__new__(V1_2Pipeline)

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
        "version": CARE_PLAN_VERSION,
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
