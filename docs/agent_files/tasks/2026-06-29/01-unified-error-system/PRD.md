# PRD: SP01 — Unified Error System

**Sub-project:** SP01  
**Branch context:** `users/tejitpabari/llm-code-check`  
**Date:** 2026-06-29  
**Status:** Planning — no implementation started

---

## 1. Problem

The Juno backend currently has four error-related files that overlap, duplicate symbols, and use incompatible return types. This creates two active runtime risks and significant ongoing maintenance burden.

**The four files today:**

| File | Size | Role | Consumers |
|---|---|---|---|
| `backend/error_codes.py` | ~593 lines | Root enum (27 codes: LLM/Vertex/Pipeline), `ErrorInfo` dataclass, `ERROR_CATALOG` dict | `utils/pipeline_errors.py`, `utils/llm.py:27`, `routes/worker.py:21` |
| `backend/utils/error_codes.py` | ~145 lines | Utils enum (30 codes: Auth/Resource/Input/Batch/Athena/Timeout), thin `_REGISTRY`, `make_error_response()` → `ApiResponse` | `app.py:12`, `utils/firebase.py:16`, `routes/batch_jobs.py:13`, `routes/care_plan.py:36`, `routes/care_plan_jobs.py:21`, `routes/datasets.py:4`, `routes/grading.py:7`, `routes/saved_outputs.py:22`, `routes/worker.py:235` (local import) |
| `backend/models/errors.py` | ~48 lines | Pydantic wire/serialization contract: `StatusEnum`, `ErrorDetail`, `ApiResponse` | Everything that serializes HTTP responses |
| `backend/utils/pipeline_errors.py` | ~220 lines | `JunoError`, Vertex/FinishReason classifiers, a second `make_error_response()` → `(dict,int)`, `build_error_data`, `build_error_data_from_exc`, `handle_exception` | `utils/llm.py:28`, `routes/worker.py:22`, `routes/care_plan.py:37` |

**Specific problems:**

1. **Two `ErrorCode` enums with divergent membership.** The root `error_codes.py` has 27 pipeline/LLM codes; `utils/error_codes.py` has 30 HTTP/Athena/batch codes. Three codes appear in both with identical names but inconsistent metadata: `JOB_TIMEOUT`, `UNSUPPORTED_FILE_TYPE`. Semantic duplicates without identical names: `UNKNOWN_ERROR` (root) ≈ `INTERNAL_ERROR` (utils), `EMPTY_DOCUMENT` (root) ≈ `INPUT_EMPTY` (utils), `PIPELINE_TIMEOUT` (root) ≈ `TIMEOUT` (utils).

2. **Two `make_error_response()` functions with the same name and incompatible return types.** `utils/error_codes.py:89` returns `ApiResponse` (pydantic). `utils/pipeline_errors.py:150` returns `tuple[dict, int]`. Importing from the wrong module causes a silent type mismatch only caught at runtime.

3. **Two metadata stores with incompatible schemas.** The root `ERROR_CATALOG` stores rich `ErrorInfo` (frozen dataclass with `http_status`, `user_hint`, `retryable`). `utils/error_codes.py`'s `_REGISTRY` stores only `(message, details_template)` tuples — no `http_status`, no `user_hint`, no `retryable`. All 30 utils codes are missing retryable/hint/status metadata.

4. **Latent runtime `KeyError` in `routes/worker.py:234-239`.** When an `AthenaAPIError` is caught, the handler does a local `from utils.error_codes import ErrorCode` (getting `ATHENA_API_ERROR` from the utils enum) and then calls `build_error_data(ErrorCode.ATHENA_API_ERROR, ...)` from `utils.pipeline_errors`. `build_error_data` looks up `ERROR_CATALOG` from the **root** `error_codes.py`, which has no `ATHENA_*` entries. This raises `KeyError: <ErrorCode.ATHENA_API_ERROR: 'ATHENA_API_ERROR'>` the first time any job attempts an Athena fetch and gets an API error — the job crashes silently, never written to Firestore.

5. **Three scattered exception classes not inheriting `JunoError`.** `AthenaAPIError` (`utils/athena_client.py:24`), `MissingJobConfigError` (`utils/cloud_tasks.py:9`), `GCSFetchRequired` (`utils/preset_data.py:16`) all inherit plain `Exception`. They cannot be caught by the unified `_classify_exc` path and are silently downgraded to `UNKNOWN_ERROR` by `build_error_data_from_exc`.

6. **Backend root directory contains two non-`app.py` modules.** Both `error_codes.py` and `utils/pipeline_errors.py` must move; the root should contain only `app.py`.

7. **Ad-hoc inline error dicts and bare `ValueError`/`RuntimeError`/`FileNotFoundError` used as pipeline control flow**, then caught further up the call stack and mapped to error responses. These produce inconsistent Firestore error payloads and make error tracing across log entries difficult.

---

## 2. Goals

1. Collapse the four files into exactly **two** new files plus one preserved wire-shape file:
   - `backend/errors/codes.py` — unified `ErrorCode` enum (all 50+ deduplicated codes), extended `ErrorInfo` dataclass (adds `details_template`), unified `ERROR_CATALOG` covering every code
   - `backend/errors/exceptions.py` — `JunoError`, all classifiers, the single `make_error_response()` returning `ApiResponse`, `build_error_data`, `build_error_data_from_exc`, `handle_exception`, `_SafeDict`/`_safe_format`
   - `backend/errors/__init__.py` — re-exports for a single clean import surface
   - `backend/models/errors.py` — **kept unchanged** (the pydantic wire shape is not a duplicate)

2. Fix the latent `KeyError` runtime bug in `routes/worker.py:234-239`.

