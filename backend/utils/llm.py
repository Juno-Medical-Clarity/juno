"""
utils/llm.py — LLM client for Vertex AI (HIPAA-compliant path only).

Uses vertexai SDK exclusively. Google AI Studio (google-generativeai /
GEMINI_API_KEY) is not used because it is excluded from Google's HIPAA BAA.

Requires environment variables:
  GCP_PROJECT_ID  — GCP project that has Vertex AI API enabled
  GCP_LOCATION    — region (default: us-central1)
  VERTEX_AI_MODEL — model name (default: gemini-1.5-pro)
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)


def _strip_json_fences(raw: str) -> str:
    # Accept both raw JSON and markdown-fenced JSON from model outputs.
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


class LLMClient:
    """LLM client backed exclusively by Vertex AI."""

    def __init__(self, model_name: str | None = None):
        if model_name is None:
            model_name = os.environ.get("VERTEX_AI_MODEL", "gemini-1.5-pro")

        import vertexai
        from vertexai.preview.generative_models import (
            FinishReason,
            GenerationConfig as VertexGenerationConfig,
            GenerativeModel,
            HarmBlockThreshold,
            HarmCategory,
        )
        project_id = os.environ.get("GCP_PROJECT_ID", "")
        location = os.environ.get("GCP_LOCATION", "us-central1")
        vertexai.init(project=project_id, location=location)
        self._model = GenerativeModel(model_name)
        self._safety = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        }
        self._FinishReason = FinishReason
        self._VertexGenerationConfig = VertexGenerationConfig
        logger.info("LLMClient: using Vertex AI")

    def generate_text(self, prompt: str, temperature: float = 0.3, max_tokens: int = 8192) -> str:
        """Generate text from a prompt. Returns the text string directly."""
        response = self._model.generate_content(
            prompt,
            generation_config=self._VertexGenerationConfig(
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
            and candidate.finish_reason == self._FinishReason.MAX_TOKENS
        ):
            logger.warning("LLMClient: hit max tokens; proceeding with partial output")

        return response.text.strip()

    def generate_json(self, prompt: str, temperature: float = 0.2, max_tokens: int = 8192) -> dict | list:
        """Generate JSON from a prompt. Strips markdown fences and parses JSON."""
        raw = self.generate_text(prompt, temperature, max_tokens)
        try:
            return json.loads(_strip_json_fences(raw))
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}. Raw start: {raw[:200]!r}") from e
