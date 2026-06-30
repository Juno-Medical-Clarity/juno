# SP02 Constants Consolidation + Backend-Root Layout — TASKS

## Prerequisites

Reorganizes constants into namespaced nested classes, migrates scattered literals, adds a config accessor, moves observability modules into `backend/observability/`, and deletes dead `config.py` — reducing coupling, eliminating silent duplicates, and leaving only `app.py` and `error_codes.py` at the backend root. Assumes SP01 (Unified Error System) is fully complete and merged.

---

## Tasks

### Task 02.1: Rewrite `utils/constants.py` with namespaced nested classes

**Goal:** Replace the flat 79-line `Constants` class with the namespaced nested-class design from PRD §4a. Add `AthenaSourceKind(StrEnum)` inside `Constants.Athena`. Add `Constants.Llm.MAX_TOKENS_LONG_FORM = 65536` (per user decision Q4: the 65536 override appears in two pipeline callsites and is promoted to a named constant). Add backward-compat flat shims at the bottom of the file (per PRD §4a and Q5) so callsites not updated in this SP continue to compile. The outer `Constants` class name is preserved so existing `from utils.constants import Constants` imports need no change.

**Files:**
- `backend/utils/constants.py` — full rewrite

**Steps:**

1. Open `backend/utils/constants.py`. Replace the entire file contents with the following structure (preserve the existing `_grading_method_base` helper class, renamed to `_GradingMethodBase` to match PEP-8 convention used in the PRD):

   ```python
   from enum import Enum, StrEnum


   class _GradingMethodBase:
       def __init__(self, value: str, description: str):
           self.value = value
           self.description = description


   class Constants:

       class Schema:
           SUMMARY_SCHEMA_VERSION_1_2: str = "1.2"
           SUMMARY_SCHEMA_VERSION_1_3: str = "1.3"
           SUMMARY_SCHEMA_VERSION_1_4: str = "1.4"
           INPUT_VERSION: str = "1.0"
           GRADING_VERSION: str = "1.0"

       class Uploads:
           ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx", "html", "htm"})
           MAX_FILE_BYTES: int = 10 * 1024 * 1024
           MAX_FILE_COUNT: int = 10
           MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024
           UPLOAD_PREFIX: str = "care_plan-uploads"

       class Pipeline:
           PIPELINE_VERSION_V1_2: str = "v1-2"
           ALLOWED_VERSIONS: frozenset[str] = frozenset({"v1-2"})
           STEPS: dict[int, str] = {
               1: "Reading your note",
               2: "Finding difficult and medical terms",
               3: "Simplifying language",
               4: "Clarifying actions and numbers",
               5: "Organizing your care plan",
           }
           RESULT_SENTINEL: str = "__result__"

           class CARE_PLAN_VERSIONS(Enum):
               V1_2 = "1.2"

       class Batch:
           MAX_BATCH_RUNS: int = 50

       class Deadlines:
           SINGLE_JOB_INTERNAL_DEADLINE_S: int = 270
           BATCH_ITEM_INTERNAL_DEADLINE_S: int = 870
           JOB_TIMEOUT_SECONDS_SINGLE: int = 300
           JOB_TIMEOUT_SECONDS_BATCH: int = 900

       class Llm:
           MODEL_DEFAULT: str = "gemini-1.5-pro"
           MAX_TOKENS: int = 8192
           MAX_TOKENS_LONG_FORM: int = 65536  # deliberate override for long-form generation steps
           TEMPERATURE_TEXT: float = 0.3
           TEMPERATURE_JSON: float = 0.2

       class Athena:
           BASE_URL: str = "https://api.preview.platform.athenahealth.com"
           PRACTICE_ID: str = "195900"
           OAUTH_SCOPE: str = "athena/service/Athenanet.MDP.*"
           BATCH_SIZE: int = 2
           BATCH_SLEEP_S: int = 30
           TOKEN_TTL_S: int = 300
           TOKEN_REFRESH_BUFFER_S: int = 20
           HTTP_TIMEOUT_TOKEN_S: int = 30
           HTTP_TIMEOUT_GET_S: int = 60
           MAX_RETRIES: int = 3

           class AthenaSourceKind(StrEnum):
               ATHENA_ENCOUNTER = "athena_encounter"
               ATHENA_CLINICAL_DOC = "athena_clinical_doc"

       class Storage:
           GCS_BUCKET_ENV_VAR: str = "GCP_BUCKET_NAME"
           GCS_PRESET_PREFIX: str = "preset-data"
           TEMP_BASE: str = "/tmp/juno-datasets"
           SIGNED_URL_TTL_MIN: int = 30
           GCP_LOCATION_DEFAULT: str = "us-central1"
           FIRESTORE_DATABASE_ID_DEFAULT: str = "(default)"

       class Grading:
           class GRADING_METHODS(Enum):
               SMOG           = _GradingMethodBase("SMOG", "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials")
               FLESCH_KINCAID = _GradingMethodBase("Flesch-Kincaid", "Flesch-Kincaid Reading Ease + Grade Level (1975) — sentence length × syllable load")
               DALE_CHALL     = _GradingMethodBase("Dale-Chall", "Dale-Chall (1948/1995) — difficult words outside the 3,000 familiar-word list")
               PEMAT          = _GradingMethodBase("PEMAT", "PEMAT (AHRQ 2013) — automated approximation of items 3,8,14,21-22 (understandability) and 27-33 (actionability)")
               SAM            = _GradingMethodBase("SAM", "SAM (Doak et al. 1996) — automated approximation of content, literacy demand, and layout/typography domains")
               CDC_CCI        = _GradingMethodBase("CDC CCI", "CDC Clear Communication Index — automated approximation of main message, behavioral recommendations, numbers, and call-to-action items")

       class Enums:
           class SOURCE(Enum):
               DOCUMENTS = "documents"
               RECORDING = "recording"
               NOTES     = "notes"

           class IMPORTANCE(Enum):
               HIGH = "high"
               LOW  = "low"

       class EnvVars:
           GCS_BUCKET: str = "GCP_BUCKET_NAME"
           GCP_PROJECT_ID: str = "GCP_PROJECT_ID"
           GCP_LOCATION: str = "GCP_LOCATION"
           VERTEX_AI_MODEL: str = "VERTEX_AI_MODEL"
           FIRESTORE_DATABASE_ID: str = "FIRESTORE_DATABASE_ID"
           DATASETS_BUCKET: str = "DATASETS_BUCKET_NAME"  # deduplicated (was DATASETS_BUCKET_NAME_ENV_VAR + DATASETS_BUCKET_ENV_VAR)
           DATASETS_BUCKET_DEFAULT: str = "juno-preset-data"
           CARE_PLAN_DEFAULT_VERSION: str = "CARE_PLAN_DEFAULT_VERSION"
           CARE_PLAN_DEFAULT_VERSION_FALLBACK: str = "v1-2"
           ATHENA_CLIENT_ID: str = "ATHENA_HEALTH_TEST_CLIENT_ID"
           ATHENA_CLIENT_SECRET: str = "ATHENA_HEALTH_TEST_CLIENT_SECRET"
           K_SERVICE: str = "K_SERVICE"
           SERVICE_VERSION: str = "SERVICE_VERSION"
           WORKER_VERIFY_OIDC: str = "WORKER_VERIFY_OIDC"
           WORKER_SERVICE_ACCOUNT: str = "WORKER_SERVICE_ACCOUNT"
           CLOUD_TASKS_QUEUE: str = "CLOUD_TASKS_QUEUE"
           WORKER_URL: str = "WORKER_URL"
           PORT: str = "PORT"
           FLASK_ENV: str = "FLASK_ENV"
           JUNO_MODE: str = "JUNO_MODE"

       class Observability:
           SERVICE_NAME_DEFAULT: str = "backend-processing"
           LOG_EXTRA_KEYS: list[str] = [
               "user_id", "function", "care_plan_version", "grading_version", "input_version",
               "operation", "metric", "metric_type", "duration_ms", "success", "outcome",
               "step_name", "status", "http_method", "http_path", "http_status",
               "http_status_code", "total_duration_ms", "saved_id", "input_chars",
               "error", "labels", "duration_ms_observed", "OpOutcome",
               "service", "environment",
           ]
           DIM_OUTCOME: str = "OpOutcome"
           DIM_STATUS_CODE: str = "StatusCode"
           DIM_CORRELATION_ID: str = "CorrelationId"


   # ---------------------------------------------------------------------------
   # Backward-compat flat shims — kept for callsites not yet migrated.
   # TODO(SP03+): remove each shim once its consumer migrates to Constants.<Namespace>.<NAME>.
   # ---------------------------------------------------------------------------
   Constants.RESULT_SENTINEL               = Constants.Pipeline.RESULT_SENTINEL
   Constants.MAX_BATCH_RUNS               = Constants.Batch.MAX_BATCH_RUNS
   Constants.ALLOWED_EXTENSIONS           = Constants.Uploads.ALLOWED_EXTENSIONS
   Constants.MAX_FILE_BYTES               = Constants.Uploads.MAX_FILE_BYTES
   Constants.MAX_FILE_COUNT               = Constants.Uploads.MAX_FILE_COUNT
   Constants.MAX_AGGREGATE_FILE_BYTES     = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES
   Constants.PIPELINE_VERSION_V1_2        = Constants.Pipeline.PIPELINE_VERSION_V1_2
   Constants.ALLOWED_VERSIONS             = Constants.Pipeline.ALLOWED_VERSIONS
   Constants.STEPS                        = Constants.Pipeline.STEPS
   Constants.CARE_PLAN_VERSIONS           = Constants.Pipeline.CARE_PLAN_VERSIONS
   Constants.GRADING_METHODS              = Constants.Grading.GRADING_METHODS
   Constants.SOURCE                       = Constants.Enums.SOURCE
   Constants.IMPORTANCE                   = Constants.Enums.IMPORTANCE
   Constants.ATHENA_BASE_URL              = Constants.Athena.BASE_URL
   Constants.ATHENA_PRACTICE_ID           = Constants.Athena.PRACTICE_ID
   Constants.GCS_BUCKET_ENV_VAR           = Constants.Storage.GCS_BUCKET_ENV_VAR
   Constants.DATASETS_BUCKET_NAME_ENV_VAR = Constants.EnvVars.DATASETS_BUCKET  # dedup
   Constants.DATASETS_BUCKET_ENV_VAR      = Constants.EnvVars.DATASETS_BUCKET  # dedup
   Constants.DATASETS_BUCKET_NAME_DEFAULT = Constants.EnvVars.DATASETS_BUCKET_DEFAULT
   Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR     = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION
   Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK    = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION_FALLBACK
   Constants.ATHENA_CLIENT_ID_ENV_VAR     = Constants.EnvVars.ATHENA_CLIENT_ID
   Constants.ATHENA_CLIENT_SECRET_ENV_VAR = Constants.EnvVars.ATHENA_CLIENT_SECRET
   ```

