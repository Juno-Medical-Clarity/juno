"""
interface.py - Base class for all care_plan pipeline versions.

To add a new version:
1. Create care_plan/v<X>/ with __init__.py and pipeline.py
2. Subclass CarePlanPipeline, implement run()
3. Register the pipeline in routes/care_plan.py
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Generator

if TYPE_CHECKING:
    from models.pipeline_events import StepEvent, PipelineRunResult, PipelineStepError
    WrapStepFn = Callable[[int, str, Callable[[], Any]], Any]


class CarePlanPipeline(ABC):
    """
    Contract for all care plan pipeline versions.

    Each version must implement run(text) returning the typed CarePlan model.
    Versions that support step-level progress should override iter_steps();
    the default falls back to run() and yields a single PipelineRunResult.
    """

    @abstractmethod
    def run(self, text: str) -> "CarePlan":
        """Run the full pipeline; returns typed CarePlan. No instrumentation."""
        pass

    def iter_steps(
        self,
        text: str,
        wrap_step: "WrapStepFn | None" = None,
    ) -> "Generator[StepEvent | PipelineRunResult | PipelineStepError, None, None]":
        """
        Default: delegates to run() without emitting step events.
        Subclasses override this to yield StepEvent progress.
        """
        from models.pipeline_events import PipelineRunResult, PipelineStepError
        try:
            care_plan = self.run(text)
            yield PipelineRunResult(
                care_plan=care_plan,
                term_data={},
                simplified="",
                clarified="",
                raw_text=text,
            )
        except Exception as exc:
            yield PipelineStepError(step=None, exc=exc)
