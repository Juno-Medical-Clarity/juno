"""
interface.py - Base class for all care_plan pipeline versions.

To add a new version:
1. Create simplify/v<X>/ with __init__.py and pipeline.py
2. Subclass CarePlanPipeline, implement run()
3. Register the pipeline in routes/care_plan.py
"""

from abc import ABC, abstractmethod


class CarePlanPipeline(ABC):
    """
    Contract for all care_plan pipeline versions.

    Each version must implement run(text) -> dict where the returned dict
    matches the version's appointment schema. The 'version' key must be set.
    """

    @abstractmethod
    def run(self, text: str) -> "CarePlan":
        """
        Run the full pipeline on the input text.

        Args:
            text: Plain text extracted from the input document.

        Returns:
            Structured output dict conforming to the version schema.
        """
        pass