2. Confirm `from enum import Enum, StrEnum` is at the top (StrEnum requires Python 3.11+; the project uses Python 3.12 so this is fine).

3. Run `python -c "from utils.constants import Constants; print(Constants.RESULT_SENTINEL)"` from `backend/` to confirm the module loads and the shim resolves.

**Acceptance:**
- `python -c "from utils.constants import Constants; assert Constants.Llm.MAX_TOKENS_LONG_FORM == 65536; assert Constants.Athena.AthenaSourceKind.ATHENA_ENCOUNTER == 'athena_encounter'; assert Constants.RESULT_SENTINEL == '__result__'"` exits 0.
- `grep -n "DATASETS_BUCKET_NAME_ENV_VAR\|DATASETS_BUCKET_ENV_VAR" backend/utils/constants.py` returns only the two shim lines (no definition-level duplication).

**Commit:** `refactor(constants): rewrite with namespaced nested classes and backward-compat shims`

---

### Task 02.2: Add config accessor `utils/env.py`

**Goal:** Implement a thin `get_env(key, default=None, *, required=False)` accessor that centralizes `os.environ.get` calls, makes test mocking trivial (mock one function instead of patching `os.environ` at every callsite), and optionally raises on missing required vars at startup. This satisfies user decision Q2 (YES — add config accessor). The accessor is not wired to existing callsites in this SP — those migrate in SP03+. It is placed in `backend/utils/env.py` as a new module.

