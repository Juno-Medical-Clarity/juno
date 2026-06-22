# SP09 — Force Vertex AI: Tasks

**PRD:** `docs/agent_files/tasks/2026-06-21/09-force-vertex-ai/PRD.md`
**Status:** Ready for implementation
**Branch target:** `main`

---

## Task 1 — Rewrite `backend/utils/llm.py`

**File:** `/root/projects/juno/backend/utils/llm.py`

**Changes:**

Replace the entire contents of the file. The `_strip_json_fences` helper and `generate_json` method are unchanged; only the module docstring, class docstring, `__init__`, and `generate_text` are rewritten.

1. **Module docstring (lines 1–10)** — replace:
   ```python
   """
   utils/llm.py — Unified LLM client for Gemini API and Vertex AI.

   Selects the backend based on environment:
     - GEMINI_API_KEY set  → uses google-generativeai (Gemini API)
     - GEMINI_API_KEY unset → uses vertexai (Vertex AI)

   This consolidates logic previously split between utils/gemini_client.py
   and the backend-selection block in simplify/v1_2/pipeline.py.
   """
   ```
   with:
   ```python
   """
   utils/llm.py — LLM client for Vertex AI (HIPAA-compliant path only).

   Uses vertexai SDK exclusively. Google AI Studio (google-generativeai /
   GEMINI_API_KEY) is not used because it is excluded from Google's HIPAA BAA.

   Requires environment variables:
     GCP_PROJECT_ID  — GCP project that has Vertex AI API enabled
     GCP_LOCATION    — region (default: us-central1)
     VERTEX_AI_MODEL — model name (default: gemini-1.5-pro)
   """
   ```

2. **Class docstring (line 27)** — replace:
   ```python
   class LLMClient:
       """Unified LLM client that wraps either Gemini API or Vertex AI."""
   ```
   with:
   ```python
   class LLMClient:
       """LLM client backed exclusively by Vertex AI."""
   ```

3. **`__init__` method (lines 29–63)** — replace the entire method body:

   Old (lines 29–63):
   ```python
       def __init__(self, model_name: str | None = None):
           if model_name is None:
               model_name = os.environ.get("VERTEX_AI_MODEL", "gemini-1.5-pro")

           if os.environ.get("GEMINI_API_KEY"):
               import google.generativeai as genai
               from google.generativeai.types import GenerationConfig as GeminiGenerationConfig
               genai.configure(api_key=os.environ["GEMINI_API_KEY"])
               self._gemini_model = genai.GenerativeModel(model_name)
               self._GeminiGenerationConfig = GeminiGenerationConfig
               self._use_gemini_api = True
               logger.info("LLMClient: using Gemini API")
           else:
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
               self._use_gemini_api = False
               logger.info("LLMClient: using Vertex AI")
   ```

   New:
   ```python
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
   ```

4. **`generate_text` method (lines 65–94)** — replace the entire method body:

   Old (lines 65–94):
   ```python
       def generate_text(self, prompt: str, temperature: float = 0.3, max_tokens: int = 8192) -> str:
           """Generate text from a prompt. Returns the text string directly."""
           if self._use_gemini_api:
               config = self._GeminiGenerationConfig(
                   temperature=temperature,
                   max_output_tokens=max_tokens,
               )
               response = self._gemini_model.generate_content(prompt, generation_config=config)
               return response.text

           # Vertex AI path.
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
   ```

   New:
   ```python
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
   ```

   `generate_json` (lines 96–102) is unchanged.

**Acceptance criteria:**
- `LLMClient` has no `_use_gemini_api`, `_gemini_model`, or `_GeminiGenerationConfig` attributes after instantiation.
- `LLMClient` has `_model`, `_safety`, `_FinishReason`, and `_VertexGenerationConfig` attributes.
- `grep -n "gemini_api\|GEMINI_API_KEY\|google.generativeai\|GeminiGenerationConfig" backend/utils/llm.py` returns zero lines.
- The module docstring contains "HIPAA-compliant path only".
- The file still has `generate_json` unchanged (delegates to `generate_text`).

---

## Task 2 — Remove `google-generativeai` from `backend/requirements.txt`

**File:** `/root/projects/juno/backend/requirements.txt`

**Changes:**

Delete line 18:
```
google-generativeai>=0.8.0
```

The surrounding lines (17 `textstat` and 19 `pydantic`) remain. No other lines change.

**Acceptance criteria:**
- `grep "google-generativeai" backend/requirements.txt` returns no output.
- `grep "google-genai\|google-cloud-aiplatform" backend/requirements.txt` still returns the original lines (those are separate packages and must not be touched).
- The file has one fewer line than before (was 34 lines, now 33).

