# PRD: SP02 — Constants Consolidation + Backend-Root Layout

**Sub-project:** SP02
**Branch context:** `users/tejitpabari/llm-code-check`
**Date:** 2026-06-29
**Status:** Planning — no implementation started

---

## 1. Problem

The Juno backend suffers from two related structural problems that compound as the codebase grows.

**Problem A — Constants are scattered and aliased:**

`backend/utils/constants.py` is a single flat `Constants` class (79 lines) organized only by inline comments. A dozen additional constants live as bare module-level or class-level literals in `utils/athena_client.py`, `utils/llm.py`, `utils/gcs_datasets.py`, `routes/care_plan.py`, `routes/worker.py`, `routes/batch_jobs.py`, `routes/care_plan_jobs.py`, `routes/saved_outputs.py`, `models/input.py`, `models/grading.py`, `logging_config.py`, `telemetry.py`, `utils/juno_logger.py`, and `utils/markers/marker.py`. Three aliases (`RESULT_SENTINEL`, `MAX_AGGREGATE_FILE_BYTES`, `CARE_PLAN_VERSION`) are re-imported into `routes/care_plan.py` from `Constants` with new names, adding noise. `routes/batch.py` imports `MAX_BATCH_RUNS` and then never uses the alias. `DATASETS_BUCKET_NAME_ENV_VAR` and `DATASETS_BUCKET_ENV_VAR` in `constants.py` are two names for the same string `"DATASETS_BUCKET_NAME"`, creating a silent duplicate.

**Problem B — Backend root has too many top-level modules:**

Flask convention is one entry point (`app.py`) at the package root; everything else belongs in a package. Currently five `.py` files live directly in `backend/`:

| File | Issue |
|---|---|
| `app.py` | Correct — keep |
| `config.py` | Dead: zero project imports. Its default values are already duplicated inline in the modules that actually need them. |
| `error_codes.py` | Managed by SP01 (pipeline error catalog). Not in this SP's scope. |
| `logging_config.py` | Observability infrastructure — belongs in a package |
| `telemetry.py` | Observability infrastructure — belongs in a package |

---

## 2. Goals

1. Redesign `utils/constants.py` into **namespaced nested classes** — every logical group is its own inner class so imports read `Constants.Llm.MODEL_DEFAULT` instead of hunting through a long flat list.
2. Migrate every scattered constant into its canonical namespace and remove the originals. After SP02, `grep -rn "gemini-1.5-pro\|BATCH_SIZE = 2\|BATCH_SLEEP_S\|TOKEN_TTL_S\|TOKEN_REFRESH_BUFFER_S"` in `backend/` (excluding `constants.py`) returns zero hits.
3. Remove the three `routes/care_plan.py` needless re-aliases and the unused `routes/batch.py` alias; replace all uses with `Constants.<Namespace>.<NAME>` directly.
4. Define `AthenaSourceKind(StrEnum)` inside `Constants` so SP04/SP06/SP07 can replace string literals with typed values.
5. Delete `backend/config.py` — it is dead code.
6. Move `backend/logging_config.py` and `backend/telemetry.py` into `backend/observability/` and update every import site.
7. After SP02, only `backend/app.py` (and the SP01-managed `backend/error_codes.py`) exist at the `backend/` root.

---

## 3. Non-Goals

- No behavior changes to the Athena client, LLM client, pipeline, or routes. SP02 only relocates values; all function signatures and env-var names remain identical.
- No migration of `AthenaSourceKind` consumers to the typed enum — that is SP04/SP06/SP07's job. SP02 only defines the enum.
- `backend/error_codes.py` (the pipeline error catalog) is not moved or modified — SP01 owns it.
- No Firestore or GCS schema changes.
- No frontend changes.
- `models/base.py` stays at `backend/models/base.py` per global locked decision (a).

---

## 4. Architecture Decisions

### 4a. New `Constants` Structure in `backend/utils/constants.py`