3. Re-parent `AthenaAPIError`, `MissingJobConfigError`, and `GCSFetchRequired` under `JunoError` with default `ErrorCode` assignments, so they are automatically classified by `build_error_data_from_exc`.

4. Replace the highest-value ad-hoc `raise ValueError`/`RuntimeError` sites in `care_plan/v1_2/pipeline.py` with `raise JunoError(ErrorCode.X)`. Enumerate the strategy for the full sweep; full remediation is cross-referenced to SP08.

5. Delete `backend/error_codes.py`, `backend/utils/error_codes.py`, and `backend/utils/pipeline_errors.py`. The backend root contains only `app.py`.

6. Migrate all ~12 import sites and 4 test files to `errors.*`.

7. Provide a complete old→new symbol table so every import change is mechanical for a junior dev.

---

## 3. Non-Goals

- No changes to `backend/models/errors.py` (wire shape, pydantic). It is the third file and is the serialization contract, not a duplicate. [RESOLVED — see §9]
- No changes to any HTTP field names visible to the frontend (`requestId`, `details`, `code`, `status`).
- No frontend changes. The error-shape contract that SP10 depends on is described in §6 but no frontend files are modified here.
- No changes to logging or metrics infrastructure (`utils/markers.py`, OpenTelemetry, `utils/juno_logger.py`).
- No changes to how `app.py` registers global Flask error handlers — those already call `make_error_response()` correctly after SP04-era work.
- No changes to test fixtures or conftest infrastructure.
- The full ad-hoc `raise ValueError` sweep across all routes is deferred to SP08; this SP fixes only the highest-value pipeline sites.

---

## 4. Architecture Decisions

### 4a. New Package: `backend/errors/`

Three new files. No other location. Neither file lives in the backend root (only `app.py` is permitted there).

```
backend/errors/
    __init__.py        # re-exports; this is the only import surface callers need
    codes.py           # ErrorInfo dataclass + ErrorCode enum + ERROR_CATALOG
    exceptions.py      # JunoError + classifiers + response builders
```

**Import direction (no cycles):**

```
errors/codes.py
    ← errors/exceptions.py  (imports ErrorCode, ErrorInfo, ERROR_CATALOG)
    ← errors/__init__.py    (re-exports both)
    ← models/errors.py      (unchanged; imported by exceptions.py for ApiResponse)
    ← utils/cloud_tasks.py  (imports JunoError to subclass it)
    ← utils/preset_data.py  (imports JunoError to subclass it)
    ← utils/athena_client.py / models/external_api/athena.py (imports JunoError to subclass it)
```

`errors/` never imports from `utils/`, `routes/`, or `models/external_api/` — import direction is one-way.

---

### 4b. `backend/errors/codes.py` — Extended `ErrorInfo` + Unified `ErrorCode`

**`ErrorInfo` — add `details_template` field:**

```python
@dataclass(frozen=True)
class ErrorInfo:
    code: str
    http_status: int
    message: str
    user_hint: str
    retryable: bool
    details_template: str = ""   # NEW — the format string from utils _REGISTRY, e.g. "{field}: {reason}"
```

This folds the `_REGISTRY` tuples from `utils/error_codes.py` into one data source. Callers that previously used `_REGISTRY[code][1]` for template expansion now use `ERROR_CATALOG[code].details_template`.

**`ErrorCode` — union of both enums, deduplicated:**

The unified enum contains every code from both current enums. Semantic duplicates are handled as follows:

| Root code | Utils code | Resolution |
|---|---|---|
| `UNKNOWN_ERROR` | `INTERNAL_ERROR` | Keep **both** with a comment; `UNKNOWN_ERROR` is used by `_classify_exc` fallback (pipeline); `INTERNAL_ERROR` is used by HTTP routes and Flask error handlers. They carry slightly different user messages and HTTP semantics (500/500 same but message differs). |
| `EMPTY_DOCUMENT` | `INPUT_EMPTY` | Keep **both**; `EMPTY_DOCUMENT` is the pipeline-level code (after file parse); `INPUT_EMPTY` is the route-level code (text field is blank). Different trigger points. |
| `PIPELINE_TIMEOUT` | `TIMEOUT` | Keep **both**; `PIPELINE_TIMEOUT` is the pipeline wall-clock limit; `TIMEOUT` is the generic HTTP timeout. |
| `JOB_TIMEOUT` | `JOB_TIMEOUT` | **Merge** — identical semantics. Keep `JOB_TIMEOUT` with the richer `ErrorInfo` from the root catalog (http_status=504, retryable=False). Use `details_template = "Job exceeded the worker time limit at stage {stage}"`. |
| `UNSUPPORTED_FILE_TYPE` | `UNSUPPORTED_FILE_TYPE` | **Merge** — identical semantics. Keep single entry with http_status=415, template `"File must be PDF, TXT, DOCX, or HTML; got {ext}"`. |

**Full merged enum (abbreviated, showing added/merged/retained codes):**