---

## Task 3 — Remove `GEMINI_API_KEY` from `.github/workflows/ci.yml`

**File:** `/root/projects/juno/.github/workflows/ci.yml`

**Changes:**

Remove line 15 (`GEMINI_API_KEY: test-key`) from the `backend` job `env` block.

Old (lines 14–19):
```yaml
    env:
      GEMINI_API_KEY: test-key
      GCP_PROJECT_ID: test-project
      GCP_LOCATION: us-central1
      FIRESTORE_DATABASE_ID: "(default)"
      SIMPLIFY_DEFAULT_VERSION: v1-2
```

New:
```yaml
    env:
      GCP_PROJECT_ID: test-project
      GCP_LOCATION: us-central1
      FIRESTORE_DATABASE_ID: "(default)"
      SIMPLIFY_DEFAULT_VERSION: v1-2
```

**Acceptance criteria:**
- `grep "GEMINI_API_KEY" .github/workflows/ci.yml` returns no output.
- The `env` block still contains `GCP_PROJECT_ID`, `GCP_LOCATION`, `FIRESTORE_DATABASE_ID`, and `SIMPLIFY_DEFAULT_VERSION` with their existing values.
- The rest of the file (frontend job, triggers, concurrency) is unchanged.

---

## Task 4 — Remove `GEMINI_API_KEY` from `.github/workflows/deploy-backend.yml`

**File:** `/root/projects/juno/.github/workflows/deploy-backend.yml`

**Changes:**

Remove line 55 (`GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }}`) from the `env_vars` block in the "Deploy to Cloud Run" step.

Old (lines 48–55):
```yaml
          env_vars: |
            GCP_PROJECT_ID=${{ env.GCP_PROJECT_ID }}
            GCP_BUCKET_NAME=${{ env.GCP_BUCKET_NAME }}
            GCP_LOCATION=${{ env.GCP_REGION }}
            VERTEX_AI_MODEL=gemini-3.5-flash
            SIMPLIFY_DEFAULT_VERSION=v1-2
            FIRESTORE_DATABASE_ID=(default)
            GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }}
```

New:
```yaml
          env_vars: |
            GCP_PROJECT_ID=${{ env.GCP_PROJECT_ID }}
            GCP_BUCKET_NAME=${{ env.GCP_BUCKET_NAME }}
            GCP_LOCATION=${{ env.GCP_REGION }}
            VERTEX_AI_MODEL=gemini-3.5-flash
            SIMPLIFY_DEFAULT_VERSION=v1-2
            FIRESTORE_DATABASE_ID=(default)
```

**Acceptance criteria:**
- `grep "GEMINI_API_KEY" .github/workflows/deploy-backend.yml` returns no output.
- The `env_vars` block retains all six remaining variables (`GCP_PROJECT_ID`, `GCP_BUCKET_NAME`, `GCP_LOCATION`, `VERTEX_AI_MODEL`, `SIMPLIFY_DEFAULT_VERSION`, `FIRESTORE_DATABASE_ID`).
- The `secrets` block below (`FIREBASE_SERVICE_ACCOUNT_JSON`) is unchanged.

---

## Task 5 — Remove `GEMINI_API_KEY` from `.github/workflows/rollback-production.yml`

**File:** `/root/projects/juno/.github/workflows/rollback-production.yml`

**Changes:**

Remove line 81 (`GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }}`) from the `env_vars` block in the "Deploy rollback backend" step.

Old (lines 74–81):
```yaml
          env_vars: |
            GCP_PROJECT_ID=${{ env.GCP_PROJECT_ID }}
            GCP_BUCKET_NAME=${{ env.GCP_BUCKET_NAME }}
            GCP_LOCATION=${{ env.GCP_REGION }}
            VERTEX_AI_MODEL=gemini-3.5-flash
            SIMPLIFY_DEFAULT_VERSION=v1-2
            FIRESTORE_DATABASE_ID=(default)
            GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }}
```

New:
```yaml
          env_vars: |
            GCP_PROJECT_ID=${{ env.GCP_PROJECT_ID }}
            GCP_BUCKET_NAME=${{ env.GCP_BUCKET_NAME }}
            GCP_LOCATION=${{ env.GCP_REGION }}
            VERTEX_AI_MODEL=gemini-3.5-flash
            SIMPLIFY_DEFAULT_VERSION=v1-2
            FIRESTORE_DATABASE_ID=(default)
```