The existing 79-line file is replaced entirely with the design below. The outer `Constants` class is kept so all existing `from utils.constants import Constants` imports continue to work without change.

```python
# backend/utils/constants.py

from enum import Enum
from enum import StrEnum  # Python 3.11+


class _GradingMethodBase:
    def __init__(self, value: str, description: str):
        self.value = value
        self.description = description


class Constants:

    class Schema:
        SUMMARY_SCHEMA_VERSION_1_2: str = "1.2"
        SUMMARY_SCHEMA_VERSION_1_3: str = "1.3"
        SUMMARY_SCHEMA_VERSION_1_4: str = "1.4"
        INPUT_VERSION: str = "1.0"      # migrated from models/input.py:15
        GRADING_VERSION: str = "1.0"    # migrated from models/grading.py:11

    class Uploads:
        ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx", "html", "htm"})
        MAX_FILE_BYTES: int = 10 * 1024 * 1024        # 10 MB per file
        MAX_FILE_COUNT: int = 10
        MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024  # 25 MB combined
        UPLOAD_PREFIX: str = "care_plan-uploads"      # migrated from routes/care_plan.py:46

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
        SINGLE_JOB_INTERNAL_DEADLINE_S: int = 270   # migrated from routes/worker.py:27
        BATCH_ITEM_INTERNAL_DEADLINE_S: int = 870   # migrated from routes/worker.py:28
        JOB_TIMEOUT_SECONDS_SINGLE: int = 300       # migrated from routes/care_plan_jobs.py:129
        JOB_TIMEOUT_SECONDS_BATCH: int = 900        # migrated from routes/batch_jobs.py:78

    class Llm:
        MODEL_DEFAULT: str = "gemini-1.5-pro"    # migrated from utils/llm.py:44 + config.py:12
        MAX_TOKENS: int = 8192
        TEMPERATURE_TEXT: float = 0.3            # migrated from utils/llm.py:60, pipeline.py:75
        TEMPERATURE_JSON: float = 0.2            # migrated from utils/llm.py:117, pipeline.py:84

    class Athena:
        BASE_URL: str = "https://api.preview.platform.athenahealth.com"
        PRACTICE_ID: str = "195900"             # sandbox practice ID
        OAUTH_SCOPE: str = "athena/service/Athenanet.MDP.*"  # migrated from athena_client.py:59
        BATCH_SIZE: int = 2                     # migrated from athena_client.py:20
        BATCH_SLEEP_S: int = 30                 # migrated from athena_client.py:21
        TOKEN_TTL_S: int = 300                  # migrated from AthenaClient.TOKEN_TTL_S:40
        TOKEN_REFRESH_BUFFER_S: int = 20        # migrated from AthenaClient.TOKEN_REFRESH_BUFFER_S:41
        HTTP_TIMEOUT_TOKEN_S: int = 30          # migrated from athena_client.py:61
        HTTP_TIMEOUT_GET_S: int = 60            # migrated from athena_client.py:77
        MAX_RETRIES: int = 3                    # migrated from athena_client.py _get(retries=3)

        class AthenaSourceKind(StrEnum):
            ATHENA_ENCOUNTER = "athena_encounter"
            ATHENA_CLINICAL_DOC = "athena_clinical_doc"

    class Storage:
        GCS_BUCKET_ENV_VAR: str = "GCP_BUCKET_NAME"
        GCS_PRESET_PREFIX: str = "preset-data"              # migrated from gcs_datasets.py:13
        TEMP_BASE: str = "/tmp/juno-datasets"               # migrated from gcs_datasets.py:14
        SIGNED_URL_TTL_MIN: int = 30                        # migrated from saved_outputs.py:224
        GCP_LOCATION_DEFAULT: str = "us-central1"           # migrated from config.py:11 / llm.py:47
        FIRESTORE_DATABASE_ID_DEFAULT: str = "(default)"    # migrated from config.py:13

    class Grading:
        class GRADING_METHODS(Enum):
            SMOG           = _GradingMethodBase("SMOG", "SMOG (McLaughlin 1969) — ...")
            FLESCH_KINCAID = _GradingMethodBase("Flesch-Kincaid", "Flesch-Kincaid Reading Ease + Grade Level (1975) — ...")
            DALE_CHALL     = _GradingMethodBase("Dale-Chall", "Dale-Chall (1948/1995) — ...")
            PEMAT          = _GradingMethodBase("PEMAT", "PEMAT (AHRQ 2013) — ...")
            SAM            = _GradingMethodBase("SAM", "SAM (Doak et al. 1996) — ...")
            CDC_CCI        = _GradingMethodBase("CDC CCI", "CDC Clear Communication Index — ...")

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
        DATASETS_BUCKET: str = "DATASETS_BUCKET_NAME"       # deduplicated (was DATASETS_BUCKET_NAME_ENV_VAR + DATASETS_BUCKET_ENV_VAR)
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
        SERVICE_NAME_DEFAULT: str = "backend-processing"  # migrated from telemetry.py:64,96
        LOG_EXTRA_KEYS: list[str] = [                     # migrated from logging_config.py:32
            "user_id", "function", "care_plan_version", "grading_version", "input_version",
            "operation", "metric", "metric_type", "duration_ms", "success", "outcome",
            "step_name", "status", "http_method", "http_path", "http_status",
            "http_status_code", "total_duration_ms", "saved_id", "input_chars",
            "error", "labels", "duration_ms_observed", "OpOutcome",
            "service", "environment",
        ]
        DIM_OUTCOME: str = "OpOutcome"            # migrated from markers/marker.py:20
        DIM_STATUS_CODE: str = "StatusCode"       # migrated from markers/marker.py:21
        DIM_CORRELATION_ID: str = "CorrelationId" # migrated from markers/marker.py:22
```

