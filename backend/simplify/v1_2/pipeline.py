"""
simplify/v1_2/pipeline.py - V1.2 medical care_plan pipeline.

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

import json
import logging

from pydantic import ValidationError

from models.care_plan import (
    CARE_PLAN_VERSION,
    CarePlan,
    CarePlanV1_2,
    CarePlanV1_2StructuredLLM,
)
from simplify.interface import CarePlanPipeline
from utils.llm import LLMClient
from utils.term_detection import (
    build_glossary_from_simplified_text,
    detect_terms,
    format_abbreviations_for_prompt,
    format_medical_terms_for_prompt,
    format_substitution_candidates_for_prompt,
)

logger = logging.getLogger(__name__)

_STRUCTURING_SCHEMA = json.dumps(
    CarePlanV1_2StructuredLLM.model_json_schema(),
    indent=2,
)


class V1_2Pipeline(CarePlanPipeline):
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

        prompt = f"""You are a health literacy expert helping rewrite a provider note for a patient.

Rewrite the note so it is easier to understand at about a 6th-grade reading level.

Use these plain-language replacement suggestions when they fit naturally in context:
{sub_block}

Preserve these medical terms exactly. Do not define them inline. They will be explained separately in the UI:
{medical_block}

Expand these abbreviations when they appear:
{abbrev_block}

Rules:
1. Keep all medical facts from the source accurate.
2. Do not add diagnosis, medical advice, urgency, prognosis, or treatment interpretation.
3. Do not remove important information.
4. Use short sentences (under 20 words where possible).
5. Use active voice.
6. Use "you" and "your."
7. Do not include the patient's name, date of birth, address, insurance details, or other identifiers.
8. Do not add parenthetical definitions.
9. Do not return term annotations or spans.
10. Output only the rewritten text; no preamble, no commentary.

SOURCE NOTE:
{text}

REWRITTEN NOTE:"""
        return self._generate_text(prompt, temperature=0.3, max_tokens=16384)

    def clarify_and_action(self, text: str, abbreviations: list[dict] | None = None) -> str:
        abbreviation_section = ""
        if abbreviations:
            abbrev_list = "\n".join(
                f"- \"{a['term']}\" -> \"{a['expansion']}\""
                for a in abbreviations[:30]
            )
            abbreviation_section = f"""
If any of these abbreviations remain in the text, expand them:
{abbrev_list}
"""
        prompt = f"""You are a health literacy expert helping patients understand what they need to do.

Review the text below and:
1. Use active voice throughout.
2. Address the patient as "you."
3. Start every patient action with a clear verb: Take / Call / Schedule / Ask / Bring / Watch / Avoid / Continue / Stop.
4. Do not fabricate numbers. Do not convert vague wording into exact numbers unless the source contains the exact number.
5. Do not add urgency unless the source implies urgency.
6. Do not create new medical advice.
7. Break multi-step instructions into separate steps.
8. Output only the improved text; no commentary, no headings.
{abbreviation_section}
TEXT:
{text}

IMPROVED TEXT:"""
        return self._generate_text(prompt, temperature=0.2, max_tokens=16384)

    def structure_appointment_note(self, text: str) -> dict:
        prompt = f"""You are structuring a simplified provider note for a patient.

Return JSON only. Use this schema:
{_STRUCTURING_SCHEMA}

Rules:
1. Use only information found in the source text.
2. Do not add diagnosis, urgency, prognosis, or medical advice not in the source.
3. If the source does not contain a field, use an empty string or empty array.
4. Every medication must have a 'why' field explaining the reason for this specific patient.
5. Every warning sign must have a 'what_to_do' field: specific instruction (call doctor, go to ER, or normal side effect).
6. Classify warning sign urgency as: emergency, call_doctor, monitor, or normal_side_effect.
7. Use active voice. Address the patient as 'you'. No abbreviations.
8. Write one idea per sentence. Maximum 20 words per sentence.
9. The summary must be exactly 3 sentences: (1) why came in, (2) main conclusion, (3) most important next step.
10. Generate exactly 3 questions that help the patient understand or manage their care.
11. Put low-priority details in low_priority array.
12. Do not return term annotations or spans.
13. Output only valid JSON; no markdown, no commentary.

SOURCE TEXT:
{text}

JSON OUTPUT:"""
        raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict from structure step, got {type(raw)}")

        try:
            model = CarePlanV1_2StructuredLLM.model_validate(raw)
        except ValidationError as e:
            raise ValueError(f"LLM structure output failed validation: {e}") from e

        return model.model_dump(mode="json")

    def run(self, text: str) -> CarePlanV1_2:
        """
        Run the full V1.2 pipeline.

        Returns the typed Simplify V1.2 care-plan model.
        """
        # Deterministic detections are used to constrain rewrite behavior.
        term_data = detect_terms(text)
        substitution_candidates = term_data["substitution_candidates"]
        preserve_and_define_terms = term_data["preserve_and_define_terms"]
        abbreviations = term_data["abbreviations"]

        simplified = self.simplify_language_with_term_plan(
            text,
            substitution_candidates,
            preserve_and_define_terms,
            abbreviations,
        )
        clarified = self.clarify_and_action(simplified, abbreviations)
        structured = self.structure_appointment_note(clarified)
        # Glossary contains only preserved terms still present in final text.
        terms_glossary = build_glossary_from_simplified_text(
            clarified,
            preserve_and_define_terms,
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
        care_plan = CarePlan.from_pipeline_result(CARE_PLAN_VERSION, result)
        if not isinstance(care_plan, CarePlanV1_2):
            raise TypeError(f"Expected CarePlanV1_2, got {type(care_plan).__name__}")
        return care_plan
