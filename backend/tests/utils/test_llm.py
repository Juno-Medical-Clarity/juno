"""
tests/utils/test_llm.py — Tests for utils/llm.py (LLMClient).

Covers:
  1. Gemini API path selection and generate_text
  2. Vertex AI path selection, safety settings, generate_text with MAX_TOKENS warning
  3. generate_json: fenced JSON, raw JSON, invalid JSON
"""

import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gemini_env():
    """Set up Gemini API environment and mocks, clean up after."""
    mock_genai = MagicMock()
    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    mock_genai_types = MagicMock()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False), \
         patch.dict("sys.modules", {
             "google.generativeai": mock_genai,
             "google.generativeai.types": mock_genai_types,
         }):
        yield mock_genai, mock_model, mock_genai_types

    sys.modules.pop("utils.llm", None)


@pytest.fixture
def vertex_env():
    """Set up Vertex AI environment and mocks, clean up after."""
    mock_vertexai = MagicMock()
    mock_GenerativeModel = MagicMock()
    mock_HarmBlockThreshold = MagicMock()
    mock_HarmCategory = MagicMock()
    mock_FinishReason = MagicMock()
    mock_GenerationConfig = MagicMock()

    hc = mock_HarmCategory
    hc.HARM_CATEGORY_HATE_SPEECH = "hate"
    hc.HARM_CATEGORY_DANGEROUS_CONTENT = "dangerous"
    hc.HARM_CATEGORY_SEXUALLY_EXPLICIT = "sexual"
    hc.HARM_CATEGORY_HARASSMENT = "harassment"
    mock_HarmBlockThreshold.BLOCK_NONE = "BLOCK_NONE"

    mock_preview_models = MagicMock()
    mock_preview_models.GenerativeModel = mock_GenerativeModel
    mock_preview_models.HarmBlockThreshold = mock_HarmBlockThreshold
    mock_preview_models.HarmCategory = mock_HarmCategory
    mock_preview_models.FinishReason = mock_FinishReason
    mock_preview_models.GenerationConfig = mock_GenerationConfig

    original_key = os.environ.pop("GEMINI_API_KEY", None)

    with patch.dict("sys.modules", {
        "vertexai": mock_vertexai,
        "vertexai.preview": MagicMock(),
        "vertexai.preview.generative_models": mock_preview_models,
    }):
        yield mock_vertexai, mock_GenerativeModel, mock_HarmBlockThreshold, mock_HarmCategory, mock_FinishReason, mock_preview_models

    sys.modules.pop("utils.llm", None)
    if original_key is not None:
        os.environ["GEMINI_API_KEY"] = original_key


@pytest.fixture
def genai_json_env():
    """Set up Gemini environment for generate_json tests."""
    mock_genai = MagicMock()
    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    mock_genai_types = MagicMock()

    original_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "test-key"

    with patch.dict("sys.modules", {
        "google.generativeai": mock_genai,
        "google.generativeai.types": mock_genai_types,
    }):
        yield mock_genai, mock_model

    sys.modules.pop("utils.llm", None)
    if original_key is None:
        os.environ.pop("GEMINI_API_KEY", None)
    else:
        os.environ["GEMINI_API_KEY"] = original_key


# ---------------------------------------------------------------------------
# Gemini path tests
# ---------------------------------------------------------------------------

def test_uses_gemini_api_flag(gemini_env):
    from utils.llm import LLMClient
    client = LLMClient()
    assert client._use_gemini_api


def test_configures_api_key(gemini_env):
    mock_genai, mock_model, _ = gemini_env
    from utils.llm import LLMClient
    LLMClient()
    mock_genai.configure.assert_called_once_with(api_key="test-key")


def test_generate_text_returns_response_text(gemini_env):
    mock_genai, mock_model, _ = gemini_env
    mock_response = MagicMock()
    mock_response.text = "hello from gemini"
    mock_model.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_text("test prompt")

    assert result == "hello from gemini"
    mock_model.generate_content.assert_called_once()


