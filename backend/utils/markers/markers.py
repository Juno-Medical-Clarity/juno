from __future__ import annotations
from .marker import CodeMarker, code_marker


class Markers:
    """Juno operation registry. Each leaf's name() is the emitted metric name."""

    class CarePlan:
        @code_marker("care_plan.read_input")
        class ReadInput(CodeMarker): pass

        @code_marker("care_plan.find_medical_terms")
        class FindMedicalTerms(CodeMarker): pass

        @code_marker("care_plan.simplify_language")
        class SimplifyLanguage(CodeMarker): pass

        @code_marker("care_plan.clarify_actions")
        class ClarifyActions(CodeMarker): pass

        @code_marker("care_plan.structure_note")
        class StructureNote(CodeMarker): pass

        @code_marker("care_plan.save_output")
        class SaveOutput(CodeMarker): pass

        @code_marker("care_plan.pipeline")
        class Pipeline(CodeMarker): pass

    class Grading:
        @code_marker("grading.run")
        class Run(CodeMarker): pass

    class Http:
        @code_marker("http.request")
        class Request(CodeMarker): pass
