"""SimplifyOutput envelope — top-level output shape for the simplify pipeline."""

from dataclasses import dataclass

from backend.models.base import JsonModel
from backend.models.care_plan import SimplifiedCarePlan
from backend.models.grading import Grading
from backend.models.input import Input
from backend.models.metrics import Metrics


@dataclass
class SimplifyOutput(JsonModel):
    """Top-level output envelope for the simplify pipeline.

    Wraps all pipeline outputs (metrics, input, grading, simplified_care_plan)
    into a single serialisable structure matching PRD §5 "After" shape.
    """

    metrics: Metrics
    input: Input
    grading: Grading
    simplified_care_plan: SimplifiedCarePlan

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics.to_dict(),
            "input": self.input.to_dict(),
            "grading": self.grading.to_dict(),
            "simplified_care_plan": self.simplified_care_plan.to_dict(),
        }


def is_legacy_shape(data: dict) -> bool:
    """Return True if *data* lacks the new-style 'simplified_care_plan' top-level key.

    Used to distinguish legacy flat outputs from the structured envelope format.
    """
    return "simplified_care_plan" not in data