def test_generate_text_no_safety_settings(gemini_env):
    """Gemini path must NOT pass safety_settings to generate_content."""
    mock_genai, mock_model, _ = gemini_env
    mock_response = MagicMock()
    mock_response.text = "output"
    mock_model.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    client.generate_text("prompt")

    call_kwargs = mock_model.generate_content.call_args[1]
    assert "safety_settings" not in call_kwargs


# ---------------------------------------------------------------------------
# Vertex AI path tests
# ---------------------------------------------------------------------------

def test_uses_vertex_flag(vertex_env):
    from utils.llm import LLMClient
    client = LLMClient()
    assert not client._use_gemini_api


def test_inits_vertexai(vertex_env):
    mock_vertexai, *_ = vertex_env
    from utils.llm import LLMClient
    LLMClient()
    mock_vertexai.init.assert_called_once()


def test_safety_settings_applied(vertex_env):
    """Vertex path must have a _safety dict with all 4 HarmCategory keys set to BLOCK_NONE."""
    from utils.llm import LLMClient
    client = LLMClient()
    assert isinstance(client._safety, dict)
    assert len(client._safety) == 4
    for v in client._safety.values():
        assert v == "BLOCK_NONE"


def test_generate_text_returns_stripped_text(vertex_env):
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    mock_candidate = MagicMock()
    mock_candidate.finish_reason = "OTHER"  # not MAX_TOKENS
    mock_FinishReason.MAX_TOKENS = "MAX_TOKENS"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.text = "  vertex output  "
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_text("test prompt")

    assert result == "vertex output"


def test_generate_text_max_tokens_logs_warning(vertex_env):
    """When finish_reason == MAX_TOKENS, should log warning but still return partial text."""
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    mock_candidate = MagicMock()
    mock_FinishReason.MAX_TOKENS = "MAX_TOKENS"
    mock_candidate.finish_reason = "MAX_TOKENS"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.text = "  partial output  "
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    import logging
    with pytest.raises(Exception) if False else _noop():
        pass

    # Use caplog is not available here but we can use assertLogs-style via logging capture
    import logging
    with _capture_logs("utils.llm", "WARNING") as captured:
        result = client.generate_text("test prompt")

    assert result == "partial output"
    assert any("max tokens" in msg.lower() for msg in captured)


def test_generate_text_no_candidates_raises(vertex_env):
    mock_vertexai, mock_GenerativeModel, *_ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    mock_response = MagicMock()
    mock_response.candidates = []
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    with pytest.raises(RuntimeError):
        client.generate_text("test prompt")


# ---------------------------------------------------------------------------
# generate_json tests
# ---------------------------------------------------------------------------

def test_generate_json_fenced_block(genai_json_env):
    mock_genai, mock_model = genai_json_env
    payload = {"key": "value", "num": 42}
    mock_response = MagicMock()
    mock_response.text = f"```json\n{json.dumps(payload)}\n```"
    mock_model.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_json("prompt")
    assert result == payload


def test_generate_json_raw_json(genai_json_env):
    mock_genai, mock_model = genai_json_env
    payload = {"a": 1}
    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)
    mock_model.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_json("prompt")
    assert result == payload


def test_generate_json_invalid_raises_value_error(genai_json_env):
    mock_genai, mock_model = genai_json_env
    mock_response = MagicMock()
    mock_response.text = "not valid json {{{"
    mock_model.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    with pytest.raises(ValueError):
        client.generate_json("prompt")


def test_generate_json_returns_list(genai_json_env):
    mock_genai, mock_model = genai_json_env
    payload = [1, 2, 3]
    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)
    mock_model.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_json("prompt")
    assert result == payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import contextlib
import logging


class _noop:
    """No-op context manager."""
    def __enter__(self): return self
    def __exit__(self, *a): return False


@contextlib.contextmanager
def _capture_logs(logger_name, level):
    """Capture log messages from the named logger."""
    records = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = _Handler()
    handler.setLevel(getattr(logging, level))
    logger = logging.getLogger(logger_name)
    orig_level = logger.level
    logger.setLevel(getattr(logging, level))
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(orig_level)