**Files:**
- `backend/utils/env.py` — new file

**Steps:**

1. Create `backend/utils/env.py` with the following content:

   ```python
   """utils/env.py — Centralized environment-variable accessor.

   Usage:
       from utils.env import get_env
       from utils.constants import Constants

       project_id = get_env(Constants.EnvVars.GCP_PROJECT_ID)
       bucket     = get_env(Constants.EnvVars.GCS_BUCKET, required=True)

   Why:
       - Single patch point for test mocking (mock utils.env.get_env).
       - Explicit required=True raises at startup with a clear message
         instead of silently passing None into downstream code.
   """

   import os
   from typing import Optional


   def get_env(key: str, default: Optional[str] = None, *, required: bool = False) -> Optional[str]:
       """Return os.environ.get(key, default).

       Args:
           key: Environment variable name (use Constants.EnvVars.* for all names).
           default: Value to return when the variable is absent. Ignored when
               required=True.
           required: If True and the variable is absent or empty, raise
               EnvironmentError with a descriptive message.

       Returns:
           The variable value as a string, or default if absent (and not required).

       Raises:
           EnvironmentError: When required=True and the variable is absent or empty.
       """
       value = os.environ.get(key)
       if required and not value:
           raise EnvironmentError(
               f"Required environment variable '{key}' is not set. "
               f"Set it before starting the server."
           )
       return value if value is not None else default
   ```

2. Add a unit test file `backend/tests/utils/test_env.py`:

   ```python
   """Tests for utils/env.py get_env accessor."""

   import os
   import pytest
   from unittest.mock import patch

   from utils.env import get_env


   def test_returns_env_value(monkeypatch):
       monkeypatch.setenv("TEST_VAR_SP02", "hello")
       assert get_env("TEST_VAR_SP02") == "hello"


   def test_returns_default_when_absent():
       os.environ.pop("TEST_VAR_SP02_ABSENT", None)
       assert get_env("TEST_VAR_SP02_ABSENT", "fallback") == "fallback"


   def test_returns_none_when_absent_no_default():
       os.environ.pop("TEST_VAR_SP02_ABSENT", None)
       assert get_env("TEST_VAR_SP02_ABSENT") is None


   def test_required_raises_when_absent():
       os.environ.pop("TEST_VAR_SP02_REQUIRED", None)
       with pytest.raises(EnvironmentError, match="TEST_VAR_SP02_REQUIRED"):
           get_env("TEST_VAR_SP02_REQUIRED", required=True)


   def test_required_succeeds_when_set(monkeypatch):
       monkeypatch.setenv("TEST_VAR_SP02_REQUIRED", "value")
       assert get_env("TEST_VAR_SP02_REQUIRED", required=True) == "value"


   def test_mockable_via_patch():
       with patch("utils.env.os.environ.get", return_value="mocked"):
           assert get_env("ANY_KEY") == "mocked"
   ```

**Acceptance:**
- `pytest backend/tests/utils/test_env.py -v` passes all 6 tests.
- `python -c "from utils.env import get_env"` from `backend/` exits 0.

**Commit:** `feat(utils): add get_env config accessor for centralized env-var reads`

---

### Task 02.3: Migrate scattered constants in `utils/athena_client.py`

**Goal:** Remove the module-level literals `BATCH_SIZE = 2`, `BATCH_SLEEP_S = 30` and the class-level attrs `TOKEN_TTL_S = 300`, `TOKEN_REFRESH_BUFFER_S = 20` from `athena_client.py`. Replace all their usages in the same file with `Constants.Athena.*`. Also update the hardcoded string `"athena/service/Athenanet.MDP.*"`, `timeout=30` (token POST), `retries: int = 3`, and `timeout=60` (GET) to use `Constants.Athena.*`.

**Files:**
- `backend/utils/athena_client.py`

**Steps:**

1. Delete lines 20–21 (`BATCH_SIZE = 2` and `BATCH_SLEEP_S = 30`) from the module-level.

2. Find all usages of `BATCH_SIZE` and `BATCH_SLEEP_S` in the file. Replace each with `Constants.Athena.BATCH_SIZE` and `Constants.Athena.BATCH_SLEEP_S`.

3. In class `AthenaClient`, delete lines 40–41 (`TOKEN_TTL_S: int = 300` and `TOKEN_REFRESH_BUFFER_S: int = 20`).

4. Find `self.TOKEN_TTL_S` references in the class and replace with `Constants.Athena.TOKEN_TTL_S`. Find `self.TOKEN_REFRESH_BUFFER_S` and replace with `Constants.Athena.TOKEN_REFRESH_BUFFER_S`.

5. At the `get_token` method scope:
   - Line 59 (approximately): change `"scope": "athena/service/Athenanet.MDP.*"` to `"scope": Constants.Athena.OAUTH_SCOPE`
   - Line 61 (approximately): change `timeout=30` to `timeout=Constants.Athena.HTTP_TIMEOUT_TOKEN_S`

6. At the `_get` method signature (line 70 approximately): change `retries: int = 3` to `retries: int = Constants.Athena.MAX_RETRIES`.

7. At the GET request inside `_get` (line 77 approximately): change `timeout=60` to `timeout=Constants.Athena.HTTP_TIMEOUT_GET_S`.

8. Ensure `from utils.constants import Constants` is already at the top of the file (it is — line 16 in current code). No new import needed.

**Acceptance:**
- `grep -n "BATCH_SIZE\s*=\s*2\|BATCH_SLEEP_S\s*=\s*30\|TOKEN_TTL_S\s*=\|TOKEN_REFRESH_BUFFER_S\s*=" backend/utils/athena_client.py` returns zero hits.
- `grep -n '"athena/service/Athenanet' backend/utils/athena_client.py` returns zero hits.
- `python -c "from utils.athena_client import AthenaClient"` exits 0.

