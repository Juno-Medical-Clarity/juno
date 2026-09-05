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
from typing import Any, Callable, Generator

from pydantic import ValidationError

from models.pipeline_events import (
    StepEvent,
    PipelineRunResult,
    PipelineStepError,
)

WrapStepFn = Callable[[int, str, Callable[[], Any]], Any]

from models.care_plan import CarePlan
from care_plan.interface import CarePlanPipeline
from models.care_plan.versions.v1_2 import CarePlanV1_2
from utils.llm import LLMClient
from utils.term_detection import (
    build_glossary_from_simplified_text,
    detect_terms,
    format_abbreviations_for_prompt,
    format_medical_terms_for_prompt,
    format_substitution_candidates_for_prompt,
)
from utils.constants import Constants
from errors import JunoError, ErrorCode

_STEP = Constants.Pipeline.PIPELINE_V1_2_STEPS

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
        temperature: float = Constants.Llm.TEMPERATURE_TEXT,
        max_tokens: int = Constants.Llm.MAX_TOKENS,
    ) -> str:
        # Delegate to shared LLM client.
        return self._llm.generate_text(prompt, temperature=temperature, max_tokens=max_tokens)

    def _generate_json(
        self,
        prompt: str,
        temperature: float = Constants.Llm.TEMPERATURE_JSON,
        max_tokens: int = Constants.Llm.MAX_TOKENS,
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
        return self._generate_text(prompt, temperature=Constants.Llm.TEMPERATURE_TEXT, max_tokens=Constants.Llm.MAX_TOKENS_LONG_FORM)

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
        return self._generate_text(prompt, temperature=Constants.Llm.TEMPERATURE_JSON, max_tokens=Constants.Llm.MAX_TOKENS_LONG_FORM)

    def structure_appointment_note(self, text: str) -> dict:
        # Long-form budget: this step emits the full structured care-plan JSON
        # (medications, tests, warning signs, etc. for the whole document), which
        # can easily exceed the default 8192-token cap on anything longer than a
        # short note. It is also the LAST LLM step, so hitting the cap here means
        # every earlier step already ran to completion before the user sees a
        # failure — use the same long-form budget as the other prose-generating
        # steps so a merely-longer (not actually huge) document doesn't fail late.
        prompt = _STRUCTURE_PROMPT.format(schema=_STRUCTURING_SCHEMA, text=text)
        raw = self._generate_json(prompt, temperature=Constants.Llm.TEMPERATURE_JSON, max_tokens=Constants.Llm.MAX_TOKENS_LONG_FORM)
        if not isinstance(raw, dict):
            raise JunoError(ErrorCode.LLM_INVALID_JSON, detail=f"expected dict, got {type(raw)}")

        try:
            model = CarePlanV1_2.model_validate(raw)
        except ValidationError as e:
            raise JunoError(ErrorCode.PIPELINE_VALIDATION_FAILED, detail=str(e), original=e)

        return model.model_dump(mode="json", exclude={"terms", "raw"})

    def iter_steps(
        self,
        text: str,
        wrap_step: WrapStepFn | None = None,
    ) -> Generator[StepEvent | PipelineRunResult | PipelineStepError, None, None]:
        """
        Run the full V1.2 pipeline, yielding step progress and the final result.

        Yields StepEvent(step, "active") before each step and StepEvent(step, "done")
        after each step. On success, yields a single PipelineRunResult. On an
        unrecoverable step failure, yields PipelineStepError and returns.

        Args:
            text:      Plain text to process.
            wrap_step: Optional hook called as wrap_step(step_num, label, fn) and
                       must return fn(). The adapter uses this to attach Markers,
                       JunoContext, and tracing spans without the pipeline importing
                       Flask or g. If None, steps are called directly.
        """

        def _call(step: int, label: str, fn: Callable[[], Any]) -> Any:
            if wrap_step is not None:
                return wrap_step(step, label, fn)
            return fn()

        # Step 2: term detection (deterministic, no LLM)
        yield StepEvent(step=_STEP.DETECT_TERMS.number, status="active", label=_STEP.DETECT_TERMS.label)
        try:
            term_data = _call(
                _STEP.DETECT_TERMS.number, _STEP.DETECT_TERMS.label,
                lambda: detect_terms(text),
            )
        except Exception:
            logger.exception("pipeline: term detection failed — continuing with empty terms")
            term_data = {
                "substitution_candidates": [],
                "preserve_and_define_terms": [],
                "abbreviations": [],
            }
        yield StepEvent(step=_STEP.DETECT_TERMS.number, status="done", label=_STEP.DETECT_TERMS.label)

        # Step 3: simplify language
        yield StepEvent(step=_STEP.SIMPLIFY_LANGUAGE.number, status="active", label=_STEP.SIMPLIFY_LANGUAGE.label)
        try:
            simplified = _call(
                _STEP.SIMPLIFY_LANGUAGE.number, _STEP.SIMPLIFY_LANGUAGE.label,
                lambda: self.simplify_language_with_term_plan(
                    text,
                    term_data["substitution_candidates"],
                    term_data["preserve_and_define_terms"],
                    term_data["abbreviations"],
                ),
            )
        except Exception as exc:
            logger.exception("pipeline: simplification failed")
            yield PipelineStepError(step=_STEP.SIMPLIFY_LANGUAGE.number, exc=exc)
            return
        yield StepEvent(step=_STEP.SIMPLIFY_LANGUAGE.number, status="done", label=_STEP.SIMPLIFY_LANGUAGE.label)

        # Step 4: clarify and action
        yield StepEvent(step=_STEP.CLARIFY_AND_ACTION.number, status="active", label=_STEP.CLARIFY_AND_ACTION.label)
        try:
            clarified = _call(
                _STEP.CLARIFY_AND_ACTION.number, _STEP.CLARIFY_AND_ACTION.label,
                lambda: self.clarify_and_action(simplified, term_data["abbreviations"]),
            )
        except Exception:
            logger.exception("pipeline: clarify step failed — using simplified text")
            clarified = simplified   # non-fatal: fall back to simplified
        yield StepEvent(step=_STEP.CLARIFY_AND_ACTION.number, status="done", label=_STEP.CLARIFY_AND_ACTION.label)

        # Step 5: structure appointment note
        yield StepEvent(step=_STEP.STRUCTURE_DOCUMENT.number, status="active", label=_STEP.STRUCTURE_DOCUMENT.label)
        try:
            structured = _call(
                _STEP.STRUCTURE_DOCUMENT.number, _STEP.STRUCTURE_DOCUMENT.label,
                lambda: self.structure_appointment_note(clarified),
            )
        except Exception as exc:
            logger.exception("pipeline: structuring failed")
            yield PipelineStepError(step=_STEP.STRUCTURE_DOCUMENT.number, exc=exc)
            return
        yield StepEvent(step=_STEP.STRUCTURE_DOCUMENT.number, status="done", label=_STEP.STRUCTURE_DOCUMENT.label)

        terms_glossary = build_glossary_from_simplified_text(
            clarified, term_data["preserve_and_define_terms"]
        )
        result = {
            **structured,
            "terms": terms_glossary,
            "raw": {
                "text": text,
                "simplified_text": simplified,
                "clarified_text": clarified,
            },
        }
        care_plan = CarePlan.from_pipeline_result(Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, result)
        if not isinstance(care_plan, CarePlanV1_2):
            raise TypeError(f"Expected CarePlanV1_2, got {type(care_plan).__name__}")

        yield PipelineRunResult(
            care_plan=care_plan,
            term_data=term_data,
            simplified=simplified,
            clarified=clarified,
            raw_text=text,
        )

    def run(self, text: str) -> CarePlanV1_2:
        """Run the full pipeline without instrumentation. Used in tests and batch pre-checks."""
        for event in self.iter_steps(text):
            if isinstance(event, PipelineRunResult):
                return event.care_plan
            if isinstance(event, PipelineStepError):
                raise event.exc
        raise RuntimeError("iter_steps completed without yielding a result")