**Backward-compatibility shims (in same file, after the class body):**

Several callsites reach top-level attributes (`Constants.RESULT_SENTINEL`, `Constants.MAX_BATCH_RUNS`, etc.) through legacy flat access. Rather than updating every consumer in this SP (some are owned by SP04/SP06/SP07), add shims at the bottom of `constants.py` so existing flat access still works while the namespaced form is canonical:

```python
# Flat shims — kept for callsites not updated until SP03–SP07.
# Remove each shim once its consumer(s) migrate to Constants.<Namespace>.<NAME>.
Constants.RESULT_SENTINEL             = Constants.Pipeline.RESULT_SENTINEL
Constants.MAX_BATCH_RUNS             = Constants.Batch.MAX_BATCH_RUNS
Constants.ALLOWED_EXTENSIONS         = Constants.Uploads.ALLOWED_EXTENSIONS
Constants.MAX_FILE_BYTES             = Constants.Uploads.MAX_FILE_BYTES
Constants.MAX_FILE_COUNT             = Constants.Uploads.MAX_FILE_COUNT
Constants.MAX_AGGREGATE_FILE_BYTES   = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES
Constants.PIPELINE_VERSION_V1_2      = Constants.Pipeline.PIPELINE_VERSION_V1_2
Constants.ALLOWED_VERSIONS           = Constants.Pipeline.ALLOWED_VERSIONS
Constants.STEPS                      = Constants.Pipeline.STEPS
Constants.CARE_PLAN_VERSIONS         = Constants.Pipeline.CARE_PLAN_VERSIONS
Constants.GRADING_METHODS            = Constants.Grading.GRADING_METHODS
Constants.SOURCE                     = Constants.Enums.SOURCE
Constants.IMPORTANCE                 = Constants.Enums.IMPORTANCE
Constants.ATHENA_BASE_URL            = Constants.Athena.BASE_URL
Constants.ATHENA_PRACTICE_ID         = Constants.Athena.PRACTICE_ID
Constants.GCS_BUCKET_ENV_VAR         = Constants.Storage.GCS_BUCKET_ENV_VAR
Constants.DATASETS_BUCKET_NAME_ENV_VAR = Constants.EnvVars.DATASETS_BUCKET  # dedup
Constants.DATASETS_BUCKET_ENV_VAR    = Constants.EnvVars.DATASETS_BUCKET    # dedup
Constants.DATASETS_BUCKET_NAME_DEFAULT = Constants.EnvVars.DATASETS_BUCKET_DEFAULT
Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION
Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION_FALLBACK
Constants.ATHENA_CLIENT_ID_ENV_VAR   = Constants.EnvVars.ATHENA_CLIENT_ID
Constants.ATHENA_CLIENT_SECRET_ENV_VAR = Constants.EnvVars.ATHENA_CLIENT_SECRET
```