```python
class ErrorCode(StrEnum):
    # LLM Generation (from root error_codes.py — all retained)
    LLM_MAX_TOKENS = "LLM_MAX_TOKENS"
    LLM_SAFETY_BLOCKED = "LLM_SAFETY_BLOCKED"
    LLM_RECITATION_BLOCKED = "LLM_RECITATION_BLOCKED"
    LLM_FINISH_OTHER = "LLM_FINISH_OTHER"
    LLM_BLOCKLIST = "LLM_BLOCKLIST"
    LLM_PROHIBITED_CONTENT = "LLM_PROHIBITED_CONTENT"
    LLM_SPII = "LLM_SPII"
    LLM_MALFORMED_FUNCTION_CALL = "LLM_MALFORMED_FUNCTION_CALL"
    LLM_NO_CANDIDATES = "LLM_NO_CANDIDATES"
    LLM_INVALID_JSON = "LLM_INVALID_JSON"

    # Vertex AI API (from root error_codes.py — all retained)
    VERTEX_QUOTA_EXCEEDED = "VERTEX_QUOTA_EXCEEDED"
    VERTEX_DEADLINE_EXCEEDED = "VERTEX_DEADLINE_EXCEEDED"
    VERTEX_INVALID_ARGUMENT = "VERTEX_INVALID_ARGUMENT"
    VERTEX_PERMISSION_DENIED = "VERTEX_PERMISSION_DENIED"
    VERTEX_NOT_FOUND = "VERTEX_NOT_FOUND"
    VERTEX_SERVICE_UNAVAILABLE = "VERTEX_SERVICE_UNAVAILABLE"
    VERTEX_INTERNAL_ERROR = "VERTEX_INTERNAL_ERROR"
    VERTEX_UNAUTHENTICATED = "VERTEX_UNAUTHENTICATED"
    VERTEX_ABORTED = "VERTEX_ABORTED"

    # Pipeline / Processing (merged from both)
    FILE_PARSE_FAILED = "FILE_PARSE_FAILED"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"   # merged (was in both)
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"                  # kept (pipeline: after parse)
    INPUT_EMPTY = "INPUT_EMPTY"                        # kept (route: blank text field)
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"              # kept (pipeline wall-clock)
    JOB_TIMEOUT = "JOB_TIMEOUT"                       # merged (was in both)
    PIPELINE_VALIDATION_FAILED = "PIPELINE_VALIDATION_FAILED"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    PIPELINE_INIT_ERROR = "PIPELINE_INIT_ERROR"
    SIMPLIFICATION_FAILED = "SIMPLIFICATION_FAILED"
    STRUCTURING_FAILED = "STRUCTURING_FAILED"

    # Auth (from utils)
    UNAUTHORIZED = "UNAUTHORIZED"
    MISSING_AUTH_HEADER = "MISSING_AUTH_HEADER"
    MALFORMED_AUTH_HEADER = "MALFORMED_AUTH_HEADER"

    # Resource (from utils)
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_FORBIDDEN = "RESOURCE_FORBIDDEN"

    # Input (from utils)
    INPUT_VALIDATION_ERROR = "INPUT_VALIDATION_ERROR"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"

    # Timeout (from utils — TIMEOUT kept separate from PIPELINE_TIMEOUT)
    TIMEOUT = "TIMEOUT"                                # kept (generic HTTP timeout)

    # Batch (from utils)
    BATCH_TOO_LARGE = "BATCH_TOO_LARGE"
    BATCH_INVALID_SELECTION = "BATCH_INVALID_SELECTION"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    DATASET_DOWNLOAD_ERROR = "DATASET_DOWNLOAD_ERROR"

    # Grading / Saving (from utils)
    NO_SOURCE_TEXT = "NO_SOURCE_TEXT"
    SAVE_FAILED = "SAVE_FAILED"
    PDF_URL_UNAVAILABLE = "PDF_URL_UNAVAILABLE"

    # System / Catch-all (both retained — see resolution above)
    UNKNOWN_ERROR = "UNKNOWN_ERROR"                    # pipeline _classify_exc fallback
    INTERNAL_ERROR = "INTERNAL_ERROR"                  # HTTP routes + Flask handlers
    ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"

    # Athena Health (from utils — already exist, no change)
    ATHENA_AUTH_FAILED = "ATHENA_AUTH_FAILED"
    ATHENA_API_ERROR = "ATHENA_API_ERROR"
    ATHENA_RATE_LIMIT_ERROR = "ATHENA_RATE_LIMIT_ERROR"
    ATHENA_PATIENT_NOT_FOUND = "ATHENA_PATIENT_NOT_FOUND"
    ATHENA_TIMEOUT = "ATHENA_TIMEOUT"
```

**`ERROR_CATALOG` — unified, every code has full `ErrorInfo`:**

Every code that previously existed only in `_REGISTRY` (with no `http_status`/`user_hint`/`retryable`) must now have a full `ErrorInfo` entry. The http_status values to use for codes migrating from `_REGISTRY`:

| Code | http_status | retryable | Notes |
|---|---|---|---|
| `UNAUTHORIZED` | 401 | False | |
| `MISSING_AUTH_HEADER` | 401 | False | |
| `MALFORMED_AUTH_HEADER` | 400 | False | |
| `RESOURCE_NOT_FOUND` | 404 | False | |
| `RESOURCE_FORBIDDEN` | 403 | False | |
| `INPUT_VALIDATION_ERROR` | 422 | False | |
| `INPUT_EMPTY` | 422 | False | |
| `FILE_TOO_LARGE` | 413 | False | |
| `UNKNOWN_VERSION` | 400 | False | |
| `PIPELINE_ERROR` | 500 | True | |
| `PIPELINE_INIT_ERROR` | 500 | False | |
| `SIMPLIFICATION_FAILED` | 500 | True | |
| `STRUCTURING_FAILED` | 500 | True | |
| `TIMEOUT` | 504 | True | |
| `BATCH_TOO_LARGE` | 400 | False | |
| `BATCH_INVALID_SELECTION` | 400 | False | |
| `DATASET_NOT_FOUND` | 404 | False | |
| `DATASET_DOWNLOAD_ERROR` | 503 | True | |
| `NO_SOURCE_TEXT` | 422 | False | |
| `SAVE_FAILED` | 500 | True | |
| `PDF_URL_UNAVAILABLE` | 404 | False | |
| `INTERNAL_ERROR` | 500 | False | |
| `ENDPOINT_NOT_FOUND` | 404 | False | |
| `ATHENA_AUTH_FAILED` | 503 | True | |
| `ATHENA_API_ERROR` | 502 | True | |
| `ATHENA_RATE_LIMIT_ERROR` | 429 | True | |
| `ATHENA_PATIENT_NOT_FOUND` | 404 | False | |
| `ATHENA_TIMEOUT` | 504 | True | |