**Commit:** `refactor(athena): replace inline literals with Constants.Athena.*`

---

### Task 02.4: Migrate scattered constants in `utils/llm.py`

**Goal:** Replace the inline hardcoded values in `LLMClient.__init__` and the method signatures of `generate_text` / `generate_json` with `Constants.Llm.*` and `Constants.EnvVars.*`.

**Files:**
- `backend/utils/llm.py`

**Steps:**

1. Add `from utils.constants import Constants` to the import block (it is not currently imported in this file — verify with a quick scan of the top of `llm.py`).

2. In `LLMClient.__init__` (line 44 approximately): change
   ```python
   model_name = os.environ.get("VERTEX_AI_MODEL", "gemini-1.5-pro")
   ```
   to:
   ```python
   model_name = os.environ.get(Constants.EnvVars.VERTEX_AI_MODEL, Constants.Llm.MODEL_DEFAULT)
   ```

3. In `generate_text` signature (line 60 approximately): change `temperature: float = 0.3, max_tokens: int = 8192` to `temperature: float = Constants.Llm.TEMPERATURE_TEXT, max_tokens: int = Constants.Llm.MAX_TOKENS`.

4. In `generate_json` signature (line 117 approximately): change `temperature: float = 0.2, max_tokens: int = 8192` to `temperature: float = Constants.Llm.TEMPERATURE_JSON, max_tokens: int = Constants.Llm.MAX_TOKENS`.

> Note: The `location = os.environ.get("GCP_LOCATION", "us-central1")` on line 47 is left as-is for this SP; it is a local default that can migrate in a later SP once `get_env` wiring is tackled. The `GCP_PROJECT_ID` and `GCP_LOCATION` reads are single-use infrastructure init calls and are low-priority.

**Acceptance:**
- `grep -n '"gemini-1.5-pro"\|temperature.*=.*0\.\(3\|2\)\|max_tokens.*=.*8192' backend/utils/llm.py` returns zero hits.
- `python -c "from utils.llm import LLMClient"` exits 0 (no import errors).

**Commit:** `refactor(llm): replace inline model/temperature/token literals with Constants.Llm.*`

---

### Task 02.5: Migrate constants in `care_plan/v1_2/pipeline.py`

**Goal:** Replace the default argument literals `temperature=0.3` / `temperature=0.2` in `_generate_text` / `_generate_json` with `Constants.Llm.*`, and replace the two explicit `max_tokens=65536` calls in `simplify_language_with_term_plan` (line 108) and `clarify_and_action` (line 124) with `Constants.Llm.MAX_TOKENS_LONG_FORM`.

**Files:**
- `backend/care_plan/v1_2/pipeline.py`

**Steps:**

1. Add `from utils.constants import Constants` to the import block if not already present (verify at the top of `pipeline.py`).

2. In `_generate_text` signature (line 74 approximately): change `temperature: float = 0.3` to `temperature: float = Constants.Llm.TEMPERATURE_TEXT`. Change `max_tokens: int = 8192` to `max_tokens: int = Constants.Llm.MAX_TOKENS`.

3. In `_generate_json` signature (line 83 approximately): change `temperature: float = 0.2` to `temperature: float = Constants.Llm.TEMPERATURE_JSON`. Change `max_tokens: int = 8192` to `max_tokens: int = Constants.Llm.MAX_TOKENS`.

4. In `simplify_language_with_term_plan` (line 108 approximately): change `max_tokens=65536` to `max_tokens=Constants.Llm.MAX_TOKENS_LONG_FORM`.

5. In `clarify_and_action` (line 124 approximately): change `max_tokens=65536` to `max_tokens=Constants.Llm.MAX_TOKENS_LONG_FORM`.

**Acceptance:**
- `grep -n "65536\|temperature.*0\.\(3\|2\)\|max_tokens.*8192" backend/care_plan/v1_2/pipeline.py` returns zero hits.
- `python -c "from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline"` exits 0.

**Commit:** `refactor(pipeline): replace inline LLM literals with Constants.Llm.*`

---

### Task 02.6: Migrate constants in `utils/gcs_datasets.py`

**Goal:** Remove the module-level `GCS_PRESET_PREFIX` and `TEMP_BASE` literals and replace their usages with `Constants.Storage.*`.

**Files:**
- `backend/utils/gcs_datasets.py`

**Steps:**

1. Add `from utils.constants import Constants` to the imports (currently not imported — verify at top of the file).

2. Delete lines 13–14:
   ```python
   GCS_PRESET_PREFIX = "preset-data"
   TEMP_BASE = Path("/tmp/juno-datasets")
   ```

3. Search the rest of `gcs_datasets.py` for all usages of `GCS_PRESET_PREFIX` and `TEMP_BASE`. Replace:
   - `GCS_PRESET_PREFIX` → `Constants.Storage.GCS_PRESET_PREFIX`
   - `TEMP_BASE` → `Path(Constants.Storage.TEMP_BASE)` (since `TEMP_BASE` was previously a `Path`, maintain path-object semantics at the callsites)

4. Confirm `Path` is still imported from `pathlib` (it is — line 7 of the current file).

**Acceptance:**
- `grep -n "GCS_PRESET_PREFIX\s*=\|TEMP_BASE\s*=\s*Path" backend/utils/gcs_datasets.py` returns zero hits.
- `python -c "from utils.gcs_datasets import download_dataset_inputs"` exits 0.

**Commit:** `refactor(gcs_datasets): replace GCS_PRESET_PREFIX and TEMP_BASE literals with Constants.Storage.*`

---

### Task 02.7: Migrate constants in `utils/markers/marker.py`

**Goal:** Remove the three `DIM_*` module-level literals and replace their usages with `Constants.Observability.*`.

**Files:**
- `backend/utils/markers/marker.py`

**Steps:**

1. Add `from utils.constants import Constants` to the imports at the top of `marker.py`.

