"""
care_plan/v1_2/pipeline.py - V1.2 medical care_plan pipeline.

Implements CarePlanPipeline. Key differences from V1:
  - Deterministic term detection (AHRQ + Michigan + abbreviations) via JSON
  - No lab result support; appointment/SOAP notes only
  - No document classification LLM call
  - No scispaCy dependency
  - No parenthetical definitions in prose; compact terms glossary in output
  - Care plan V1.2 appointment_note output, plus "terms" key

Steps:
  1. detect_terms
  2. simplify_language
  3. clarify_and_action
  4. structure_document
  5. postprocess
"""

import copy
import json
import logging
from pathlib import Path

from pydantic import ValidationError

from models.care_plan import CarePlan
from care_plan.interface import CarePlanPipeline
from models.care_plan_versions.v1_2 import CarePlanV1_2
from utils.llm import LLMClient
from utils.term_detection import (
    build_glossary_from_simplified_text,
    detect_terms,
    format_abbreviations_for_prompt,
    format_medical_terms_for_prompt,
    format_substitution_candidates_for_prompt,
)
from utils.constants import Constants

logger = logging.getLogger(__name__)


def _llm_schema(model_cls, exclude: set[str]) -> dict:
    """Generate a JSON schema from model_cls with the given field names excluded."""
    schema = copy.deepcopy(model_cls.model_json_schema())
    props = schema.get("properties", {})
    for field in exclude:
        props.pop(field, None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in exclude]
    return schema


_STRUCTURING_SCHEMA = json.dumps(
    _llm_schema(CarePlanV1_2, exclude={"terms", "raw", "note"}),
    indent=2,
)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_SIMPLIFY_PROMPT  = (_PROMPTS_DIR / "simplify_language.txt").read_text(encoding="utf-8")
_CLARIFY_PROMPT   = (_PROMPTS_DIR / "clarify_and_action.txt").read_text(encoding="utf-8")
_STRUCTURE_PROMPT = (_PROMPTS_DIR / "structure_note.txt").read_text(encoding="utf-8")


class CarePlanV1_2Pipeline(CarePlanPipeline):
    """V1.2 care_plan pipeline with deterministic term detection."""

    def __init__(self):
        self._llm = LLMClient()

    def _generate_text(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> str:
        # Delegate to shared LLM client.
        return self._llm.generate_text(prompt, temperature=temperature, max_tokens=max_tokens)

    def _generate_json(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> dict | list:
        # Delegate to shared LLM client (includes fence-stripping and JSON parsing).
        return self._llm.generate_json(prompt, temperature=temperature, max_tokens=max_tokens)

    def simplify_language_with_term_plan(
        self,
        text: str,
        substitution_candidates: list[dict],
        preserve_and_define_terms: list[dict],
        abbreviations: list[dict],
    ) -> str:
        # Pre-format deterministic term detections into compact prompt sections.
        sub_block = format_substitution_candidates_for_prompt(substitution_candidates)
        medical_block = format_medical_terms_for_prompt(preserve_and_define_terms)
        abbrev_block = format_abbreviations_for_prompt(abbreviations)

        prompt = _SIMPLIFY_PROMPT.format(
            sub_block=sub_block,
            medical_block=medical_block,
            abbrev_block=abbrev_block,
            text=text,
        )
        return self._generate_text(prompt, temperature=0.3, max_tokens=65536)

    def clarify_and_action(self, text: str, abbreviations: list[dict] | None = None) -> str:
        abbreviation_section = ""
        if abbreviations:
            abbrev_list = "\n".join(
                f"- \"{a['term']}\" -> \"{a['expansion']}\""
                for a in abbreviations[:30]
            )
            abbreviation_section = (
                f"\nIf any of these abbreviations remain in the text, expand them:\n{abbrev_list}\n"
            )
        prompt = _CLARIFY_PROMPT.format(
            abbreviation_section=abbreviation_section,
            text=text,
        )
        return self._generate_text(prompt, temperature=0.2, max_tokens=65536)

    def structure_appointment_note(self, text: str) -> dict:
        prompt = _STRUCTURE_PROMPT.format(schema=_STRUCTURING_SCHEMA, text=text)
        raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict from structure step, got {type(raw)}")

        try:
            model = CarePlanV1_2.model_validate(raw)
        except ValidationError as e:
            raise ValueError(f"LLM structure output failed validation: {e}") from e

        return model.model_dump(mode="json", exclude={"terms", "raw"})

    def run(self, text: str) -> CarePlanV1_2:
        """
        Run the full V1.2 pipeline.

        Returns the typed Simplify V1.2 care-plan model.
        """
        # Deterministic detections are used to constrain rewrite behavior.
        term_data = detect_terms(text)

        simplified = self.simplify_language_with_term_plan(
            text,
            term_data["substitution_candidates"],
            term_data["preserve_and_define_terms"],
            term_data["abbreviations"],
        )
        clarified = self.clarify_and_action(simplified, term_data["abbreviations"])
        structured = self.structure_appointment_note(clarified)
        # Glossary contains only preserved terms still present in final text.
        terms_glossary = build_glossary_from_simplified_text(
            clarified,
            term_data["preserve_and_define_terms"],
        )

        # Merge structured output with deterministic glossary, intermediary raw data,
        # and optional scores.
        result = {
            **structured,
            "terms": terms_glossary,
            "raw": {
                "text": text,
                "simplified_text": simplified,
                "clarified_text": clarified,
            },
        }
        care_plan = CarePlan.from_pipeline_result(Constants.CARE_PLAN_VERSIONS.V1_2.value, result)
        if not isinstance(care_plan, CarePlanV1_2):
            raise TypeError(f"Expected CarePlanV1_2, got {type(care_plan).__name__}")
        return care_plan