Completeness assertion from root `error_codes.py` is retained in `errors/codes.py`:

```python
_missing = [ec for ec in ErrorCode if ec not in ERROR_CATALOG]
if _missing:
    raise AssertionError(f"errors/codes.py: missing ERROR_CATALOG entries for: {[ec.value for ec in _missing]}")
```

---

### 4c. `backend/errors/exceptions.py` — All Logic, Single `make_error_response`

This file merges the logic from `utils/pipeline_errors.py` and the helper functions from `utils/error_codes.py`. It imports from `errors/codes.py` and `models/errors.py`.

**`JunoError` — unchanged signature, import path changes:**

```python
from errors.codes import ERROR_CATALOG, ErrorCode, ErrorInfo
from models.errors import ApiResponse, ErrorDetail, StatusEnum

class JunoError(Exception):
    def __init__(self, error_code: ErrorCode, detail: str = "", original: Exception | None = None) -> None:
        self.error_code = error_code
        self.info: ErrorInfo = ERROR_CATALOG[error_code]
        self.detail = detail
        self.original = original
        super().__init__(self.info.message)
```

**`make_error_response` — single function, returns `ApiResponse`:**

The utils version (`utils/error_codes.py:89`) becomes the canonical implementation. The pipeline version (`utils/pipeline_errors.py:150`) is deleted. Callers that used the pipeline version's `(dict, int)` return must be updated (see §4g migration table).

```python
def make_error_response(
    code: ErrorCode,
    path: str | None = None,
    details_vars: dict | None = None,
    requestId: str | None = None,
    user_hint: str | None = None,
    retryable: bool = False,
) -> ApiResponse:
    """Build a structured ApiResponse for an error. Returns ApiResponse (not a dict tuple)."""
    catalog_entry = ERROR_CATALOG[code]
    details = _safe_format(catalog_entry.details_template, details_vars or {})

    if requestId is None:
        try:
            from flask import g
            requestId = getattr(g, "session_id", None)
        except RuntimeError:
            requestId = None

    timestamp = datetime.now(timezone.utc).isoformat()
    error_detail = ErrorDetail(
        code=code.value,
        message=catalog_entry.message,
        details=details or None,
        timestamp=timestamp,
        path=path,
        user_hint=user_hint if user_hint is not None else catalog_entry.user_hint,
        retryable=retryable if retryable else catalog_entry.retryable,
    )
    logger.error("error_response", extra={"error_code": code.value, "path": path, "request_id": requestId})
    return ApiResponse(status=StatusEnum.error, error=error_detail, requestId=requestId)
```

Note: the new signature auto-fills `user_hint` and `retryable` from `ERROR_CATALOG` when not explicitly passed. This removes the need for callers to pass hint/retryable manually for catalog-registered codes; callers can still override them.

**`build_error_data` — Firestore dict builder, unchanged shape:**

```python
def build_error_data(error_code: ErrorCode, detail: str = "") -> dict:
    """Build the error_data dict written to Firestore on job failure."""
    info = ERROR_CATALOG[error_code]
    return {
        "code": info.code,
        "message": info.message,
        "user_hint": info.user_hint,
        "retryable": info.retryable,
        "details": detail or None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

**All other functions retained from `utils/pipeline_errors.py` unchanged:**
- `build_error_data_from_exc(exc)` — classify any exception → Firestore dict
- `handle_exception(exc)` — classify any exception → `(dict, int)` tuple (legacy path, retained for SP08 migration)
- `_classify_exc(exc)` — internal classifier (JunoError → GoogleAPICallError → RuntimeError legacy → UNKNOWN_ERROR)
- `classify_vertex_exception(exc)` — maps `google.api_core.exceptions` → `ErrorCode`
- `classify_finish_reason(finish_reason_str)` — maps FinishReason strings → `ErrorCode`
- `_FINISH_REASON_MAP` — static mapping dict
- `_SafeDict`, `_safe_format` — safe string formatting

**`backend/errors/__init__.py` — flat re-export surface:**

```python
from errors.codes import ERROR_CATALOG, ErrorCode, ErrorInfo
from errors.exceptions import (
    JunoError,
    make_error_response,
    build_error_data,
    build_error_data_from_exc,
    handle_exception,
    classify_vertex_exception,
    classify_finish_reason,
)

__all__ = [
    "ERROR_CATALOG", "ErrorCode", "ErrorInfo",
    "JunoError",
    "make_error_response",
    "build_error_data",
    "build_error_data_from_exc",
    "handle_exception",
    "classify_vertex_exception",
    "classify_finish_reason",
]
```

Callers can either `from errors import ErrorCode, make_error_response` or `from errors.codes import ErrorCode` — both work.

---

### 4d. Re-parenting `AthenaAPIError`, `MissingJobConfigError`, `GCSFetchRequired`

All three inherit plain `Exception` today. They must inherit `JunoError` so `_classify_exc` catches them correctly.

**`utils/cloud_tasks.py:9` — `MissingJobConfigError`:**

```python
# Before:
class MissingJobConfigError(RuntimeError):
    ...

# After:
from errors import JunoError, ErrorCode

