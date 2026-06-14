"""
interface.py — Base class for all Simplify pipeline versions.

To add a new version:
1. Create simplify/v<X>/ with __init__.py and pipeline.py
2. Subclass SimplifyPipeline, implement run()
3. Create routes/simplify_v<X>.py with one SSE route
4. Register the blueprint in routes/__init__.py
"""

from abc import ABC, abstractmethod


class SimplifyPipeline(ABC):
    """
    Contract for all Simplify pipeline versions.

    Each version must implement run(text) -> dict where the returned dict
    matches the version's appointment schema. The 'version' key must be set.
    """

    @abstractmethod
    def run(self, text: str) -> dict:
        """
        Run the full pipeline on the input text.

        Args:
            text: Plain text extracted from the input document.

        Returns:
            Structured output dict conforming to the version schema.
        """
        pass