These shims mean only the sites listed in §4b–§4h need touching in this SP; all other callsites continue to compile.

---

### 4b. Scattered-Constant Migration Table

Every site that currently defines a constant inline is updated to reference `Constants.<Namespace>.<NAME>`. The full list:

| File | Line(s) | Before | After |
|---|---|---|---|
| `routes/worker.py` | 27 | `SINGLE_JOB_INTERNAL_DEADLINE_S = 270` (module-level literal) | delete; use `Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S` at line 185 |
| `routes/worker.py` | 28 | `BATCH_ITEM_INTERNAL_DEADLINE_S = 870` (module-level literal) | delete; use `Constants.Deadlines.BATCH_ITEM_INTERNAL_DEADLINE_S` at line 185 |
| `routes/care_plan_jobs.py` | 129 | `int(os.environ.get("JOB_TIMEOUT_SECONDS_SINGLE", "300"))` | `Constants.Deadlines.JOB_TIMEOUT_SECONDS_SINGLE` |
| `routes/care_plan_jobs.py` | 68 | `raise ValueError("Stored file exceeds 10 MB limit")` | `raise ValueError(f"Stored file exceeds {Constants.Uploads.MAX_FILE_BYTES // (1024 * 1024)} MB limit")` |
| `routes/batch_jobs.py` | 78 | `int(os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900"))` | `Constants.Deadlines.JOB_TIMEOUT_SECONDS_BATCH` |
| `utils/athena_client.py` | 20 | `BATCH_SIZE = 2` (module-level) | delete literal; use `Constants.Athena.BATCH_SIZE` |
| `utils/athena_client.py` | 21 | `BATCH_SLEEP_S = 30` (module-level) | delete literal; use `Constants.Athena.BATCH_SLEEP_S` |
| `utils/athena_client.py` | 40 | `TOKEN_TTL_S: int = 300` (class attr) | delete class attr; use `Constants.Athena.TOKEN_TTL_S` |
| `utils/athena_client.py` | 41 | `TOKEN_REFRESH_BUFFER_S: int = 20` (class attr) | delete class attr; use `Constants.Athena.TOKEN_REFRESH_BUFFER_S` |
| `utils/athena_client.py` | 59 | `"scope": "athena/service/Athenanet.MDP.*"` | `"scope": Constants.Athena.OAUTH_SCOPE` |
| `utils/athena_client.py` | 61 | `timeout=30` (token POST) | `timeout=Constants.Athena.HTTP_TIMEOUT_TOKEN_S` |
| `utils/athena_client.py` | 70 | `def _get(self, path: str, retries: int = 3)` | `def _get(self, path: str, retries: int = Constants.Athena.MAX_RETRIES)` |
| `utils/athena_client.py` | 77 | `timeout=60` (GET request) | `timeout=Constants.Athena.HTTP_TIMEOUT_GET_S` |
| `utils/llm.py` | 44 | `os.environ.get("VERTEX_AI_MODEL", "gemini-1.5-pro")` | `os.environ.get(Constants.EnvVars.VERTEX_AI_MODEL, Constants.Llm.MODEL_DEFAULT)` |
| `utils/llm.py` | 60 | `def generate_text(self, ..., temperature: float = 0.3, max_tokens: int = 8192)` | `temperature: float = Constants.Llm.TEMPERATURE_TEXT, max_tokens: int = Constants.Llm.MAX_TOKENS` |
| `utils/llm.py` | 117 | `def generate_json(self, ..., temperature: float = 0.2, max_tokens: int = 8192)` | `temperature: float = Constants.Llm.TEMPERATURE_JSON, max_tokens: int = Constants.Llm.MAX_TOKENS` |
| `care_plan/v1_2/pipeline.py` | 75 | `temperature=0.3` in `_generate_text` default | `temperature=Constants.Llm.TEMPERATURE_TEXT` |
| `care_plan/v1_2/pipeline.py` | 84 | `temperature=0.2` in `_generate_json` default | `temperature=Constants.Llm.TEMPERATURE_JSON` |
| `care_plan/v1_2/pipeline.py` | 108 | `max_tokens=65536` in `simplify_language_with_term_plan` call | keep as explicit override (not the default) — no change needed |
| `utils/gcs_datasets.py` | 13 | `GCS_PRESET_PREFIX = "preset-data"` (module-level) | delete literal; use `Constants.Storage.GCS_PRESET_PREFIX` |
| `utils/gcs_datasets.py` | 14 | `TEMP_BASE = Path("/tmp/juno-datasets")` (module-level) | delete literal; use `Path(Constants.Storage.TEMP_BASE)` |
| `routes/care_plan.py` | 46 | `_UPLOAD_PREFIX = "care_plan-uploads"` (module-level) | delete literal; use `Constants.Uploads.UPLOAD_PREFIX` |
| `routes/saved_outputs.py` | 224 | `expiration=timedelta(minutes=30)` | `expiration=timedelta(minutes=Constants.Storage.SIGNED_URL_TTL_MIN)` |
| `models/input.py` | 15 | `INPUT_VERSION = "1.0"` (module-level) | delete literal; use `Constants.Schema.INPUT_VERSION` |
| `models/grading.py` | 11 | `GRADING_VERSION = "1.0"` (module-level) | delete literal; use `Constants.Schema.GRADING_VERSION` |
| `logging_config.py` | 32 | `_EXTRA_KEYS = [...]` (module-level) | delete list; use `Constants.Observability.LOG_EXTRA_KEYS` |
| `telemetry.py` | 64 | `os.getenv("K_SERVICE", "backend-processing")` | `os.getenv(Constants.EnvVars.K_SERVICE, Constants.Observability.SERVICE_NAME_DEFAULT)` |
| `telemetry.py` | 96 | `def get_tracer(name: str = "backend-processing")` | `def get_tracer(name: str = Constants.Observability.SERVICE_NAME_DEFAULT)` |
| `utils/markers/marker.py` | 20 | `DIM_OUTCOME = "OpOutcome"` (module-level) | delete literal; use `Constants.Observability.DIM_OUTCOME` |
| `utils/markers/marker.py` | 21 | `DIM_STATUS_CODE = "StatusCode"` | delete literal; use `Constants.Observability.DIM_STATUS_CODE` |
| `utils/markers/marker.py` | 22 | `DIM_CORRELATION_ID = "CorrelationId"` | delete literal; use `Constants.Observability.DIM_CORRELATION_ID` |