class MissingJobConfigError(JunoError):
    """Raised when a required Cloud Tasks env var is unset/empty."""
    def __init__(self, var_name: str) -> None:
        super().__init__(
            ErrorCode.INTERNAL_ERROR,
            detail=f"Required environment variable '{var_name}' is not set.",
        )
```

**`utils/preset_data.py:16` — `GCSFetchRequired`:**

```python
# Before:
class GCSFetchRequired(Exception):
    def __init__(self, group: str, input_id: str, filename: str): ...

# After:
from errors import JunoError, ErrorCode

class GCSFetchRequired(JunoError):
    """Raised when the requested file requires a live GCS fetch."""
    def __init__(self, group: str, input_id: str, filename: str) -> None:
        self.group = group
        self.input_id = input_id
        self.filename = filename
        super().__init__(
            ErrorCode.DATASET_DOWNLOAD_ERROR,
            detail=f"GCS fetch required for {group}/{input_id}/{filename}",
        )
```

**`AthenaAPIError` — final location is `models/external_api/` per SP03/SP04; it must inherit `JunoError` from THIS SP's package:**

SP03/SP04 will move `AthenaAPIError` to `models/external_api/athena.py`. This SP only adds the `JunoError` inheritance at the current location `utils/athena_client.py:24`:

```python
# Before (utils/athena_client.py:24):
class AthenaAPIError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Athena API error {status_code}: {body[:200]}")

# After (utils/athena_client.py:24, pending move to models/external_api/ in SP03/SP04):
from errors import JunoError, ErrorCode

class AthenaAPIError(JunoError):
    """Raised when an Athena API call returns a non-200 status."""
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        # Map status code to appropriate error code
        if status_code == 401:
            code = ErrorCode.ATHENA_AUTH_FAILED
        elif status_code == 429:
            code = ErrorCode.ATHENA_RATE_LIMIT_ERROR
        elif status_code == 404:
            code = ErrorCode.ATHENA_PATIENT_NOT_FOUND
        else:
            code = ErrorCode.ATHENA_API_ERROR
        super().__init__(code, detail=f"status={status_code} body={body[:200]}")
```

This also **fixes the latent runtime bug**: `routes/worker.py:234-239` can be simplified to:

```python
# After SP01: the local import and dual-enum lookup are eliminated.
# AthenaAPIError is now a JunoError; build_error_data_from_exc handles it automatically.
except AthenaAPIError as exc:
    fail_job(job_id, build_error_data_from_exc(exc))
    logger.error("worker: Athena API error for job %s: %s", job_id, exc)
    return "", 200
```

Drop the `from error_codes import ErrorCode as PipelineErrorCode` alias on line 21 and the local `from utils.error_codes import ErrorCode` import on line 235. Use a single `from errors import ErrorCode, build_error_data, build_error_data_from_exc`.

---

### 4e. Ad-hoc Exception Strategy and Highest-Value Sites

**Pattern to eliminate:**

```python
# Problematic pattern (used as control flow):
raise ValueError("File must be PDF, TXT, DOCX, or HTML")
# ... then caught somewhere above:
except ValueError as e:
    return make_error_response(ErrorCode.UNSUPPORTED_FILE_TYPE, ...).to_dict(), 415
```

This pattern forces callers to know which `ValueError` maps to which `ErrorCode` and risks the wrong handler catching unrelated `ValueError`s.

**Replacement pattern:**

```python
raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"got extension: {ext}")
# ... caller catches JunoError and uses its error_code directly — no mapping needed
```

**Highest-value sites to fix in this SP (full sweep in SP08):**

| File | Line | Current | Replace With |
|---|---|---|---|
| `care_plan/v1_2/pipeline.py` | 130 | `raise ValueError(f"Expected dict from structure step, got {type(raw)}")` | `raise JunoError(ErrorCode.LLM_INVALID_JSON, detail=f"expected dict, got {type(raw)}")` |
| `care_plan/v1_2/pipeline.py` | 135 | `raise ValueError(f"LLM structure output failed validation: {e}")` | `raise JunoError(ErrorCode.PIPELINE_VALIDATION_FAILED, detail=str(e), original=e)` |
| `routes/care_plan.py` | 141 | `raise ValueError(f"Unsupported file extension: {ext}")` | `raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")` |
| `routes/care_plan.py` | 224 | `raise FileNotFoundError(f"No file found for doc_id={doc_id}")` | `raise JunoError(ErrorCode.RESOURCE_NOT_FOUND, detail=f"doc_id={doc_id}")` |

**Strategy for remaining sites (to be catalogued in SP08):**

- Any `raise ValueError` / `raise RuntimeError` that is caught within 3 call frames and mapped to a specific error response → replace with `raise JunoError(ErrorCode.X, ...)`.
- Any `raise ValueError` / `raise RuntimeError` that represents a genuine programming error (misconfiguration, contract violation) may stay as-is or become `JunoError(ErrorCode.INTERNAL_ERROR)`.
- `raise RuntimeError("GCP_BUCKET_NAME is not configured")` → `raise JunoError(ErrorCode.INTERNAL_ERROR, detail="GCP_BUCKET_NAME not configured")`.
- The `routes/batch.py` `ValueError` chain in `_resolve_requested_runs` (lines 51-81) → each becomes `raise JunoError(ErrorCode.BATCH_INVALID_SELECTION, detail=...)` or `ErrorCode.DATASET_NOT_FOUND` as appropriate.

**Ad-hoc inline `{"error": ...}` dicts:**