2. Delete lines 20–22:
   ```python
   DIM_OUTCOME = "OpOutcome"
   DIM_STATUS_CODE = "StatusCode"
   DIM_CORRELATION_ID = "CorrelationId"
   ```

3. Search the rest of `marker.py` (and any other file in `backend/utils/markers/` that imports `DIM_OUTCOME`, `DIM_STATUS_CODE`, or `DIM_CORRELATION_ID` from `marker.py`) for all usages. Replace each with `Constants.Observability.DIM_OUTCOME`, `Constants.Observability.DIM_STATUS_CODE`, and `Constants.Observability.DIM_CORRELATION_ID` respectively.

4. Run `grep -rn "from utils.markers.marker import DIM\|from .marker import DIM" backend/` to find any external importers of these names. Update those import sites to either import from `Constants.Observability.*` directly or remove the import if the constant is no longer referenced after step 3.

**Acceptance:**
- `grep -n "DIM_OUTCOME\s*=\|DIM_STATUS_CODE\s*=\|DIM_CORRELATION_ID\s*=" backend/utils/markers/marker.py` returns zero hits.
- `python -c "from utils.markers.marker import Scope"` exits 0.

**Commit:** `refactor(markers): replace DIM_* literals with Constants.Observability.*`

---

### Task 02.8: Migrate constants in `routes/worker.py`

**Goal:** Remove the module-level `SINGLE_JOB_INTERNAL_DEADLINE_S = 270` and `BATCH_ITEM_INTERNAL_DEADLINE_S = 870` literals and replace their usages with `Constants.Deadlines.*`.

**Files:**
- `backend/routes/worker.py`

**Steps:**

1. Delete lines 27–28:
   ```python
   SINGLE_JOB_INTERNAL_DEADLINE_S = 270
   BATCH_ITEM_INTERNAL_DEADLINE_S = 870
   ```

2. In the `execute_job` function body (around line 185), replace:
   - `BATCH_ITEM_INTERNAL_DEADLINE_S` → `Constants.Deadlines.BATCH_ITEM_INTERNAL_DEADLINE_S`
   - `SINGLE_JOB_INTERNAL_DEADLINE_S` → `Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S`

3. Confirm `from utils.constants import Constants` is already imported (it is — line 20 in the current file).

**Acceptance:**
- `grep -n "SINGLE_JOB_INTERNAL_DEADLINE_S\s*=\|BATCH_ITEM_INTERNAL_DEADLINE_S\s*=" backend/routes/worker.py` returns zero hits.
- `python -c "from routes.worker import worker_bp"` exits 0.

**Commit:** `refactor(worker): replace deadline literals with Constants.Deadlines.*`

---

### Task 02.9: Migrate constants in `routes/care_plan_jobs.py` and `routes/batch_jobs.py`

**Goal:** Replace the inline `os.environ.get("JOB_TIMEOUT_SECONDS_SINGLE", "300")` and `os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900")` calls with `Constants.Deadlines.*`. Also update the hardcoded `"10 MB limit"` string in `care_plan_jobs.py` to derive its value from `Constants.Uploads.MAX_FILE_BYTES`.

**Files:**
- `backend/routes/care_plan_jobs.py`
- `backend/routes/batch_jobs.py`

**Steps:**

1. In `backend/routes/care_plan_jobs.py`:
   - Find the line (approximately 129) containing `int(os.environ.get("JOB_TIMEOUT_SECONDS_SINGLE", "300"))`. Replace it with `Constants.Deadlines.JOB_TIMEOUT_SECONDS_SINGLE` (the constant is already an `int`; remove the `int(os.environ.get(...))` wrapper entirely).
   - Find line 68 approximately: `raise ValueError("Stored file exceeds 10 MB limit")`. Change to: `raise ValueError(f"Stored file exceeds {Constants.Uploads.MAX_FILE_BYTES // (1024 * 1024)} MB limit")`.
   - Confirm `from utils.constants import Constants` is already imported (verify at top of file). Confirm `os` is still imported if still used elsewhere in the file; if not, remove the `import os` line.

2. In `backend/routes/batch_jobs.py`:
   - Find line 78 approximately: `deadline_s = int(os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900"))`. Replace with `deadline_s = Constants.Deadlines.JOB_TIMEOUT_SECONDS_BATCH`.
   - Confirm `from utils.constants import Constants` is already imported (verify at top of file).

**Acceptance:**
- `grep -n "JOB_TIMEOUT_SECONDS_SINGLE\|JOB_TIMEOUT_SECONDS_BATCH" backend/routes/care_plan_jobs.py backend/routes/batch_jobs.py` shows only the `Constants.Deadlines.*` references, no `os.environ.get`.
- `grep -n '"10 MB limit"' backend/routes/care_plan_jobs.py` returns zero hits.
- `python -c "from routes.care_plan_jobs import care_plan_jobs_bp; from routes.batch_jobs import batch_jobs_bp"` exits 0.

**Commit:** `refactor(routes): replace job-timeout env reads and file-size literal with Constants.*`

---

### Task 02.10: Remove aliases in `routes/care_plan.py` and `routes/batch.py`

**Goal:** Delete the three needless re-alias lines in `care_plan.py` (lines 21–22, 35) and the unused alias in `batch.py` (line 10). Update the downstream usages within `care_plan.py` to use namespaced `Constants.*` forms. Remove `GRADING_VERSION` and `INPUT_VERSION` from the import lines since those symbols move in the next task.

**Files:**
- `backend/routes/care_plan.py`
- `backend/routes/batch.py`

**Steps:**