**Note on `utils/juno_logger.py:24`:** `_SERVICE = os.getenv("K_SERVICE", "juno-backend")` uses the default `"juno-backend"`, which differs from `telemetry.py`'s `"backend-processing"`. This discrepancy is intentional (service-identity vs. tracer-name convention). Do not unify them. Leave `juno_logger.py` referencing `Constants.EnvVars.K_SERVICE` for the env-var name but keep `"juno-backend"` as a plain string default (not promoted to a constant) until a future SP aligns service-name conventions.

**Note on `config.py`'s `VERTEX_AI_MODEL` default:** `config.py:12` has `VERTEX_AI_MODEL = os.getenv('VERTEX_AI_MODEL', 'gemini-1.5-pro')` and `utils/llm.py:44` has the same fallback inline. Both collapse into `Constants.Llm.MODEL_DEFAULT`. Since `config.py` is deleted (see §4e), no migration is needed there.

---

### 4c. Alias and Duplicate Removal in `routes/care_plan.py`

**File:** `backend/routes/care_plan.py`

Lines 21–22 and 35 define needless re-aliases of `Constants` values. Delete all three assignments and replace every downstream reference within the file with the namespaced `Constants.*` form.

| Line | Current code | Action |
|---|---|---|
| 21 | `RESULT_SENTINEL = Constants.RESULT_SENTINEL` | Delete. Replace uses at lines 400 with `Constants.Pipeline.RESULT_SENTINEL`. |
| 22 | `MAX_AGGREGATE_FILE_BYTES = Constants.MAX_AGGREGATE_FILE_BYTES` | Delete. Replace uses at line 175 with `Constants.Uploads.MAX_AGGREGATE_FILE_BYTES`. |
| 35 | `CARE_PLAN_VERSION = Constants.CARE_PLAN_VERSIONS.V1_2.value` | Delete. Replace uses at line 366 with `Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value`. |

