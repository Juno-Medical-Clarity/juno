"""
gemini_client.py — Gemini API client (Google AI Studio).

Used when GEMINI_API_KEY env var is set. Falls back to Vertex AI otherwise.
Provides the same interface as the VertexAIClient so pipeline code is unchanged.
"""

import logging
import os

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

logger = logging.getLogger(__name__)


class GeminiAPIClient:
    """Thin wrapper around google-generativeai for use in the Simplify pipeline."""

    def __init__(self, model_name: str = "gemini-1.5-flash"):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info("gemini_client: initialized with model=%s", model_name)

    def generate_content(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> str:
        """
        Generate text from a prompt. Returns the text string directly.
        """
        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        response = self.model.generate_content(prompt, generation_config=config)
        return response.text