1. In `backend/routes/care_plan.py`:

   a. Delete line 21: `RESULT_SENTINEL = Constants.RESULT_SENTINEL`
   b. Delete line 22: `MAX_AGGREGATE_FILE_BYTES = Constants.MAX_AGGREGATE_FILE_BYTES`
   c. Delete line 35: `CARE_PLAN_VERSION = Constants.CARE_PLAN_VERSIONS.V1_2.value`
   d. Delete line 46: `_UPLOAD_PREFIX = "care_plan-uploads"` (this is the upload prefix literal migrated in Task 02.1)

   e. Update references within `care_plan.py`:
      - Line 400 approximately: `yield (Constants.RESULT_SENTINEL, ...)` — the alias deletion means this already works via the flat shim, but update to the namespaced form: `yield (Constants.Pipeline.RESULT_SENTINEL, ...)`.
      - Line 174 approximately: `if aggregate_bytes > MAX_AGGREGATE_FILE_BYTES:` — change to `if aggregate_bytes > Constants.Uploads.MAX_AGGREGATE_FILE_BYTES:`. Also fix line 175: `limit_mb = MAX_AGGREGATE_FILE_BYTES // (1024 * 1024)` → `limit_mb = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES // (1024 * 1024)`.
      - Line 366 approximately: `CarePlan.from_pipeline_result("1.2", {...})` — change `"1.2"` to `Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value`.
      - Any usage of `_UPLOAD_PREFIX` in the file (find with grep): replace with `Constants.Uploads.UPLOAD_PREFIX`.

   f. Line 29 imports `GRADING_VERSION` from `models.grading`. Line 32 imports `INPUT_VERSION` from `models.input`. After Task 02.11 adds re-exports to those modules, these imports will still work. No change needed here — leave them as is. (If the implementer prefers using `Constants.Schema.*` directly, either approach is acceptable.)

   g. Line 38: `from telemetry import get_tracer` — update to `from observability.telemetry import get_tracer`. (This is the observability move from Task 02.13; if doing tasks in order, do this change in Task 02.13 instead.)

2. In `backend/routes/batch.py`:
   - Delete line 10: `MAX_BATCH_RUNS = Constants.MAX_BATCH_RUNS`
   - Confirm `MAX_BATCH_RUNS` is never referenced again in `batch.py` (grep confirms it is not — the batch-size check is in `batch_jobs.py`).

**Acceptance:**
- `grep -n "^RESULT_SENTINEL\s*=\|^MAX_AGGREGATE_FILE_BYTES\s*=\|^CARE_PLAN_VERSION\s*=\|^_UPLOAD_PREFIX\s*=\|^MAX_BATCH_RUNS\s*=" backend/routes/care_plan.py backend/routes/batch.py` returns zero hits.
- `python -c "from routes.care_plan import care_plan_bp; from routes.batch import batch_bp"` exits 0.

**Commit:** `refactor(routes): remove needless aliases from care_plan.py and batch.py`

---

### Task 02.11: Update `models/input.py` and `models/grading.py` to use Constants

**Goal:** Remove the standalone `INPUT_VERSION = "1.0"` and `GRADING_VERSION = "1.0"` literals from the model files. Per PRD Q3 (RESOLVED): keep them as re-exports so SP03 model consumers need no import-site changes.

**Files:**
- `backend/models/input.py`
- `backend/models/grading.py`

**Steps:**

1. In `backend/models/input.py`:
   - Add `from utils.constants import Constants` to the imports.
   - Change line 15 from `INPUT_VERSION = "1.0"` to `INPUT_VERSION = Constants.Schema.INPUT_VERSION` (re-export for backward compatibility with importers like `routes/care_plan.py`).

2. In `backend/models/grading.py`:
   - Confirm `from utils.constants import Constants` is already imported (it is — line 8 in the current file).
   - Change line 11 from `GRADING_VERSION = "1.0"` to `GRADING_VERSION = Constants.Schema.GRADING_VERSION` (re-export).

**Acceptance:**
- `grep -n '"1\.0"' backend/models/input.py backend/models/grading.py` returns zero hits.
- `python -c "from models.input import INPUT_VERSION; from models.grading import GRADING_VERSION; assert INPUT_VERSION == '1.0'; assert GRADING_VERSION == '1.0'"` exits 0.

**Commit:** `refactor(models): replace VERSION literals with Constants.Schema re-exports`

---

### Task 02.12: Migrate constants in `logging_config.py` and `telemetry.py`

**Goal:** Replace the `_EXTRA_KEYS` module-level list in `logging_config.py` with `Constants.Observability.LOG_EXTRA_KEYS`. Replace the two `"backend-processing"` hardcoded strings in `telemetry.py` with `Constants.Observability.SERVICE_NAME_DEFAULT`. Also update the env-var key in `telemetry.py` to use `Constants.EnvVars.K_SERVICE`.

**Files:**
- `backend/logging_config.py`
- `backend/telemetry.py`

**Steps:**

1. In `backend/logging_config.py`:
   - Add `from utils.constants import Constants` to the imports.
   - Delete lines 32–39 (the `_EXTRA_KEYS = [...]` block).
   - Replace every reference to `_EXTRA_KEYS` in the file (line 90 approximately in `StructuredJsonFormatter.format`) with `Constants.Observability.LOG_EXTRA_KEYS`.

2. In `backend/telemetry.py`:
   - Add `from utils.constants import Constants` to the imports.
   - Line 64 approximately: change `os.getenv("K_SERVICE", "backend-processing")` to `os.getenv(Constants.EnvVars.K_SERVICE, Constants.Observability.SERVICE_NAME_DEFAULT)`.
   - Line 96 approximately: change `def get_tracer(name: str = "backend-processing"):` to `def get_tracer(name: str = Constants.Observability.SERVICE_NAME_DEFAULT):`.

> Note: `utils/juno_logger.py` line 24 has `_SERVICE = os.getenv("K_SERVICE", "juno-backend")` — the env-var name `"K_SERVICE"` should ideally become `Constants.EnvVars.K_SERVICE` too, but the `"juno-backend"` default is intentionally different from `"backend-processing"` (per PRD §4b note) and is left as a plain string. Update only the env-var key: change `"K_SERVICE"` to `Constants.EnvVars.K_SERVICE` in `juno_logger.py` if convenient, but leave `"juno-backend"` as-is.

**Acceptance:**
- `grep -n "_EXTRA_KEYS\s*=" backend/logging_config.py` returns zero hits.
- `grep -n '"backend-processing"' backend/telemetry.py` returns zero hits.
- `python -c "from logging_config import setup_logging, StructuredJsonFormatter"` exits 0.
- `python -c "from telemetry import get_tracer, init_telemetry"` exits 0.

