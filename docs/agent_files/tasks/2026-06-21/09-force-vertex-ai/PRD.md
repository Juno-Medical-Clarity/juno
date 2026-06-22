# SP09 — Force Vertex AI: Remove Gemini API Studio Path

**Status:** Ready for implementation
**Date:** 2026-06-21
**Branch target:** `main`
**Files touched:** 6

---

## 1. Problem

`backend/utils/llm.py` contains a dual-path `LLMClient` that selects its LLM backend based on whether `GEMINI_API_KEY` is set in the environment. When the key is present, the client routes all LLM calls through **Google AI Studio** (`google-generativeai` / `genai`). Google AI Studio is **explicitly excluded** from Google's HIPAA Business Associate Agreement (BAA). Sending Protected Health Information (PHI) through it is a HIPAA violation.

The deploy pipeline (`.github/workflows/deploy-backend.yml` line 55 and `.github/workflows/rollback-production.yml` line 81) injects `GEMINI_API_KEY` from repository secrets at deploy time, which silently activates the non-compliant path in production whenever the secret is set.

The Vertex AI path (`vertexai` SDK) in the same file is covered under Google's GCP HIPAA BAA and is the only permissible LLM backend for this application.

**Summary of the compliance gap:**
- `GEMINI_API_KEY` secret present in GitHub → Cloud Run gets the env var → `LLMClient.__init__` branches into AI Studio → PHI sent to a non-BAA-covered endpoint.
- The CI workflow (`.github/workflows/ci.yml` line 15) also hard-codes `GEMINI_API_KEY: test-key`, causing the non-compliant path to be exercised in CI tests.

---

## 2. Goals

1. Eliminate the `google-generativeai` / Google AI Studio code path from `LLMClient` entirely.
2. Make `LLMClient` unconditionally use Vertex AI — no runtime flag, no dual paths, no `google.generativeai` import.
3. Remove `GEMINI_API_KEY` from all CI/CD environment injection points.
4. Remove the `google-generativeai` package from `requirements.txt`.
5. Update the test suite in `backend/tests/utils/test_llm.py` to cover only the Vertex AI path.
6. Update the module docstring in `llm.py` to reflect the Vertex-AI-only design.

---

## 3. Non-Goals

- Adding new AI features or changing model behavior.
- Changing the Gemini model name or version (currently `gemini-3.5-flash` via `VERTEX_AI_MODEL`).
- Modifying prompts anywhere in the codebase.
- Rotating or revoking the Gemini API key (human-only step; see §8).
- Executing the GCP HIPAA BAA (human-only step; see §8).
- Auditing other parts of the backend for HIPAA compliance outside of LLM routing.
- Removing the `google-genai` or `google-cloud-aiplatform` packages (those are used by other components and are unrelated to AI Studio).

---

## 4. Architecture Decisions

### 4.1 `backend/utils/llm.py`

**Module docstring — lines 1–10**

Old:
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

New:
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

**`LLMClient` class docstring — line 27**

Old:
```python
class LLMClient:
    """Unified LLM client that wraps either Gemini API or Vertex AI."""
```

New:
```python
class LLMClient:
    """LLM client backed exclusively by Vertex AI."""
```

**`LLMClient.__init__` — lines 29–63**

Old:
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

**`LLMClient.generate_text` — lines 65–94**

Old:
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

`generate_json` (lines 96–102) is unchanged — it delegates to `generate_text`.

---

### 4.2 `.github/workflows/deploy-backend.yml`

**Lines 48–57 — remove `GEMINI_API_KEY` from `env_vars`**

Old:
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

---

### 4.3 `.github/workflows/rollback-production.yml`

**Lines 74–81 — remove `GEMINI_API_KEY` from `env_vars`**

Old:
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

---

### 4.4 `.github/workflows/ci.yml`

**Lines 14–15 — remove `GEMINI_API_KEY` from CI job env**

Old:
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

---

### 4.5 `backend/requirements.txt`

**Line 18 — remove `google-generativeai`**

Old:
```
google-generativeai>=0.8.0
```

New: *(line deleted entirely)*