**Acceptance criteria:**
- `grep "GEMINI_API_KEY" .github/workflows/rollback-production.yml` returns no output.
- The `env_vars` block retains all six remaining variables (`GCP_PROJECT_ID`, `GCP_BUCKET_NAME`, `GCP_LOCATION`, `VERTEX_AI_MODEL`, `SIMPLIFY_DEFAULT_VERSION`, `FIRESTORE_DATABASE_ID`).
- The `secrets` block below (`FIREBASE_SERVICE_ACCOUNT_JSON`) and all frontend steps are unchanged.

---

## Task 6 — Replace `backend/tests/utils/test_llm.py` with Vertex-AI-only tests

**File:** `/root/projects/juno/backend/tests/utils/test_llm.py`

**Changes:**

Replace the entire file with the content specified in PRD §4.6. The new file:

- Removes the `gemini_env` fixture (lines 22–37).
- Removes the `genai_json_env` fixture (lines 78–99).
- Removes all Gemini-path tests: `test_uses_gemini_api_flag`, `test_configures_api_key`, `test_generate_text_returns_response_text`, `test_generate_text_no_safety_settings` (lines 106–145).
- Removes the `test_uses_vertex_flag` test (lines 152–155) — the attribute `_use_gemini_api` no longer exists.
- Rewrites the `vertex_env` fixture to use `patch.dict("os.environ", ..., clear=True)` with `GEMINI_API_KEY` explicitly absent (instead of `os.environ.pop` and restore).
- Moves `_capture_logs` and imports to the top of the file (currently defined at the bottom, lines 300–329).
- Migrates the four `generate_json` tests (`test_generate_json_fenced_block`, `test_generate_json_raw_json`, `test_generate_json_returns_list`, `test_generate_json_invalid_raises_value_error`) from `genai_json_env` to `vertex_env`.
- Adds `test_generate_text_passes_safety_settings` (new test not present in current file).

The complete new file content is exactly as specified in PRD §4.6 (reproduced here for reference):

```python
"""
tests/utils/test_llm.py — Tests for utils/llm.py (LLMClient).

Covers (Vertex AI path only — AI Studio path removed for HIPAA compliance):
  1. Vertex AI initialisation: vertexai.init called, GenerativeModel instantiated
  2. Safety settings applied with all four HarmCategory keys set to BLOCK_NONE
  3. generate_text: returns stripped text, logs warning on MAX_TOKENS, raises on no candidates
  4. generate_json: fenced JSON, raw JSON, list, invalid JSON raises ValueError
"""

import json
import sys
import os
import contextlib
import logging
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vertex_env():
    """Set up Vertex AI mocks and ensure GEMINI_API_KEY is absent."""
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

    # Ensure the non-compliant key is never present during tests
    env_override = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}

    with patch.dict("os.environ", env_override, clear=True), \
         patch.dict("sys.modules", {
             "vertexai": mock_vertexai,
             "vertexai.preview": MagicMock(),
             "vertexai.preview.generative_models": mock_preview_models,
         }):
        yield mock_vertexai, mock_GenerativeModel, mock_HarmBlockThreshold, mock_HarmCategory, mock_FinishReason, mock_preview_models

    sys.modules.pop("utils.llm", None)


@contextlib.contextmanager
def _capture_logs(logger_name, level):
    """Capture log messages from the named logger."""
    records = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = _Handler()
    handler.setLevel(getattr(logging, level))
    log = logging.getLogger(logger_name)
    orig_level = log.level
    log.setLevel(getattr(logging, level))
    log.addHandler(handler)
    try:
        yield records
    finally:
        log.removeHandler(handler)
        log.setLevel(orig_level)


# ---------------------------------------------------------------------------
# Initialisation tests
# ---------------------------------------------------------------------------

def test_inits_vertexai(vertex_env):
    mock_vertexai, *_ = vertex_env
    from utils.llm import LLMClient
    LLMClient()
    mock_vertexai.init.assert_called_once()


def test_safety_settings_applied(vertex_env):
    """_safety dict must have all 4 HarmCategory keys set to BLOCK_NONE."""
    from utils.llm import LLMClient
    client = LLMClient()
    assert isinstance(client._safety, dict)
    assert len(client._safety) == 4
    for v in client._safety.values():
        assert v == "BLOCK_NONE"


# ---------------------------------------------------------------------------
# generate_text tests
# ---------------------------------------------------------------------------

def test_generate_text_returns_stripped_text(vertex_env):
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    mock_candidate = MagicMock()
    mock_candidate.finish_reason = "OTHER"
    mock_FinishReason.MAX_TOKENS = "MAX_TOKENS"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.text = "  vertex output  "
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_text("test prompt")

    assert result == "vertex output"


def test_generate_text_passes_safety_settings(vertex_env):
    """generate_text must always pass safety_settings to generate_content."""
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.text = "output"
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    client.generate_text("prompt")

    call_kwargs = mock_model_instance.generate_content.call_args[1]
    assert "safety_settings" in call_kwargs
    assert call_kwargs["safety_settings"] == client._safety


def test_generate_text_max_tokens_logs_warning(vertex_env):
    """When finish_reason == MAX_TOKENS, log a warning but still return text."""
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

def test_generate_json_fenced_block(vertex_env):
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    payload = {"key": "value", "num": 42}
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.text = f"```json\n{json.dumps(payload)}\n```"
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_json("prompt")
    assert result == payload


def test_generate_json_raw_json(vertex_env):
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    payload = {"a": 1}
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.text = json.dumps(payload)
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_json("prompt")
    assert result == payload


def test_generate_json_returns_list(vertex_env):
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    payload = [1, 2, 3]
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.text = json.dumps(payload)
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    result = client.generate_json("prompt")
    assert result == payload


def test_generate_json_invalid_raises_value_error(vertex_env):
    mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
    mock_model_instance = MagicMock()
    mock_GenerativeModel.return_value = mock_model_instance

    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.text = "not valid json {{{"
    mock_model_instance.generate_content.return_value = mock_response

    from utils.llm import LLMClient
    client = LLMClient()
    with pytest.raises(ValueError):
        client.generate_json("prompt")
```