**Commit:** `refactor(observability): replace _EXTRA_KEYS list and service-name literals with Constants.*`

---

### Task 02.13: Create `backend/observability/` package and move observability modules

**Goal:** Create a new `backend/observability/` package. Move `backend/logging_config.py` → `backend/observability/logging_config.py` and `backend/telemetry.py` → `backend/observability/telemetry.py`. Add `backend/observability/__init__.py` with convenience re-exports. Update all import sites.

**Files:**
- `backend/observability/__init__.py` — new file
- `backend/observability/logging_config.py` — moved from `backend/logging_config.py`
- `backend/observability/telemetry.py` — moved from `backend/telemetry.py`
- `backend/logging_config.py` — deleted
- `backend/telemetry.py` — deleted
- `backend/app.py` — update imports
- `backend/routes/care_plan.py` — update imports
- `backend/tests/utils/test_telemetry_version.py` — update imports
- `backend/tests/utils/test_logging_config.py` — update imports

**Steps:**

1. Create the directory `backend/observability/`.

2. Copy the content of `backend/logging_config.py` (as modified by Task 02.12) to `backend/observability/logging_config.py`. No further content changes needed.

3. Copy the content of `backend/telemetry.py` (as modified by Task 02.12) to `backend/observability/telemetry.py`. No further content changes needed.

4. Create `backend/observability/__init__.py` with:

   ```python
   from observability.logging_config import setup_logging
   from observability.telemetry import init_telemetry, get_tracer

   __all__ = ["setup_logging", "init_telemetry", "get_tracer"]
   ```

5. Delete `backend/logging_config.py` and `backend/telemetry.py`.

6. Update `backend/app.py` lines 14–15:
   - Change `from logging_config import setup_logging` → `from observability import setup_logging`
   - Change `from telemetry import init_telemetry` → `from observability import init_telemetry`

7. Update `backend/routes/care_plan.py`:
   - Change `from telemetry import get_tracer` → `from observability.telemetry import get_tracer`

8. Update `backend/tests/utils/test_telemetry_version.py`:
   - Lines 14, 25, 52: change `from telemetry import _build_version` → `from observability.telemetry import _build_version`
   - Line 63: change `import telemetry` → `from observability import telemetry`

9. Update `backend/tests/utils/test_logging_config.py`:
   - Line 15: change `from logging_config import StructuredJsonFormatter` → `from observability.logging_config import StructuredJsonFormatter`
   - Line 97 (the `patch` call): change `"logging_config.trace.get_current_span"` → `"observability.logging_config.trace.get_current_span"`

**Acceptance:**
- `ls backend/*.py | grep -E "logging_config|telemetry"` returns no output (files deleted from root).
- `python -c "from observability import setup_logging, init_telemetry, get_tracer"` exits 0.
- `python -c "from observability.telemetry import _build_version"` exits 0.
- `pytest backend/tests/utils/test_telemetry_version.py backend/tests/utils/test_logging_config.py -v` all pass.

**Commit:** `refactor(observability): move logging_config and telemetry into backend/observability/ package`

---

### Task 02.14: Delete dead `backend/config.py`

**Goal:** `backend/config.py` has zero project importers (confirmed: `grep -rn "from config import\|import config" backend/ --include="*.py"` returns zero hits). Delete it.

**Files:**
- `backend/config.py` — deleted

**Steps:**

1. Verify no file imports `config` by running `grep -rn "from config import\|import config" backend/ --include="*.py"`. Expect zero hits.

2. Delete `backend/config.py`.

**Acceptance:**
- `ls backend/config.py` returns "No such file or directory".
- `python -c "import importlib.util; assert importlib.util.find_spec('config') is None"` exits 0.

**Commit:** `chore: delete dead backend/config.py (zero importers; defaults now live in Constants)`

---

### Task 02.15: Add unit tests for `utils/constants.py`

**Goal:** Create `backend/tests/utils/test_constants.py` with the test suite from PRD §7a, verifying all namespaces, the `AthenaSourceKind` enum, the deduplication fix, and the backward-compat flat shims.

**Files:**
- `backend/tests/utils/test_constants.py` — new file

**Steps:**