Note: The `google-genai` package (a separate, newer SDK from Google) may remain if used by other components — this SP only targets `google-generativeai` (the legacy AI Studio SDK). The `.venv` already contains `google-genai` as a transitive dependency of other packages; do not touch those.

---

### 4.6 `backend/tests/utils/test_llm.py`

This file currently tests both the Gemini API path and the Vertex AI path. With the Gemini path removed, the entire file must be rewritten to cover only Vertex AI. The fixtures `gemini_env` and `genai_json_env` are deleted. The Gemini-specific tests are deleted. The `generate_json` tests are migrated to use the Vertex AI fixture.

**Full replacement — complete new file content:**

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

---

## 5. API Change Summary

N/A. No public API endpoints are added, removed, or altered. The change is internal to the LLM client initialisation and is invisible to callers of `LLMClient.generate_text` and `LLMClient.generate_json`.

---

## 6. Frontend Change Summary

N/A. This is a backend-only change. No frontend files, API contracts, or Firebase calls are affected.

---

## 7. Testing

### 7.1 Unit tests (automated)

Run the updated test suite after implementation:

```bash
cd /root/projects/juno/backend
python -m pytest tests/utils/test_llm.py -v
```

Expected: all tests pass. The Gemini-path tests (`test_uses_gemini_api_flag`, `test_configures_api_key`, `test_generate_text_no_safety_settings`, `test_generate_json_*` via `genai_json_env`) no longer exist. New tests verify Vertex AI path exclusively, including `test_generate_text_passes_safety_settings` which asserts `safety_settings` is always forwarded.

### 7.2 Verify `GEMINI_API_KEY` presence no longer routes to AI Studio

After the change, set `GEMINI_API_KEY` in the environment and instantiate `LLMClient` in a Python REPL (with mocked Vertex AI SDK). The key should be silently ignored — `LLMClient` must initialise the Vertex AI path regardless:

```python
import os, sys
from unittest.mock import MagicMock, patch
os.environ["GEMINI_API_KEY"] = "should-be-ignored"

mock_vertexai = MagicMock()
mock_preview = MagicMock()
with patch.dict("sys.modules", {
    "vertexai": mock_vertexai,
    "vertexai.preview": MagicMock(),
    "vertexai.preview.generative_models": mock_preview,
}):
    from utils.llm import LLMClient
    client = LLMClient()

# Must NOT have a _gemini_model or _use_gemini_api attribute
assert not hasattr(client, "_use_gemini_api")
assert not hasattr(client, "_gemini_model")
assert hasattr(client, "_model")
mock_vertexai.init.assert_called_once()
print("PASS: Vertex AI used regardless of GEMINI_API_KEY")
```

### 7.3 Full backend test suite

```bash
cd /root/projects/juno/backend
python -m pytest tests/ -q
```

All existing tests should pass. Any test that previously relied on `GEMINI_API_KEY` being set (in the old `ci.yml`) will now run with the key absent — which is the correct production-equivalent state.

### 7.4 Local smoke test (optional, requires GCP credentials)

```bash
export GCP_PROJECT_ID=juno-medical-clarity
export GCP_LOCATION=us-central1
export VERTEX_AI_MODEL=gemini-3.5-flash
unset GEMINI_API_KEY
cd /root/projects/juno/backend
python -c "
from utils.llm import LLMClient
client = LLMClient()
print(client.generate_text('Say hello in one word.'))
"
```

Expected: a one-word response from Vertex AI, logged with "LLMClient: using Vertex AI".

---

## 8. Manual Intervention Required From You

These steps cannot be automated and must be performed by a human with appropriate access.

**Step 1 — Execute the Google Cloud HIPAA BAA**
Navigate to GCP Console > Account > Legal / Privacy Compliance and execute the HIPAA Business Associate Agreement for project `juno-medical-clarity`. This BAA is the legal basis that makes Vertex AI usage with PHI permissible. Without it, even the Vertex AI path is not HIPAA-covered. This step is a prerequisite to any production use of the backend with patient data.

**Step 2 — Delete `GEMINI_API_KEY` from GitHub repository secrets**
Navigate to the Juno GitHub repository > Settings > Secrets and variables > Actions > Repository secrets. Delete the `GEMINI_API_KEY` secret. After this SP is deployed, the key serves no purpose and leaving it in place creates an unnecessary risk that it could be re-injected.