**Acceptance criteria:**
- `grep -n "gemini_env\|genai_json_env\|test_uses_gemini\|test_configures_api_key\|test_generate_text_no_safety_settings\|test_uses_vertex_flag\|_noop\|GEMINI_API_KEY" backend/tests/utils/test_llm.py` returns zero lines.
- The file contains exactly these test function names: `test_inits_vertexai`, `test_safety_settings_applied`, `test_generate_text_returns_stripped_text`, `test_generate_text_passes_safety_settings`, `test_generate_text_max_tokens_logs_warning`, `test_generate_text_no_candidates_raises`, `test_generate_json_fenced_block`, `test_generate_json_raw_json`, `test_generate_json_returns_list`, `test_generate_json_invalid_raises_value_error`.
- Running `cd /root/projects/juno/backend && python -m pytest tests/utils/test_llm.py -v` shows all 10 tests passing and 0 failures.

---

## Task 7 — Run the full backend test suite and verify

**No file changes.** This task is a verification gate.

**Steps:**

```bash
cd /root/projects/juno/backend
python -m pytest tests/ -q
```

**Acceptance criteria:**
- All tests pass (0 failures, 0 errors).
- No test imports or references `GEMINI_API_KEY`, `google.generativeai`, or `_use_gemini_api` — confirm with:
  ```bash
  grep -r "GEMINI_API_KEY\|google.generativeai\|_use_gemini_api" /root/projects/juno/backend/tests/
  ```
  This must return zero lines.
- Confirm `GEMINI_API_KEY` is absent from all three workflow files:
  ```bash
  grep -r "GEMINI_API_KEY" /root/projects/juno/.github/workflows/
  ```
  This must return zero lines.

---

## Summary of what requires you (not a dev agent)

These steps from PRD §8 require human access and cannot be scripted:

**Step 1 — Execute the Google Cloud HIPAA BAA**
Log into GCP Console for project `juno-medical-clarity`, navigate to Account > Legal / Privacy Compliance, and execute the HIPAA Business Associate Agreement. This is the legal prerequisite for any production PHI processing via Vertex AI.

**Step 2 — Delete `GEMINI_API_KEY` from GitHub repository secrets**
Go to the Juno GitHub repository > Settings > Secrets and variables > Actions > Repository secrets and delete the `GEMINI_API_KEY` secret. Do this after the code changes from Tasks 1–6 are merged and deployed, so that any rollback of the workflow files does not silently re-activate the non-compliant path.

**Step 3 — Verify Vertex AI API is enabled in GCP project `juno-medical-clarity`**
In GCP Console > APIs & Services > Enabled APIs, confirm the Vertex AI API is enabled. Confirm the Cloud Run service account has the `roles/aiplatform.user` IAM role (or equivalent) so `vertexai.init` and `GenerativeModel.generate_content` can be called without permission errors.

**Step 4 — Assess prior PHI exposure (legal/compliance)**
If `GEMINI_API_KEY` was populated in GitHub secrets at any time while the backend was processing real patient data, consult your legal counsel and HIPAA compliance officer. A breach assessment under 45 CFR § 164.400–414 may be required. The presence of `GEMINI_API_KEY` in `deploy-backend.yml` line 55 (confirmed in the actual file) makes this a credible concern if the secret was ever set.