Also update lines 29–30 (`from models.grading import Grading, build_grading, GRADING_VERSION`) and line 32 (`from models.input import INPUT_VERSION`): the standalone `GRADING_VERSION` and `INPUT_VERSION` symbols will no longer be exported from those modules after migration. Import them as `Constants.Schema.GRADING_VERSION` / `Constants.Schema.INPUT_VERSION` instead, or keep importing from `models.grading` / `models.input` if those modules re-export the constant from `Constants` (either approach is acceptable — choose whichever the implementer finds cleaner).

---

### 4d. Alias Removal in `routes/batch.py`

**File:** `backend/routes/batch.py`

Line 10: `MAX_BATCH_RUNS = Constants.MAX_BATCH_RUNS`

This alias is defined and never referenced again in the file body (the only check for batch size is in `routes/batch_jobs.py`, not here). Delete line 10 entirely.

**Note:** SP06 renames `batch.py` to `batch_utils.py`. This SP does not rename the file — just deletes the dead alias.

---

### 4e. Delete Dead `backend/config.py`

**File:** `backend/config.py`

Zero project files import from `config.py` (confirmed with `grep -rn "from config import\|import config" backend/ --include="*.py"` returning no hits). The file reads env vars at module load time and assigns them to module-level names that nothing consumes. Its default values (`'us-central1'`, `'gemini-1.5-pro'`, `'(default)'`) are already read inline by the modules that actually use them, and after SP02 those defaults live in `Constants`.

**Action:** Delete the file. Add to `backend/tests/integration/test_dead_code_removed.py`:

```python
def test_config_py_deleted():
    import importlib.util
    assert importlib.util.find_spec("config") is None, \
        "backend/config.py must not exist after SP02"
```

---

### 4f. Move Observability Modules into `backend/observability/`

**New package:** `backend/observability/`

Create `backend/observability/__init__.py` (empty or re-exporting the two public symbols for convenience).

**Files moved:**

| From | To |
|---|---|
| `backend/logging_config.py` | `backend/observability/logging_config.py` |
| `backend/telemetry.py` | `backend/observability/telemetry.py` |

The files' internal code is unchanged except for the constant references updated in §4b.

**Import sites that must be updated:**