**Step 3 — Verify Vertex AI API is enabled in GCP project `juno-medical-clarity`**
Navigate to GCP Console > APIs & Services > Enabled APIs and verify that the **Vertex AI API** is enabled. If it is not enabled, enable it. The backend service account must also have the `roles/aiplatform.user` IAM role (or equivalent) to call `vertexai.init` and `GenerativeModel.generate_content`.

**Step 4 — Assess prior PHI exposure (legal/compliance)**
If the `GEMINI_API_KEY` GitHub secret was set and deployed to production at any point while the backend was processing real patient data, consult your legal counsel and HIPAA compliance officer to determine whether a breach assessment or notification is required under 45 CFR § 164.400–414 (HIPAA Breach Notification Rule). The finding that `GEMINI_API_KEY` is injected at deploy time (confirmed in `deploy-backend.yml` line 55) makes this a credible concern if the secret was ever populated.

---

## 9. Open Questions & Decisions

**[RESOLVED: Remove]** Should the `google-generativeai` package be kept in `requirements.txt` in case it is needed by other backend code?
Resolved by grep: `grep -r "google.generativeai" /root/projects/juno/backend/ --include="*.py"` returns hits only in `backend/utils/llm.py` (the branch being deleted) and `backend/tests/utils/test_llm.py` (the tests being replaced). No other backend module imports `google.generativeai`. The package can be safely removed from `requirements.txt`.

**[RESOLVED: Ignore silently]** Should `LLMClient.__init__` explicitly raise an error if `GEMINI_API_KEY` is found in the environment, as a defense-in-depth guard?
Resolved: No. Raising on the presence of `GEMINI_API_KEY` would break any environment where the key is present for unrelated tooling (e.g., local developer machines running both AI Studio experiments and this backend). Since the code no longer reads or acts on the key, ignoring it silently is the correct behavior. The CI workflow change (removing the key from CI env) and the GitHub secret deletion (Step 8.2) are the appropriate controls. A startup log line at INFO level ("LLMClient: using Vertex AI") is sufficient to confirm the correct path.

**[RESOLVED: Delete entirely]** Should `test_uses_gemini_api_flag`, `test_configures_api_key`, `test_generate_text_no_safety_settings`, and the `genai_json_env`-based `generate_json` tests be kept as skipped/xfail tests?
Resolved: No. Tests for deleted code paths should be deleted, not marked xfail. Keeping them as xfail would create maintenance debt and confuse the intent of the test suite. The Vertex AI path already has coverage for `generate_json` via `generate_text` delegation; new `generate_json` tests using the `vertex_env` fixture are included in the replacement test file.

**[RESOLVED: No action]** Does `backend/config.py` require any changes?
Resolved by reading the file: `config.py` has no `GEMINI_API_KEY` reference. No changes needed.

**[RESOLVED: No action]** Are there any other workflow files beyond `deploy-backend.yml`, `rollback-production.yml`, and `ci.yml` that reference `GEMINI_API_KEY`?
Resolved by grep: `grep -r "GEMINI_API_KEY" /root/projects/juno/.github/` returns exactly those three files. No other workflow files are affected.

**[RESOLVED: No action required in this SP]** The `google-genai` package (newer Google AI SDK) is present in `.venv` as a transitive dependency. Should it be audited?
Resolved: Out of scope for SP09. `google-genai` is not imported by any application code (`grep -r "from google import genai\|import google.genai" /root/projects/juno/backend/ --include="*.py"` returns no hits). It exists only as a transitive dependency. If it becomes a direct dependency in future work, that SP should include a HIPAA routing review at that time.

**[DEFERRED]** Should the CI workflow be updated to run tests against a local Vertex AI emulator or mock, rather than relying entirely on unit-level mocks?
Deferred: The existing pattern of mocking the `vertexai` SDK at the `sys.modules` level is consistent with the project's current test strategy and does not require a live GCP connection in CI. Moving to an emulator would require infrastructure changes and is a separate initiative.
