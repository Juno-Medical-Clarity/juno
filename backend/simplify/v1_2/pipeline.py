"""
simplify/v1_2/pipeline.py - V1.2 medical document simplification pipeline.

Implements SimplifyPipeline. Key differences from V1:
  - Deterministic term detection (AHRQ + Michigan + abbreviations) via JSON
  - No lab result support; appointment/SOAP notes only
  - No document classification LLM call
  - No scispaCy dependency
  - No parenthetical definitions in prose; compact terms glossary in output
  - Simplify V1.2 appointment_note output, plus "terms" key

Steps:
  1. detect_terms
  2. simplify_language
  3. clarify_and_action
  4. structure_document
  5. postprocess
"""

import json
import logging
import os
import re
from pathlib import Path

import vertexai
from vertexai.preview.generative_models import (
    FinishReason,
    GenerationConfig,
    GenerativeModel,
    HarmBlockThreshold,
    HarmCategory,
)

from simplify.interface import SimplifyPipeline
from utils.scoring import score_text
from utils.term_detection import (
    build_glossary_from_simplified_text,
    detect_terms,
    format_abbreviations_for_prompt,
    format_medical_terms_for_prompt,
    format_substitution_candidates_for_prompt,
)

logger = logging.getLogger(__name__)

_STRUCTURING_SCHEMA_PATH = Path(__file__).with_name("appointment.schema.json")
_STRUCTURING_SCHEMA = json.dumps(
    json.loads(_STRUCTURING_SCHEMA_PATH.read_text(encoding="utf-8")),
    indent=2,
)


def _strip_json_fences(raw: str) -> str:
    # Accept both raw JSON and markdown-fenced JSON from model outputs.
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


class V1_2Pipeline(SimplifyPipeline):
    """V1.2 simplification pipeline with deterministic term detection."""

    def __init__(self):
        # Environment-driven model config keeps deployment/runtime configurable.
        project_id = os.environ.get("GCP_PROJECT_ID", "")
        location = os.environ.get("GCP_LOCATION", "us-central1")
        model_name = os.environ.get("VERTEX_AI_MODEL", "gemini-1.5-pro")

        vertexai.init(project=project_id, location=location)
        self._model = GenerativeModel(model_name)
        # Safety blocking is disabled for deterministic backend handling; downstream
        # validation and prompt constraints enforce output shape/content.
        self._safety = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        }

    def _generate_text(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> str:
        # Shared low-level model call used by all text-producing stages.
        response = self._model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
            safety_settings=self._safety,
        )
        if not response.candidates:
            raise RuntimeError("Model response blocked or no candidates")

        candidate = response.candidates[0]
        if (
            hasattr(candidate, "finish_reason")
            and candidate.finish_reason == FinishReason.MAX_TOKENS
        ):
            # Partial output can still be useful; caller handles downstream parsing.
            logger.warning("V1_2Pipeline: hit max tokens; proceeding with partial output")

        return response.text.strip()

    def _generate_json(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> dict | list:
        # Centralized JSON parsing path so fence handling stays consistent.
        raw = self._generate_text(prompt, temperature, max_tokens)
        try:
            return json.loads(_strip_json_fences(raw))
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}. Raw start: {raw[:200]!r}") from e

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

        # Backfill missing keys to keep response shape stable for API clients.
        defaults = {
            "doc_type": "appointment_note",
            "urgency": "normal",
            "version": "1.2",
            "summary": "",
            "reason_for_visit": [],
            "diagnosis": {"main_conclusion": "", "changed_since_last_visit": "", "details": []},
            "medications": [],
            "tests": [],
            "procedures": [],
            "other": [],
            "follow_up": [],
            "warning_signs": [],
            "questions": [],
            "low_priority": [],
        }
        for key, value in defaults.items():
            if key not in raw:
                raw[key] = value

        raw["doc_type"] = "appointment_note"
        raw["version"] = "1.2"
        return raw

    def run(self, text: str) -> dict:
        """
        Run the full V1.2 pipeline.

        Returns the Simplify V1.2 appointment_note JSON shape, plus a terms glossary.
        """
        # Readability score before rewrite for quality telemetry.
        before_score = score_text(text)

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
        # Readability score after rewrite for before/after comparison.
        after_score = score_text(clarified)
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
        if before_score is not None:
            result["before_score"] = before_score
        if after_score is not None:
            result["after_score"] = after_score
        return result