| File | Current import | New import |
|---|---|---|
| `backend/app.py:14` | `from logging_config import setup_logging` | `from observability.logging_config import setup_logging` |
| `backend/app.py:15` | `from telemetry import init_telemetry` | `from observability.telemetry import init_telemetry` |
| `backend/routes/care_plan.py:38` | `from telemetry import get_tracer` | `from observability.telemetry import get_tracer` |
| `backend/tests/utils/test_telemetry_version.py:14` | `from telemetry import _build_version` | `from observability.telemetry import _build_version` |
| `backend/tests/utils/test_telemetry_version.py:25` | `from telemetry import _build_version` | `from observability.telemetry import _build_version` |
| `backend/tests/utils/test_telemetry_version.py:52` | `from telemetry import _build_version` | `from observability.telemetry import _build_version` |
| `backend/tests/utils/test_telemetry_version.py:63` | `import telemetry` | `from observability import telemetry` |
| `backend/tests/utils/test_logging_config.py:15` | `from logging_config import StructuredJsonFormatter` | `from observability.logging_config import StructuredJsonFormatter` |

**`backend/observability/__init__.py` (convenience re-exports, optional):**

```python
from observability.logging_config import setup_logging
from observability.telemetry import init_telemetry, get_tracer

__all__ = ["setup_logging", "init_telemetry", "get_tracer"]
```

If the convenience re-exports are added, `app.py` can remain as:
```python
from observability import setup_logging, init_telemetry
```
Either pattern is acceptable — pick one and be consistent.

---

### 4g. `AthenaSourceKind` Definition

`Constants.Athena.AthenaSourceKind` is a `StrEnum` defined as part of the `Constants.Athena` inner class (shown in §4a). Its two values match the existing string literals used as `input_source_kind` values:

```python
class AthenaSourceKind(StrEnum):
    ATHENA_ENCOUNTER   = "athena_encounter"
    ATHENA_CLINICAL_DOC = "athena_clinical_doc"
```

**SP02 only defines this enum.** The following consumer sites continue to use the raw string literals until SP04/SP06/SP07 migrate them:

| File | Line | Current literal |
|---|---|---|
| `routes/worker.py` | 40–41 | `"athena_encounter"`, `"athena_clinical_doc"` in `_INPUT_TYPE_MAP` |
| `routes/worker.py` | 219 | `source_kind in ("athena_encounter", "athena_clinical_doc")` |
| `routes/batch_jobs.py` | 44 | `ATHENA_KINDS = {"athena_encounter", "athena_clinical_doc"}` |
| `routes/batch_jobs.py` | 153 | `if source_kind == "athena_encounter":` |
| `utils/athena_client.py` | 122 | `if item["source_kind"] == "athena_encounter":` |

---

### 4h. `GRADING_WEIGHTS` and `RESEARCH_BASIS` Stay in `utils/scoring.py`

The prompt mentions folding scoring weights into `Constants.Grading`. On inspection, `WEIGHTS` (line 203) and `RESEARCH_BASIS` (line 213) in `utils/scoring.py` are used only locally within `score_text()` and are tightly coupled to the scoring algorithm. Promoting them to `Constants` would couple the constants layer to the algorithm layer without benefit. **Decision: leave `WEIGHTS` and `RESEARCH_BASIS` in `utils/scoring.py`.** Only `GRADING_METHODS` (which is genuinely cross-module — used in `models/grading.py:43`) migrates into `Constants.Grading`.

---

## 5. API Change Summary

None. SP02 is a pure internal refactor. No HTTP routes, request shapes, or response shapes change.

---

## 6. Frontend Change Summary

N/A.

---

## 7. Testing

### 7a. Unit tests for `utils/constants.py`

**File:** `backend/tests/utils/test_constants.py` (new file)

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
    from utils.constants import Constants
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
    # The two duplicate names must resolve to the same string.
    assert Constants.EnvVars.DATASETS_BUCKET == "DATASETS_BUCKET_NAME"

