"""
tests/test_llm.py — Tests for utils/llm.py (LLMClient).

Covers:
  1. Gemini API path selection and generate_text
  2. Vertex AI path selection, safety settings, generate_text with MAX_TOKENS warning
  3. generate_json: fenced JSON, raw JSON, invalid JSON
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class TestLLMClientGeminiPath(unittest.TestCase):
    """LLMClient selects Gemini API when GEMINI_API_KEY is set."""

    def setUp(self):
        # Patch google.generativeai before importing LLMClient
        self.mock_genai = MagicMock()
        self.mock_model = MagicMock()
        self.mock_genai.GenerativeModel.return_value = self.mock_model
        self.mock_genai_types = MagicMock()

        self.env_patch = patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-key"},
            clear=False,
        )
        self.genai_patch = patch.dict(
            "sys.modules",
            {
                "google.generativeai": self.mock_genai,
                "google.generativeai.types": self.mock_genai_types,
            },
        )
        self.env_patch.start()
        self.genai_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.genai_patch.stop()
        # Remove cached module so next test gets a fresh import
        sys.modules.pop("utils.llm", None)

    def _make_client(self):
        from utils.llm import LLMClient
        return LLMClient()

    def test_uses_gemini_api_flag(self):
        client = self._make_client()
        self.assertTrue(client._use_gemini_api)

    def test_configures_api_key(self):
        self._make_client()
        self.mock_genai.configure.assert_called_once_with(api_key="test-key")

    def test_generate_text_returns_response_text(self):
        mock_response = MagicMock()
        mock_response.text = "hello from gemini"
        self.mock_model.generate_content.return_value = mock_response

        client = self._make_client()
        result = client.generate_text("test prompt")

        self.assertEqual(result, "hello from gemini")
        self.mock_model.generate_content.assert_called_once()

    def test_generate_text_no_safety_settings(self):
        """Gemini path must NOT pass safety_settings to generate_content."""
        mock_response = MagicMock()
        mock_response.text = "output"
        self.mock_model.generate_content.return_value = mock_response

        client = self._make_client()
        client.generate_text("prompt")

        call_kwargs = self.mock_model.generate_content.call_args[1]
        self.assertNotIn("safety_settings", call_kwargs)


class TestLLMClientVertexPath(unittest.TestCase):
    """LLMClient selects Vertex AI when GEMINI_API_KEY is absent."""

    def setUp(self):
        self.mock_vertexai = MagicMock()
        self.mock_GenerativeModel = MagicMock()
        self.mock_HarmBlockThreshold = MagicMock()
        self.mock_HarmCategory = MagicMock()
        self.mock_FinishReason = MagicMock()
        self.mock_GenerationConfig = MagicMock()

        # Simulate 4 distinct HarmCategory values
        hc = self.mock_HarmCategory
        hc.HARM_CATEGORY_HATE_SPEECH = "hate"
        hc.HARM_CATEGORY_DANGEROUS_CONTENT = "dangerous"
        hc.HARM_CATEGORY_SEXUALLY_EXPLICIT = "sexual"
        hc.HARM_CATEGORY_HARASSMENT = "harassment"
        self.mock_HarmBlockThreshold.BLOCK_NONE = "BLOCK_NONE"

        self.mock_preview_models = MagicMock()
        self.mock_preview_models.GenerativeModel = self.mock_GenerativeModel
        self.mock_preview_models.HarmBlockThreshold = self.mock_HarmBlockThreshold
        self.mock_preview_models.HarmCategory = self.mock_HarmCategory
        self.mock_preview_models.FinishReason = self.mock_FinishReason
        self.mock_preview_models.GenerationConfig = self.mock_GenerationConfig

        self.env_patch = patch.dict(
            "os.environ",
            {},
            clear=False,
        )
        # Remove GEMINI_API_KEY from env
        import os
        self._original_key = os.environ.pop("GEMINI_API_KEY", None)

        self.modules_patch = patch.dict(
            "sys.modules",
            {
                "vertexai": self.mock_vertexai,
                "vertexai.preview": MagicMock(),
                "vertexai.preview.generative_models": self.mock_preview_models,
            },
        )
        self.modules_patch.start()

    def tearDown(self):
        self.modules_patch.stop()
        sys.modules.pop("utils.llm", None)
        # Restore GEMINI_API_KEY if it was set
        if self._original_key is not None:
            import os
            os.environ["GEMINI_API_KEY"] = self._original_key

    def _make_client(self):
        from utils.llm import LLMClient
        return LLMClient()

    def test_uses_vertex_flag(self):
        client = self._make_client()
        self.assertFalse(client._use_gemini_api)

    def test_inits_vertexai(self):
        self._make_client()
        self.mock_vertexai.init.assert_called_once()

    def test_safety_settings_applied(self):
        """Vertex path must have a _safety dict with all 4 HarmCategory keys set to BLOCK_NONE."""
        client = self._make_client()
        self.assertIsInstance(client._safety, dict)
        self.assertEqual(len(client._safety), 4)
        for v in client._safety.values():
            self.assertEqual(v, "BLOCK_NONE")

    def test_generate_text_returns_stripped_text(self):
        mock_model_instance = MagicMock()
        self.mock_GenerativeModel.return_value = mock_model_instance

        mock_candidate = MagicMock()
        mock_candidate.finish_reason = "OTHER"  # not MAX_TOKENS
        self.mock_FinishReason.MAX_TOKENS = "MAX_TOKENS"

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.text = "  vertex output  "
        mock_model_instance.generate_content.return_value = mock_response

        client = self._make_client()
        result = client.generate_text("test prompt")

        self.assertEqual(result, "vertex output")

    def test_generate_text_max_tokens_logs_warning(self):
        """When finish_reason == MAX_TOKENS, should log warning but still return partial text."""
        mock_model_instance = MagicMock()
        self.mock_GenerativeModel.return_value = mock_model_instance

        mock_candidate = MagicMock()
        self.mock_FinishReason.MAX_TOKENS = "MAX_TOKENS"
        mock_candidate.finish_reason = "MAX_TOKENS"

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.text = "  partial output  "
        mock_model_instance.generate_content.return_value = mock_response

        client = self._make_client()
        with self.assertLogs("utils.llm", level="WARNING") as cm:
            result = client.generate_text("test prompt")

        self.assertEqual(result, "partial output")
        self.assertTrue(any("max tokens" in msg.lower() for msg in cm.output))

    def test_generate_text_no_candidates_raises(self):
        mock_model_instance = MagicMock()
        self.mock_GenerativeModel.return_value = mock_model_instance

        mock_response = MagicMock()
        mock_response.candidates = []
        mock_model_instance.generate_content.return_value = mock_response

        client = self._make_client()
        with self.assertRaises(RuntimeError):
            client.generate_text("test prompt")


class TestLLMClientGenerateJson(unittest.TestCase):
    """generate_json: fence-stripping, raw JSON, invalid JSON."""

    def setUp(self):
        self.mock_genai = MagicMock()
        self.mock_model = MagicMock()
        self.mock_genai.GenerativeModel.return_value = self.mock_model
        self.mock_genai_types = MagicMock()

        import os
        self._original_key = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "test-key"

        self.modules_patch = patch.dict(
            "sys.modules",
            {
                "google.generativeai": self.mock_genai,
                "google.generativeai.types": self.mock_genai_types,
            },
        )
        self.modules_patch.start()

    def tearDown(self):
        self.modules_patch.stop()
        sys.modules.pop("utils.llm", None)
        import os
        if self._original_key is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = self._original_key

    def _make_client(self):
        from utils.llm import LLMClient
        return LLMClient()

    def _set_response(self, text):
        mock_response = MagicMock()
        mock_response.text = text
        self.mock_model.generate_content.return_value = mock_response

    def test_generate_json_fenced_block(self):
        payload = {"key": "value", "num": 42}
        self._set_response(f"```json\n{json.dumps(payload)}\n```")
        client = self._make_client()
        result = client.generate_json("prompt")
        self.assertEqual(result, payload)

    def test_generate_json_raw_json(self):
        payload = {"a": 1}
        self._set_response(json.dumps(payload))
        client = self._make_client()
        result = client.generate_json("prompt")
        self.assertEqual(result, payload)

    def test_generate_json_invalid_raises_value_error(self):
        self._set_response("not valid json {{{")
        client = self._make_client()
        with self.assertRaises(ValueError):
            client.generate_json("prompt")

    def test_generate_json_returns_list(self):
        payload = [1, 2, 3]
        self._set_response(json.dumps(payload))
        client = self._make_client()
        result = client.generate_json("prompt")
        self.assertEqual(result, payload)


if __name__ == "__main__":
    unittest.main()