`routes/batch.py:20-25` and `routes/care_plan.py:50-55` use bare `jsonify({"error": "..."})` for deprecated SSE endpoints returning 410. These are intentionally minimal tombstone responses. They may stay as-is since they are permanent 410 gone responses and SP02 ruled no changes to the 410 stubs.

---

### 4f. Files to Delete

| File | Action | When Safe |
|---|---|---|
| `backend/error_codes.py` | Delete — content moves to `errors/codes.py` | After all 3 import sites migrated |
| `backend/utils/error_codes.py` | Delete — content merges into `errors/codes.py` + `errors/exceptions.py` | After all 9 import sites migrated |
| `backend/utils/pipeline_errors.py` | Delete — content moves to `errors/exceptions.py` | After all 3 import sites migrated |

---

### 4g. Complete Import Migration Table

**Old → New symbol/path mapping:**

| Old import | Old symbol | New import | New symbol |
|---|---|---|---|
| `from error_codes import ErrorCode` | `ErrorCode` (27 pipeline codes) | `from errors import ErrorCode` | unified `ErrorCode` |
| `from error_codes import ErrorCode as PipelineErrorCode` | `PipelineErrorCode` | `from errors import ErrorCode` | drop alias |
| `from error_codes import ERROR_CATALOG, ErrorCode, ErrorInfo` | all three | `from errors import ERROR_CATALOG, ErrorCode, ErrorInfo` | same names |
| `from utils.error_codes import ErrorCode` | `ErrorCode` (30 utils codes) | `from errors import ErrorCode` | unified `ErrorCode` |
| `from utils.error_codes import make_error_response, ErrorCode` | both | `from errors import make_error_response, ErrorCode` | same names |
| `from utils.error_codes import _REGISTRY` | `_REGISTRY` | not exported — use `ERROR_CATALOG[code].details_template` | — |
| `from utils.pipeline_errors import JunoError, classify_finish_reason, classify_vertex_exception` | three functions | `from errors import JunoError, classify_finish_reason, classify_vertex_exception` | same names |
| `from utils.pipeline_errors import build_error_data, build_error_data_from_exc` | both | `from errors import build_error_data, build_error_data_from_exc` | same names |
| `from utils.pipeline_errors import build_error_data_from_exc` | one function | `from errors import build_error_data_from_exc` | same name |

**Per-file migration:**

| File | Lines | Old import | Change |
|---|---|---|---|
| `backend/app.py` | 12 | `from utils.error_codes import make_error_response, ErrorCode` | → `from errors import make_error_response, ErrorCode` |
| `backend/utils/firebase.py` | 16 | `from utils.error_codes import make_error_response, ErrorCode` | → `from errors import make_error_response, ErrorCode` |
| `backend/utils/llm.py` | 27-28 | `from error_codes import ErrorCode` + `from utils.pipeline_errors import JunoError, classify_finish_reason, classify_vertex_exception` | → `from errors import ErrorCode, JunoError, classify_finish_reason, classify_vertex_exception` |
| `backend/routes/care_plan.py` | 36-37 | `from utils.error_codes import ...` + `from utils.pipeline_errors import ...` | → `from errors import make_error_response, ErrorCode, build_error_data_from_exc` |
| `backend/routes/worker.py` | 21-22, 235 | `from error_codes import ErrorCode as PipelineErrorCode` + `from utils.pipeline_errors import ...` + local `from utils.error_codes import ErrorCode` | → single `from errors import ErrorCode, build_error_data, build_error_data_from_exc`; drop alias |
| `backend/routes/batch_jobs.py` | 13 | `from utils.error_codes import make_error_response, ErrorCode` | → `from errors import make_error_response, ErrorCode` |
| `backend/routes/care_plan_jobs.py` | 21 | `from utils.error_codes import make_error_response, ErrorCode` | → `from errors import make_error_response, ErrorCode` |
| `backend/routes/datasets.py` | 4 | `from utils.error_codes import make_error_response, ErrorCode` | → `from errors import make_error_response, ErrorCode` |
| `backend/routes/grading.py` | 7 | `from utils.error_codes import make_error_response, ErrorCode` | → `from errors import make_error_response, ErrorCode` |
| `backend/routes/saved_outputs.py` | 22 | `from utils.error_codes import make_error_response, ErrorCode` | → `from errors import make_error_response, ErrorCode` |
| `backend/utils/cloud_tasks.py` | 9 | `class MissingJobConfigError(RuntimeError)` | add `from errors import JunoError, ErrorCode`; re-parent |
| `backend/utils/preset_data.py` | 16 | `class GCSFetchRequired(Exception)` | add `from errors import JunoError, ErrorCode`; re-parent |
| `backend/utils/athena_client.py` | 24 | `class AthenaAPIError(Exception)` | add `from errors import JunoError, ErrorCode`; re-parent |

---

## 5. API Change Summary

No HTTP response field names change. The changes are additive and fully backward-compatible.

| Change | Impact |
|---|---|
| `user_hint` in error responses may now be populated from `ERROR_CATALOG` automatically (was sometimes `null` when not passed explicitly). | Additive — clients that already render `user_hint` get better content; clients that ignore it are unaffected. |
| `retryable` in error responses may now be `true` for codes like `ATHENA_RATE_LIMIT_ERROR` automatically. | Additive. |
| Athena job failures now write a well-formed Firestore error dict (previously would KeyError and write nothing). | Bug fix — no field name change. |

**Wire shape contract for SP10 (Frontend Legacy-Shim Retirement):**

The error shape that SP10 and the frontend depend on is `models/errors.py`'s `ApiResponse`/`ErrorDetail`, which is unchanged. The Firestore `error_data` dict shape is unchanged:

```json
{
  "code": "<ErrorCode.value>",
  "message": "<developer-facing string>",
  "user_hint": "<user-facing string | null>",
  "retryable": "<bool>",
  "details": "<extra context | null>",
  "timestamp": "<ISO-8601 UTC>"
}
```

SP10 may depend on this shape being stable across all job failure paths, including Athena failures (previously broken). SP01 makes it stable.

---

## 6. Frontend Change Summary

No frontend files are modified in SP01.

**Error-shape contract that SP10 depends on (document only):**

SP10 targets `frontend/src/types/errors.ts` and the `FirestoreJobError` TypeScript interface. The Firestore `error_data` shape guaranteed by SP01 is documented in §5 above. SP10 should type `jobDoc.error_data` as:

```typescript
export interface FirestoreJobError {
  code: string;
  message: string;
  user_hint: string | null;
  retryable: boolean;
  details: string | null;
  timestamp: string;  // ISO-8601 UTC
}
```

All Athena job error paths now write this shape (previously the Athena path crashed before writing). SP10 can treat the shape as complete and stable after SP01 lands.

---

## 7. Testing

### Tests to delete (their modules are deleted)

| Test file | Reason |
|---|---|
| `backend/tests/utils/test_error_codes.py` | Tests `utils/error_codes.py` internal `_REGISTRY` directly — module deleted |
| `backend/tests/utils/test_pipeline_errors.py` | Tests `utils/pipeline_errors.py` directly — module deleted |

### New test file: `backend/tests/errors/test_codes.py`

```python
# Tests for errors/codes.py

def test_all_error_codes_in_catalog():
    from errors.codes import ErrorCode, ERROR_CATALOG
    missing = [code for code in ErrorCode if code not in ERROR_CATALOG]
    assert missing == [], f"ErrorCodes missing from ERROR_CATALOG: {missing}"

def test_catalog_entries_have_all_fields():
    from errors.codes import ERROR_CATALOG
    for code, info in ERROR_CATALOG.items():
        assert isinstance(info.http_status, int), f"{code}: http_status not int"
        assert isinstance(info.user_hint, str) and info.user_hint, f"{code}: user_hint empty"
        assert isinstance(info.retryable, bool), f"{code}: retryable not bool"
        assert isinstance(info.details_template, str), f"{code}: details_template not str"

def test_merged_codes_not_duplicated():
    from errors.codes import ErrorCode
    values = [e.value for e in ErrorCode]
    assert len(values) == len(set(values)), "Duplicate ErrorCode values detected"

def test_athena_codes_have_correct_http_status():
    from errors.codes import ErrorCode, ERROR_CATALOG
    assert ERROR_CATALOG[ErrorCode.ATHENA_AUTH_FAILED].http_status == 503
    assert ERROR_CATALOG[ErrorCode.ATHENA_RATE_LIMIT_ERROR].http_status == 429
    assert ERROR_CATALOG[ErrorCode.ATHENA_PATIENT_NOT_FOUND].http_status == 404
```

### New test file: `backend/tests/errors/test_exceptions.py`

```python
# Tests for errors/exceptions.py

def test_make_error_response_returns_api_response():
    from errors import make_error_response, ErrorCode
    from models.errors import ApiResponse, StatusEnum
    resp = make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path="/test",
                               details_vars={"collection": "c", "doc_id": "d"})
    assert isinstance(resp, ApiResponse)
    assert resp.status == StatusEnum.error
    assert resp.error.code == "RESOURCE_NOT_FOUND"

def test_make_error_response_autofills_user_hint_from_catalog():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.VERTEX_QUOTA_EXCEEDED)
    assert resp.error.user_hint is not None
    assert len(resp.error.user_hint) > 0

def test_make_error_response_override_user_hint():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.PIPELINE_ERROR, user_hint="Custom hint")
    assert resp.error.user_hint == "Custom hint"

def test_make_error_response_autofills_retryable_from_catalog():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.VERTEX_QUOTA_EXCEEDED)
    assert resp.error.retryable is True

def test_make_error_response_no_flask_context_does_not_raise():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.TIMEOUT)
    assert resp.requestId is None

def test_build_error_data_includes_timestamp():
    from errors import build_error_data, ErrorCode
    from datetime import datetime
    result = build_error_data(ErrorCode.JOB_TIMEOUT)
    assert "timestamp" in result
    datetime.fromisoformat(result["timestamp"])

def test_build_error_data_uses_details_key():
    from errors import build_error_data, ErrorCode
    result = build_error_data(ErrorCode.JOB_TIMEOUT, detail="some detail")
    assert "details" in result
    assert "detail" not in result

def test_build_error_data_from_exc_juno_error():
    from errors import build_error_data_from_exc, JunoError, ErrorCode
    try:
        raise JunoError(ErrorCode.LLM_MAX_TOKENS, "too big")
    except JunoError as exc:
        result = build_error_data_from_exc(exc)
    assert result["code"] == "LLM_MAX_TOKENS"
    assert result.get("user_hint") is not None

def test_build_error_data_athena_api_error_no_key_error():
    """Regression test for the worker.py KeyError bug (SP01)."""
    from errors import build_error_data, ErrorCode
    # Must not raise KeyError
    result = build_error_data(ErrorCode.ATHENA_API_ERROR, detail="status=500 path=/test")
    assert result["code"] == "ATHENA_API_ERROR"
    assert result["retryable"] is True

def test_athena_api_error_is_juno_error():
    from utils.athena_client import AthenaAPIError
    from errors import JunoError, ErrorCode
    exc = AthenaAPIError(429, "rate limit")
    assert isinstance(exc, JunoError)
    assert exc.error_code == ErrorCode.ATHENA_RATE_LIMIT_ERROR

def test_missing_job_config_error_is_juno_error():
    from utils.cloud_tasks import MissingJobConfigError
    from errors import JunoError
    exc = MissingJobConfigError("CLOUD_TASKS_QUEUE")
    assert isinstance(exc, JunoError)

def test_gcs_fetch_required_is_juno_error():
    from utils.preset_data import GCSFetchRequired
    from errors import JunoError, ErrorCode
    exc = GCSFetchRequired("group", "id", "file.txt")
    assert isinstance(exc, JunoError)
    assert exc.error_code == ErrorCode.DATASET_DOWNLOAD_ERROR
```