def test_flat_shims_still_work():
    # Legacy flat access via shims must not break existing consumers.
    assert Constants.RESULT_SENTINEL == Constants.Pipeline.RESULT_SENTINEL
    assert Constants.MAX_BATCH_RUNS == Constants.Batch.MAX_BATCH_RUNS
    assert Constants.GRADING_METHODS is Constants.Grading.GRADING_METHODS
    assert Constants.ATHENA_BASE_URL == Constants.Athena.BASE_URL
```

### 7b. Integration test — no top-level `.py` files at backend root

**File:** `backend/tests/integration/test_dead_code_removed.py` (update existing file)

Add:

```python
import importlib.util
import pathlib

def test_config_py_deleted():
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

### 7c. Observability tests — no import regressions

The existing test files `test_telemetry_version.py` and `test_logging_config.py` already cover the module behavior. After updating their import lines (§4f), run them as the regression check.

No new test logic is required for the move — the move is a rename, not a behavior change.

### 7d. Smoke check — constants imported in consuming modules

The following existing tests exercise the constants indirectly and must continue to pass without modification:

- `tests/routes/test_worker.py` — uses `Constants.RESULT_SENTINEL` via shim
- `tests/routes/test_batch_jobs.py` — uses `Constants.MAX_BATCH_RUNS` via shim
- `tests/utils/test_athena_client.py` — uses `BATCH_SIZE`, `TOKEN_TTL_S` (now from Constants)
- `tests/utils/test_gcs_datasets.py` — uses `TEMP_BASE` (now from Constants)

Run only these tests (not the full suite) to verify no import regressions.

---

## 8. Manual Intervention Required

None. SP02 is a pure refactor:

- No environment variable names change (only the Python names that hold those strings are reorganized).
- No Firestore documents change.
- No GCS paths change.
- No Cloud Run config changes.

The one action to communicate to the team: **any open branch that imports `from logging_config import ...` or `from telemetry import ...` will get a merge conflict** once this SP lands. The fix is a one-line import update per occurrence.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Exact observability folder name: `backend/observability/` vs. `backend/utils/observability/`. | [RESOLVED: `backend/observability/` — top-level package alongside `utils/`. Rationale: `logging_config` and `telemetry` are app-level infrastructure, not utilities; putting them in `utils/` would blur that boundary.] |
| Q2 | Whether to add a config accessor (e.g. `get_env(Constants.EnvVars.GCS_BUCKET)`) that centralizes `os.environ.get` calls, or leave inline reading of `Constants.EnvVars.*` names. | [OPEN: a config accessor would make test mocking easier and catch missing env vars at startup. However it adds a layer and is not needed for correctness. Defer decision to SP08 or a dedicated config sub-project.] |
| Q3 | Whether `INPUT_VERSION` and `GRADING_VERSION` module-level symbols should remain importable from `models/input.py` and `models/grading.py` as re-exports of `Constants.Schema.*` (to avoid breaking SP03 model consumers), or be removed entirely. | [RESOLVED: keep them as re-exports in the model files — `INPUT_VERSION = Constants.Schema.INPUT_VERSION` — so SP03 model consumers require no import-site changes in this SP.] |
| Q4 | Whether `care_plan/v1_2/pipeline.py`'s explicit `max_tokens=65536` overrides in `simplify_language_with_term_plan` and `clarify_and_action` should be promoted to a named constant. | [DEFERRED: 65536 is a deliberate non-default override for long-form generation steps. It is not duplicated elsewhere, so it does not meet the "used in 2+ places" criterion for promotion. Leave as an inline literal with a comment.] |
| Q5 | Whether backward-compat flat shims should be removed within SP02 itself (updating all 20+ callsites), or left for SP03–SP09 to clean up. | [RESOLVED: leave shims in place for SP02. Each downstream SP removes the shims for the constants it touches. The shims carry a `# TODO(SP03/SP04/etc.): remove after <SP> migrates this consumer` comment to make tracking explicit.] |