1. Create `backend/tests/utils/test_constants.py` with the following content (copied verbatim from PRD §7a, no changes needed):

   ```python
   from utils.constants import Constants


   def test_schema_namespace():
       assert Constants.Schema.INPUT_VERSION == "1.0"
       assert Constants.Schema.GRADING_VERSION == "1.0"
       assert Constants.Schema.SUMMARY_SCHEMA_VERSION_1_4 == "1.4"


   def test_uploads_namespace():
       assert Constants.Uploads.MAX_FILE_BYTES == 10 * 1024 * 1024
       assert Constants.Uploads.MAX_AGGREGATE_FILE_BYTES == 25 * 1024 * 1024
       assert "pdf" in Constants.Uploads.ALLOWED_EXTENSIONS
       assert Constants.Uploads.UPLOAD_PREFIX == "care_plan-uploads"


   def test_deadlines_namespace():
       assert Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S == 270
       assert Constants.Deadlines.BATCH_ITEM_INTERNAL_DEADLINE_S == 870
       assert Constants.Deadlines.JOB_TIMEOUT_SECONDS_SINGLE == 300
       assert Constants.Deadlines.JOB_TIMEOUT_SECONDS_BATCH == 900


   def test_llm_namespace():
       assert Constants.Llm.MODEL_DEFAULT == "gemini-1.5-pro"
       assert Constants.Llm.TEMPERATURE_TEXT == 0.3
       assert Constants.Llm.TEMPERATURE_JSON == 0.2
       assert Constants.Llm.MAX_TOKENS == 8192
       assert Constants.Llm.MAX_TOKENS_LONG_FORM == 65536


   def test_athena_namespace():
       assert Constants.Athena.BATCH_SIZE == 2
       assert Constants.Athena.BATCH_SLEEP_S == 30
       assert Constants.Athena.TOKEN_TTL_S == 300
       assert Constants.Athena.TOKEN_REFRESH_BUFFER_S == 20
       assert Constants.Athena.HTTP_TIMEOUT_TOKEN_S == 30
       assert Constants.Athena.HTTP_TIMEOUT_GET_S == 60
       assert Constants.Athena.MAX_RETRIES == 3
       assert "Athenanet" in Constants.Athena.OAUTH_SCOPE


   def test_athena_source_kind_enum():
       sk = Constants.Athena.AthenaSourceKind
       assert sk.ATHENA_ENCOUNTER == "athena_encounter"
       assert sk.ATHENA_CLINICAL_DOC == "athena_clinical_doc"


   def test_storage_namespace():
       assert Constants.Storage.GCS_PRESET_PREFIX == "preset-data"
       assert Constants.Storage.TEMP_BASE == "/tmp/juno-datasets"
       assert Constants.Storage.SIGNED_URL_TTL_MIN == 30


   def test_observability_namespace():
       assert Constants.Observability.SERVICE_NAME_DEFAULT == "backend-processing"
       assert "user_id" in Constants.Observability.LOG_EXTRA_KEYS
       assert Constants.Observability.DIM_OUTCOME == "OpOutcome"


   def test_env_vars_namespace_deduplicated():
       assert Constants.EnvVars.DATASETS_BUCKET == "DATASETS_BUCKET_NAME"


   def test_flat_shims_still_work():
       assert Constants.RESULT_SENTINEL == Constants.Pipeline.RESULT_SENTINEL
       assert Constants.MAX_BATCH_RUNS == Constants.Batch.MAX_BATCH_RUNS
       assert Constants.GRADING_METHODS is Constants.Grading.GRADING_METHODS
       assert Constants.ATHENA_BASE_URL == Constants.Athena.BASE_URL
   ```

**Acceptance:**
- `pytest backend/tests/utils/test_constants.py -v` passes all tests.

**Commit:** `test(constants): add test_constants.py verifying all namespaces and shims`

---

### Task 02.16: Add integration tests for backend root cleanliness

**Goal:** Extend `backend/tests/integration/test_dead_code_removed.py` with the two integration tests from PRD §7b: `test_config_py_deleted` and `test_backend_root_only_app_and_error_codes`.

**Files:**
- `backend/tests/integration/test_dead_code_removed.py` — extend existing file

**Steps:**

1. Open `backend/tests/integration/test_dead_code_removed.py`.

2. Add at the end of the file:

   ```python
   import importlib.util
   import pathlib


   def test_config_py_deleted():
       import sys
       sys.modules.pop("config", None)
       assert importlib.util.find_spec("config") is None, \
           "backend/config.py must not exist after SP02"


   def test_backend_root_only_app_and_error_codes():
       """After SP02: only app.py and error_codes.py live at backend/ root."""
       root = pathlib.Path(__file__).parent.parent.parent  # backend/
       py_files = {f.name for f in root.glob("*.py") if f.is_file()}
       allowed = {"app.py", "error_codes.py"}
       unexpected = py_files - allowed
       assert not unexpected, f"Unexpected .py files at backend root: {unexpected}"
   ```

   > Note: `importlib` and `pathlib` are already in the stdlib; no new pip dependency needed. The existing file already imports `sys` and `pytest` at the top.

**Acceptance:**
- `pytest backend/tests/integration/test_dead_code_removed.py -v` passes all tests including the two new ones.

**Commit:** `test(integration): guard config.py deletion and backend-root .py file count`

---

## Verification

Run from the `backend/` directory after all tasks are complete.

### Lint / import checks

```bash
# No syntax errors anywhere in the backend
python -m py_compile utils/constants.py utils/env.py utils/athena_client.py \
    utils/llm.py utils/gcs_datasets.py utils/markers/marker.py \
    routes/care_plan.py routes/batch.py routes/worker.py \
    routes/care_plan_jobs.py routes/batch_jobs.py routes/saved_outputs.py \
    models/input.py models/grading.py \
    care_plan/v1_2/pipeline.py \
    observability/logging_config.py observability/telemetry.py \
    app.py

# No remaining inline literals that should have been migrated
grep -rn "gemini-1.5-pro\|BATCH_SIZE = 2\|BATCH_SLEEP_S\s*=\s*30\|TOKEN_TTL_S\s*=\s*300\|TOKEN_REFRESH_BUFFER_S\s*=\s*20" backend/ --include="*.py" | grep -v "constants.py"
# Expected: zero hits

# No remaining top-level .py files except app.py and error_codes.py
ls backend/*.py
# Expected: only app.py and error_codes.py
```

### Unit tests

```bash
# New constants test suite
pytest tests/utils/test_constants.py -v

# New env accessor tests
pytest tests/utils/test_env.py -v

# Observability regression (import path changed to observability.*)
pytest tests/utils/test_telemetry_version.py tests/utils/test_logging_config.py -v

# Smoke: routes and utils that consumed the migrated constants
pytest tests/routes/test_worker.py tests/routes/test_batch_jobs.py \
    tests/utils/test_athena_client.py tests/utils/test_gcs_datasets.py -v
```

### Integration tests

```bash
pytest tests/integration/test_dead_code_removed.py -v
# Must include: test_config_py_deleted, test_backend_root_only_app_and_error_codes
```

### Full suite

```bash
pytest --tb=short -q
```

### Definition of Done

- All `pytest` runs above exit 0 with no failures.
- `ls backend/*.py` lists exactly `app.py` and `error_codes.py`.
- `python -c "from utils.constants import Constants; from observability import setup_logging, init_telemetry, get_tracer; from utils.env import get_env"` exits 0.
- `grep -rn "gemini-1.5-pro\|BATCH_SIZE = 2\|BATCH_SLEEP_S\s*=\s*30\|TOKEN_TTL_S\s*=\|TOKEN_REFRESH_BUFFER_S\s*=" backend/ --include="*.py" | grep -v constants.py` returns zero hits.