### Existing test file to update: `backend/tests/utils/test_llm.py`

Lines 20-21 import `from error_codes import ErrorCode` and `from utils.pipeline_errors import JunoError`. Update to `from errors import ErrorCode, JunoError`. No logic changes.

### Existing test file to update: `backend/tests/models/test_errors.py`

No import changes needed — it only imports from `models.errors` which is unchanged.

### Manual integration test

1. Start the backend. Submit an Athena job that will fail with a 429 from the Athena mock. Confirm the Firestore `error_data` dict is written (not missing), with `code == "ATHENA_RATE_LIMIT_ERROR"` and `retryable == true`.
2. Grep the running process for `KeyError` — should be zero after SP01.
3. Run `python -c "from errors import ErrorCode, make_error_response"` with no app context — confirm no import error and no assertion failure from the completeness check.

---

## 8. Manual Intervention Required From You

None. SP01 is entirely code changes:
- No GCS bucket configuration changes.
- No Cloud Run / Cloud Tasks env var changes.
- No Firestore schema migration (schemaless; new fields appear naturally on new job writes).
- No database backfill needed.

The only thing to watch: if any in-flight jobs are queued during deploy and fail via the Athena path, they will have previously produced no Firestore error record. After SP01 they will write a proper `error_data` dict. Old jobs already in terminal state are unaffected.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | `models/errors.py` is a third error-related file — should it be merged into `errors/`? | [RESOLVED: kept as-is. It is the pydantic wire/serialization contract, not an error-logic duplicate. It lives in `models/` because it defines `ApiResponse` and `ErrorDetail` — types used across the entire model layer, not just the error system. Moving it would break `models/__init__.py` re-exports and create a circular import with `errors/exceptions.py`. The "three files" concern in the prompt refers to logic duplication; `models/errors.py` has zero logic.] |
| Q2 | Merged enum approach vs. keeping two enums in different namespaces | [RESOLVED: single unified `ErrorCode` enum in `errors/codes.py`. The benefits (single import, single catalog, fixes runtime KeyError) outweigh the risk. Any code that used `PipelineErrorCode` or the local utils `ErrorCode` gets one alias update.] |
| Q3 | `make_error_response` split — which return type wins? | [RESOLVED: `ApiResponse` return type wins (from `utils/error_codes.py`). The `(dict, int)` variant from `utils/pipeline_errors.py` is deleted. The small number of callers that used it (none confirmed in routes; the `handle_exception` wrapper remains for SP08) are migrated. `build_error_data` / `build_error_data_from_exc` / `handle_exception` remain for Firestore payloads and the legacy catch-all path.] |
| Q4 | Should `UNKNOWN_ERROR` and `INTERNAL_ERROR` be merged into one code? | [OPEN: they serve different semantic roles today — `UNKNOWN_ERROR` is the `_classify_exc` fallback for unclassified pipeline exceptions (carries `retryable=False`, no user-facing path awareness); `INTERNAL_ERROR` is used by HTTP route handlers and Flask global error handlers (carries a user_hint aimed at the HTTP context). They have the same `http_status=500` but different `user_hint` strings. Merging them risks homogenizing log search (harder to distinguish pipeline crashes from route-level crashes). Recommendation: keep both, add comments.] |
| Q5 | Should `EMPTY_DOCUMENT` and `INPUT_EMPTY` be merged? | [OPEN: `EMPTY_DOCUMENT` fires after file parse produces no text (pipeline stage 1). `INPUT_EMPTY` fires when the HTTP route receives an empty text field before pipeline dispatch. Same user-visible symptom but different trigger contexts. Merging simplifies the enum but means log search cannot distinguish whether emptiness was detected pre-pipeline or post-parse. Recommendation: keep both with explanatory comments.] |
| Q6 | Package name: `errors/` vs. `error/` vs. `core/errors/`? | [OPEN: `errors/` is shortest and most self-explanatory. `error/` (singular) is non-idiomatic Python. `core/errors/` adds a `core/` wrapper that would need its own `__init__.py`. Recommendation: `backend/errors/` — straightforward, no extra nesting.] |
| Q7 | Should `handle_exception()` (returns `(dict, int)` tuple) be kept or removed? | [RESOLVED: kept in `errors/exceptions.py`. It is a convenience wrapper used in tests and is needed for SP08's sweep of bare-except catch-alls in older route handlers that currently call `jsonify(handle_exception(exc))`. Removing it now forces SP08 to do two things at once.] |
| Q8 | `AthenaAPIError` status-code-to-ErrorCode mapping — should it be in `AthenaAPIError.__init__` or in `_classify_exc`? | [OPEN: putting it in `AthenaAPIError.__init__` (as shown in §4d) means the exception self-identifies its ErrorCode at raise time, which is precise and avoids a second status-code parse. Putting it in `_classify_exc` centralizes all classification. The `__init__` approach is preferred because `AthenaAPIError` has the `status_code` attribute available at construction time; by the time `_classify_exc` sees it, the status code is already embedded in the exception message string and would need re-parsing.] |
