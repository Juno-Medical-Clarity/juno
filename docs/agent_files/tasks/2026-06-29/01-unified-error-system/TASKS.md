# SP01 Unified Error System — TASKS

## Prerequisites

Collapse four overlapping error files into a clean `backend/errors/` package, fix a latent
`KeyError` runtime bug in the Athena error handler, re-parent three exception classes, replace
the highest-value ad-hoc `raise` sites, and migrate all import sites.

SP01 is the first sub-project and depends on no other SP.

---

## Tasks

### Task 01.1: Audit user-facing vs internal error separation in `models/errors.py`

- **Goal:** Confirm (or add) a clear distinction between user-facing and internal error fields
  in the wire model. The user-facing `status_code` and `error_code` at the top level must differ
  from internal error detail — internal code + more context should be nested under `details`.
  Read the code only; do not query production data.
- **Files:** `backend/models/errors.py`
- **Steps:**
  1. Open `backend/models/errors.py` and inspect `ErrorDetail`.
  2. Confirm `ErrorDetail` has top-level user-facing fields: `code` (string, the public
     `ErrorCode` value), `message` (user-facing), `user_hint` (user-facing), `retryable`.
  3. Confirm `details` (Optional[str]) carries additional internal context.
  4. The current model does NOT have a separate nested internal error code field — `details` is a
     plain string. This is acceptable: the user-facing `code` is the public-facing error
     identifier and `details` is the internal string context.
  5. Add a docstring to `ErrorDetail` that explicitly documents this contract:
     - `code`, `message`, `user_hint`, `retryable` — user-facing; safe to display in client UI.
     - `details` — internal context string (stack info, upstream error text); may be omitted from
       client-rendered UI; suitable for logs and support diagnostics.
  6. No structural changes to fields are needed — the existing model already implements the
     required separation via the `user_hint` / `code` vs `details` boundary.

  > Note: The user asked to confirm a "nested internal error code" exists. The current model
  > uses `details: Optional[str]` for internal context rather than a nested object with its own
  > `code` field. Adding a nested object would break the wire contract (SP10 dependency). The
  > documented boundary between `user_hint`/`code` (public) and `details` (internal) satisfies
  > the design requirement without a breaking schema change.

- **Acceptance:**
  - `ErrorDetail` docstring explicitly labels each field as user-facing or internal.
  - `pytest backend/tests/models/test_errors.py` passes with no changes.
  - No new fields added; wire shape unchanged.
- **Commit:** `docs(errors): document user-facing vs internal field boundary in ErrorDetail`

---

### Task 01.2: Create `backend/errors/codes.py` — unified `ErrorInfo`, `ErrorCode`, `ERROR_CATALOG`

- **Goal:** Build the single source of truth for all error metadata. Merges content from
  `backend/error_codes.py` (27 pipeline/LLM codes) and `backend/utils/error_codes.py` (30
  HTTP/Athena/batch codes) into one file. Fixes the missing `ATHENA_*` entries that cause the
  runtime `KeyError`.
- **Files:** `backend/errors/__init__.py` (create, empty for now), `backend/errors/codes.py` (create)
- **Steps:**
  1. Create directory `backend/errors/` and an empty `backend/errors/__init__.py`.
  2. Create `backend/errors/codes.py` with:

     a. `ErrorInfo` dataclass — copy from `backend/error_codes.py` and add one new field:
        ```python
        @dataclass(frozen=True)
        class ErrorInfo:
            code: str
            http_status: int
            message: str
            user_hint: str
            retryable: bool
            details_template: str = ""   # NEW: format string for structured detail expansion
        ```

     b. `ErrorCode(StrEnum)` — unified enum containing ALL codes from both existing enums.
        Deduplication rules (apply exactly):
        - `JOB_TIMEOUT`: appears in both — keep ONE entry (merged).
        - `UNSUPPORTED_FILE_TYPE`: appears in both — keep ONE entry (merged).
        - `UNKNOWN_ERROR` and `INTERNAL_ERROR`: keep BOTH; add inline comments:
          `# UNKNOWN_ERROR: _classify_exc fallback for unclassified pipeline exceptions`
          `# INTERNAL_ERROR: HTTP routes and Flask global error handlers`
        - `EMPTY_DOCUMENT` and `INPUT_EMPTY`: keep BOTH; add inline comments:
          `# EMPTY_DOCUMENT: after file parse produces no text (pipeline stage 1)`
          `# INPUT_EMPTY: HTTP route received empty text field before pipeline dispatch`
        - `PIPELINE_TIMEOUT` and `TIMEOUT`: keep BOTH; add inline comments:
          `# PIPELINE_TIMEOUT: pipeline wall-clock limit exceeded`
          `# TIMEOUT: generic HTTP timeout (route level)`
        - All remaining codes from both enums: include all, no deduplication needed.
        - Add `PIPELINE_ERROR = "PIPELINE_ERROR"` and `PIPELINE_INIT_ERROR = "PIPELINE_INIT_ERROR"`
          and `SIMPLIFICATION_FAILED`, `STRUCTURING_FAILED` from `utils/error_codes.py`.

     c. `ERROR_CATALOG: dict[ErrorCode, ErrorInfo]` — one entry per code. Rules:
        - All 27 codes from `backend/error_codes.py`: copy their existing `ErrorInfo` verbatim,
          adding `details_template=""` (empty default — these codes had no template).
        - All 30 codes from `backend/utils/error_codes.py` `_REGISTRY`: add full `ErrorInfo`
          entries using the http_status and retryable values from the table in PRD §4b. Copy
          the `_REGISTRY` tuple's first element as `message` and second element as
          `details_template`. Use the `_REGISTRY` message as `user_hint` too, unless a more
          user-appropriate hint is obvious; in that case write a brief user-facing one.
        - For merged codes (`JOB_TIMEOUT`, `UNSUPPORTED_FILE_TYPE`): use the richer existing
          `ErrorInfo` from `backend/error_codes.py` and add `details_template` from `_REGISTRY`.
        - `UNSUPPORTED_FILE_TYPE`: use `details_template = "File must be PDF, TXT, DOCX, or HTML; got {ext}"`.
        - `JOB_TIMEOUT`: use `details_template = "Job exceeded the worker time limit at stage {stage}"`.

     d. Add the completeness assertion at module bottom:
        ```python
        _missing = [ec for ec in ErrorCode if ec not in ERROR_CATALOG]
        if _missing:
            raise AssertionError(
                f"errors/codes.py: missing ERROR_CATALOG entries for: {[ec.value for ec in _missing]}"
            )
        ```

  3. `backend/errors/codes.py` must have zero imports from `utils/`, `routes/`, `models/`, or
     `app.py` — only stdlib (`dataclasses`, `enum`).

- **Acceptance:**
  - `python -c "from errors.codes import ErrorCode, ERROR_CATALOG, ErrorInfo"` runs without error
    (run from `backend/` directory).
  - No `AssertionError` raised at import time (completeness check passes).
  - `len(ErrorCode)` equals the total count of unique codes from both original enums after
    deduplication (expect ~53 codes).
  - `retryable` field present and typed `bool` on every `ErrorInfo` in `ERROR_CATALOG`.
  - `details_template` field present and typed `str` on every `ErrorInfo`.
  - `ERROR_CATALOG[ErrorCode.ATHENA_API_ERROR].http_status == 502` (was missing before — this
    confirms the KeyError fix is in place).
- **Commit:** `feat(errors): create errors/codes.py with unified ErrorCode enum and ERROR_CATALOG`

---

### Task 01.3: Create `backend/errors/exceptions.py` — single `make_error_response`, all classifiers

- **Goal:** Merge all logic from `backend/utils/pipeline_errors.py` and the helper functions
  from `backend/utils/error_codes.py` into a single file. Establish `make_error_response`
  returning `ApiResponse` as the one canonical response builder.
- **Files:** `backend/errors/exceptions.py` (create)
- **Steps:**
  1. Create `backend/errors/exceptions.py`. Import at the top:
     ```python
     from __future__ import annotations
     import logging
     from datetime import datetime, timezone
     from errors.codes import ERROR_CATALOG, ErrorCode, ErrorInfo
     from models.errors import ApiResponse, ErrorDetail, StatusEnum
     ```

  2. Copy `_SafeDict` and `_safe_format` verbatim from `backend/utils/error_codes.py`.

  3. Copy `JunoError` class verbatim from `backend/utils/pipeline_errors.py` — only update
     the import line (it already imports from `error_codes`; change to `errors.codes`).

  4. Copy `_FINISH_REASON_MAP`, `classify_finish_reason`, `classify_vertex_exception` verbatim
     from `backend/utils/pipeline_errors.py` — update the internal `ErrorCode` reference to
     the unified one.

  5. Copy `_classify_exc` verbatim from `backend/utils/pipeline_errors.py`.
     Remove the "Legacy RuntimeError classification" block (lines that check `isinstance(exc,
     RuntimeError)` for `"MAX_TOKENS"` or `"SAFETY"` in the message) — this is dead legacy code
     (Q3 decision: remove all legacy). After removal, `_classify_exc` falls through directly to
     `UNKNOWN_ERROR` for unclassified exceptions.

  6. Add the canonical `make_error_response` — use the signature from `utils/error_codes.py`
     (returns `ApiResponse`). Extend it to auto-fill `user_hint` and `retryable` from
     `ERROR_CATALOG` when not explicitly passed:
     ```python
     def make_error_response(
         code: ErrorCode,
         path: str | None = None,
         details_vars: dict | None = None,
         requestId: str | None = None,
         user_hint: str | None = None,
         retryable: bool | None = None,
     ) -> ApiResponse:
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
             retryable=retryable if retryable is not None else catalog_entry.retryable,
         )
         logger.error("error_response", extra={"error_code": code.value, "path": path, "request_id": requestId})
         return ApiResponse(status=StatusEnum.error, error=error_detail, requestId=requestId)
     ```
     > Note: `retryable` parameter type changed from `bool = False` to `bool | None = None` so
     > callers that pass nothing get the catalog default rather than always `False`. Callers that
     > explicitly pass `retryable=True` or `retryable=False` get their value honored.

  7. Copy `build_error_data` verbatim from `backend/utils/pipeline_errors.py` — update import.

  8. Copy `build_error_data_from_exc` verbatim from `backend/utils/pipeline_errors.py`.

  9. Copy `handle_exception` verbatim from `backend/utils/pipeline_errors.py`. Update its
     internal call to use the new `make_error_response` — since `handle_exception` returns
     `tuple[dict, int]` it must call:
     ```python
     def handle_exception(exc: Exception) -> tuple[dict, int]:
         error_code, detail = _classify_exc(exc)
         info = ERROR_CATALOG[error_code]
         resp = make_error_response(error_code, details_vars={"detail": detail})
         return resp.model_dump(), info.http_status
     ```

  10. Do NOT import from `utils/pipeline_errors.py` or `utils/error_codes.py` or
      `backend/error_codes.py` — all content is being replicated here from the source files,
      not re-imported.

- **Acceptance:**
  - `python -c "from errors.exceptions import make_error_response, JunoError, build_error_data, build_error_data_from_exc, handle_exception, classify_vertex_exception, classify_finish_reason"` succeeds (run from `backend/`).
  - `make_error_response(ErrorCode.RESOURCE_NOT_FOUND)` returns an `ApiResponse` instance.
  - `make_error_response(ErrorCode.VERTEX_QUOTA_EXCEEDED).error.retryable is True` (auto-filled from catalog).
  - No reference to `utils.error_codes`, `utils.pipeline_errors`, or `error_codes` remains in the new file.
- **Commit:** `feat(errors): create errors/exceptions.py with unified make_error_response and classifiers`

---

### Task 01.4: Populate `backend/errors/__init__.py` with flat re-export surface

- **Goal:** Create the single import surface so all callers can use `from errors import X`
  without knowing which sub-module holds X.
- **Files:** `backend/errors/__init__.py`
- **Steps:**
  1. Replace the empty `__init__.py` created in Task 01.2 with:
     ```python
     """errors — unified error package for the Juno backend.

     Import from here; do not import directly from errors.codes or errors.exceptions
     unless you need an internal symbol not re-exported here.
     """
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
- **Acceptance:**
  - `python -c "from errors import ErrorCode, make_error_response, JunoError, build_error_data, build_error_data_from_exc, classify_vertex_exception, classify_finish_reason, ERROR_CATALOG, ErrorInfo"` succeeds from `backend/`.
  - `from errors.codes import ErrorCode` also works (direct sub-module import still valid).
- **Commit:** `feat(errors): populate errors/__init__.py re-export surface`

---

### Task 01.5: Add `retryable` as a property on the error model and write new test suite

- **Goal:** (a) Confirm `retryable` is already a field on `ErrorDetail` (it is — Task 01.1
  confirmed this). Now create the `backend/tests/errors/` test package with tests for both
  `errors/codes.py` and `errors/exceptions.py`. (b) Add explicit test coverage for `retryable`
  auto-fill behavior from catalog.
- **Files:**
  - `backend/tests/errors/__init__.py` (create, empty)
  - `backend/tests/errors/test_codes.py` (create)
  - `backend/tests/errors/test_exceptions.py` (create)
- **Steps:**
  1. Create `backend/tests/errors/__init__.py` (empty).
  2. Create `backend/tests/errors/test_codes.py` with the following tests:
     ```python
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
         assert ERROR_CATALOG[ErrorCode.ATHENA_API_ERROR].http_status == 502

     def test_retryable_field_is_bool_for_all_codes():
         from errors.codes import ERROR_CATALOG
         for code, info in ERROR_CATALOG.items():
             assert isinstance(info.retryable, bool), f"{code}.retryable is not bool"

     def test_job_timeout_and_unsupported_file_type_not_duplicated():
         from errors.codes import ErrorCode
         values = [e.value for e in ErrorCode]
         assert values.count("JOB_TIMEOUT") == 1
         assert values.count("UNSUPPORTED_FILE_TYPE") == 1
     ```

  3. Create `backend/tests/errors/test_exceptions.py` with tests covering:
     - `make_error_response` returns `ApiResponse` with correct `StatusEnum.error`.
     - `make_error_response` auto-fills `user_hint` from catalog when not passed.
     - `make_error_response` auto-fills `retryable` from catalog (`VERTEX_QUOTA_EXCEEDED` → `True`).
     - `make_error_response` explicit `user_hint` override is honored.
     - `make_error_response` explicit `retryable=False` override overrides catalog `True`.
     - `make_error_response` with no Flask context does not raise; `requestId` is `None`.
     - `build_error_data` returns dict with `timestamp`, `code`, `message`, `user_hint`,
       `retryable`, `details` keys.
     - `build_error_data` with `detail` arg puts value in `details` key, not `detail` key.
     - `build_error_data_from_exc` with `JunoError(ErrorCode.LLM_MAX_TOKENS, "too big")` returns
       dict with `code == "LLM_MAX_TOKENS"`.
     - Regression: `build_error_data(ErrorCode.ATHENA_API_ERROR, detail="status=500")` does not
       raise `KeyError` and returns dict with `code == "ATHENA_API_ERROR"` and `retryable is True`.
     - `handle_exception` with an unclassified `Exception("boom")` returns `tuple[dict, int]`
       with HTTP status 500.

- **Acceptance:**
  - `pytest backend/tests/errors/ -v` passes (all tests green).
  - No imports from `utils.error_codes`, `utils.pipeline_errors`, or `error_codes` in new tests.
- **Commit:** `test(errors): add test suite for errors/codes.py and errors/exceptions.py`

---

### Task 01.6: Re-parent `AthenaAPIError` under `JunoError` with status-code mapping

- **Goal:** Fix the latent `KeyError` runtime bug. `AthenaAPIError` currently inherits `Exception`
  and is not caught by `_classify_exc`. Re-parent it under `JunoError` with status-code-to-ErrorCode
  mapping in `__init__` (Q8 decision: in `AthenaAPIError.__init__` is good).
- **Files:** `backend/utils/athena_client.py`
- **Steps:**
  1. Add imports at the top of `backend/utils/athena_client.py`:
     ```python
     from errors import JunoError, ErrorCode
     ```
  2. Replace the `AthenaAPIError` class definition (currently lines 24-30):
     ```python
     class AthenaAPIError(JunoError):
         """Raised when an Athena API call returns a non-200 status."""

         def __init__(self, status_code: int, body: str) -> None:
             self.status_code = status_code
             self.body = body
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
  3. Do NOT change any raise sites within `athena_client.py` — they already raise `AthenaAPIError`
     with `(status_code, body)` and that call signature is preserved.
- **Acceptance:**
  - `from utils.athena_client import AthenaAPIError; from errors import JunoError; assert issubclass(AthenaAPIError, JunoError)` passes.
  - `AthenaAPIError(429, "rate limit").error_code == ErrorCode.ATHENA_RATE_LIMIT_ERROR`.
  - `AthenaAPIError(401, "unauth").error_code == ErrorCode.ATHENA_AUTH_FAILED`.
  - `AthenaAPIError(500, "server error").error_code == ErrorCode.ATHENA_API_ERROR`.
  - `pytest backend/tests/utils/test_athena_client.py` passes.
- **Commit:** `fix(athena): re-parent AthenaAPIError under JunoError with status-code mapping`

---

### Task 01.7: Re-parent `MissingJobConfigError` and `GCSFetchRequired` under `JunoError`

- **Goal:** Ensure all three project-specific exception classes are caught by `_classify_exc`
  automatically; eliminates silent `UNKNOWN_ERROR` downgrades.
- **Files:** `backend/utils/cloud_tasks.py`, `backend/utils/preset_data.py`
- **Steps:**
  1. In `backend/utils/cloud_tasks.py`:
     - Add at top: `from errors import JunoError, ErrorCode`
     - Replace `class MissingJobConfigError(RuntimeError):` with:
       ```python
       class MissingJobConfigError(JunoError):
           """Raised when a required Cloud Tasks env var is unset/empty."""

           def __init__(self, var_name: str) -> None:
               super().__init__(
                   ErrorCode.INTERNAL_ERROR,
                   detail=f"Required environment variable '{var_name}' is not set.",
               )
       ```
     - The `require_env` function calls `MissingJobConfigError(...)` with a string message today.
       After the change it takes `var_name` — check `require_env` body and update the call to
       pass only the variable name string (not the full message), e.g. `raise MissingJobConfigError(name)`.
       The detail message is now built inside `__init__`.

  2. In `backend/utils/preset_data.py`:
     - Add at top: `from errors import JunoError, ErrorCode`
     - Replace `class GCSFetchRequired(Exception):` with:
       ```python
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
     - Keep all existing raise sites (`raise GCSFetchRequired(group=..., input_id=..., filename=...)`)
       unchanged — the signature is preserved.

- **Acceptance:**
  - `from utils.cloud_tasks import MissingJobConfigError; from errors import JunoError; assert issubclass(MissingJobConfigError, JunoError)` passes.
  - `from utils.preset_data import GCSFetchRequired; assert issubclass(GCSFetchRequired, JunoError)` passes.
  - `GCSFetchRequired("g", "id", "f.txt").error_code == ErrorCode.DATASET_DOWNLOAD_ERROR`.
  - `pytest backend/tests/utils/test_cloud_tasks.py backend/tests/utils/test_preset_data.py` passes.
- **Commit:** `fix(errors): re-parent MissingJobConfigError and GCSFetchRequired under JunoError`

---

### Task 01.8: Fix `routes/worker.py` Athena handler and migrate its imports

- **Goal:** Remove the local `from utils.error_codes import ErrorCode` (line 235) and the
  `PipelineErrorCode` alias (line 21), replacing them with a single unified import. The Athena
  catch block becomes one line since `AthenaAPIError` is now a `JunoError`.
- **Files:** `backend/routes/worker.py`
- **Steps:**
  1. Remove line 21: `from error_codes import ErrorCode as PipelineErrorCode`
  2. Remove line 22: `from utils.pipeline_errors import build_error_data, build_error_data_from_exc`
  3. Add a single replacement import:
     ```python
     from errors import ErrorCode, build_error_data, build_error_data_from_exc
     ```
  4. Find line 235 (the local `from utils.error_codes import ErrorCode` inside the
     `except AthenaAPIError` block) and delete it.
  5. Replace the entire `except AthenaAPIError as exc:` block (lines 234-243) with:
     ```python
     except AthenaAPIError as exc:
         fail_job(job_id, build_error_data_from_exc(exc))
         logger.error("worker: Athena API error for job %s: %s", job_id, exc)
         return "", 200
     ```
     (The manual `ErrorCode.ATHENA_API_ERROR` lookup is gone — `build_error_data_from_exc` now
     handles it via `JunoError.error_code`.)
  6. Find all remaining references to `PipelineErrorCode` in `worker.py` (e.g., line 250:
     `fail_job(job_id, _build_error_data(PipelineErrorCode.EMPTY_DOCUMENT))`). Replace
     `PipelineErrorCode` with `ErrorCode`.
  7. Verify no remaining imports from `error_codes` (root module) or `utils.error_codes` or
     `utils.pipeline_errors` remain in `worker.py`.
- **Acceptance:**
  - `grep -n "error_codes\|pipeline_errors\|PipelineErrorCode" backend/routes/worker.py` returns zero results.
  - `grep -n "from errors import" backend/routes/worker.py` shows the unified import.
  - `pytest backend/tests/routes/test_worker.py` passes.
- **Commit:** `fix(worker): remove dual ErrorCode imports and fix Athena error handler`

---

### Task 01.9: Migrate remaining route and utility import sites

- **Goal:** Update all remaining callers of `utils.error_codes` and `utils.pipeline_errors`
  to use `from errors import ...`.
- **Files:**
  - `backend/app.py`
  - `backend/utils/firebase.py`
  - `backend/utils/llm.py`
  - `backend/routes/care_plan.py`
  - `backend/routes/batch_jobs.py`
  - `backend/routes/care_plan_jobs.py`
  - `backend/routes/datasets.py`
  - `backend/routes/grading.py`
  - `backend/routes/saved_outputs.py`
- **Steps:**

  For each file, make ONLY the import line changes specified below. Do not change any logic.

  1. `backend/app.py` line 12:
     Change `from utils.error_codes import make_error_response, ErrorCode`
     → `from errors import make_error_response, ErrorCode`

  2. `backend/utils/firebase.py` line 16:
     Change `from utils.error_codes import make_error_response, ErrorCode`
     → `from errors import make_error_response, ErrorCode`

  3. `backend/utils/llm.py` lines 27-28:
     Change `from error_codes import ErrorCode` → (remove)
     Change `from utils.pipeline_errors import JunoError, classify_finish_reason, classify_vertex_exception` → (remove)
     Add: `from errors import ErrorCode, JunoError, classify_finish_reason, classify_vertex_exception`

  4. `backend/routes/care_plan.py` lines 36-37:
     Change `from utils.error_codes import make_error_response, ErrorCode` → (remove)
     Change `from utils.pipeline_errors import build_error_data_from_exc` → (remove)
     Add: `from errors import make_error_response, ErrorCode, build_error_data_from_exc`

  5. `backend/routes/batch_jobs.py` line 13:
     Change `from utils.error_codes import make_error_response, ErrorCode`
     → `from errors import make_error_response, ErrorCode`

  6. `backend/routes/care_plan_jobs.py` line 21:
     Change `from utils.error_codes import make_error_response, ErrorCode`
     → `from errors import make_error_response, ErrorCode`

  7. `backend/routes/datasets.py` line 4:
     Change `from utils.error_codes import make_error_response, ErrorCode`
     → `from errors import make_error_response, ErrorCode`

  8. `backend/routes/grading.py` line 7:
     Change `from utils.error_codes import make_error_response, ErrorCode`
     → `from errors import make_error_response, ErrorCode`

  9. `backend/routes/saved_outputs.py` line 22:
     Change `from utils.error_codes import make_error_response, ErrorCode`
     → `from errors import make_error_response, ErrorCode`

  After all changes:
  - Run `grep -rn "from utils.error_codes\|from utils.pipeline_errors\|from error_codes" backend/ --include="*.py" | grep -v ".venv"` and confirm zero results (excluding the three source files to be deleted in the next task).

- **Acceptance:**
  - `grep -rn "from utils.error_codes\|from utils.pipeline_errors\|from error_codes" backend/ --include="*.py" | grep -v ".venv" | grep -v "backend/error_codes.py" | grep -v "backend/utils/error_codes.py" | grep -v "backend/utils/pipeline_errors.py"` returns zero lines.
  - `pytest backend/tests/routes/ backend/tests/utils/test_firebase.py backend/tests/utils/test_llm.py -v` passes.
- **Commit:** `refactor(imports): migrate all callers to from errors import ...`

---

### Task 01.10: Replace highest-value ad-hoc `raise` sites in pipeline and routes

- **Goal:** Replace four specific `raise ValueError` / `raise FileNotFoundError` / `raise RuntimeError`
  sites with typed `raise JunoError(ErrorCode.X, ...)`. These are the highest-value sites
  (PRD §4e); the full sweep is deferred to SP08.
- **Files:**
  - `backend/care_plan/v1_2/pipeline.py`
  - `backend/routes/care_plan.py`
- **Steps:**
  1. In `backend/care_plan/v1_2/pipeline.py`:
     - Ensure `JunoError` and `ErrorCode` are imported: add `from errors import JunoError, ErrorCode`
       (remove any existing imports from `error_codes` or `utils.pipeline_errors`).
     - Line 130: Replace `raise ValueError(f"Expected dict from structure step, got {type(raw)}")`
       with `raise JunoError(ErrorCode.LLM_INVALID_JSON, detail=f"expected dict, got {type(raw)}")`
     - Line 135: Replace `raise ValueError(f"LLM structure output failed validation: {e}") from e`
       with `raise JunoError(ErrorCode.PIPELINE_VALIDATION_FAILED, detail=str(e), original=e)`

  2. In `backend/routes/care_plan.py`:
     - `from errors import make_error_response, ErrorCode, build_error_data_from_exc, JunoError`
       (JunoError is needed for the raise sites).
     - Line 141: Replace `raise ValueError(f"Unsupported file extension: {ext}")`
       with `raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")`
     - Line 224: Replace `raise FileNotFoundError(f"No file found for doc_id={doc_id}")`
       with `raise JunoError(ErrorCode.RESOURCE_NOT_FOUND, detail=f"doc_id={doc_id}")`

  > Note: Lines 156-176 in `routes/care_plan.py` contain additional `raise ValueError` sites for
  > file validation (missing filename, file count, type, size). These are deferred to SP08.
  > Lines 62 and 215 (`raise RuntimeError("GCP_BUCKET_NAME is not configured")`) are also SP08.

- **Acceptance:**
  - `grep -n "raise ValueError\|raise FileNotFoundError" backend/care_plan/v1_2/pipeline.py` returns zero results.
  - Lines 141 and 224 in `backend/routes/care_plan.py` no longer contain `raise ValueError` or `raise FileNotFoundError`.
  - `pytest backend/tests/care_plan/ backend/tests/routes/ -v` passes.
- **Commit:** `fix(pipeline): replace highest-value ad-hoc raise sites with JunoError`

---

### Task 01.11: Delete old test files and update existing test imports

- **Goal:** Remove the two test files that test the now-deleted modules. Update existing test
  files that import from old paths.
- **Files:**
  - `backend/tests/utils/test_error_codes.py` (DELETE)
  - `backend/tests/utils/test_pipeline_errors.py` (DELETE)
  - `backend/tests/utils/test_llm.py` (edit imports only)
- **Steps:**
  1. Delete `backend/tests/utils/test_error_codes.py`.
  2. Delete `backend/tests/utils/test_pipeline_errors.py`.
  3. In `backend/tests/utils/test_llm.py` lines 20-21:
     - Remove `from error_codes import ErrorCode`
     - Remove `from utils.pipeline_errors import JunoError`
     - Add `from errors import ErrorCode, JunoError`
  4. Run `grep -rn "from error_codes\|from utils.error_codes\|from utils.pipeline_errors" backend/tests/ --include="*.py"` and confirm zero results.

- **Acceptance:**
  - `backend/tests/utils/test_error_codes.py` does not exist.
  - `backend/tests/utils/test_pipeline_errors.py` does not exist.
  - `pytest backend/tests/utils/test_llm.py` passes.
  - `pytest backend/tests/` (full suite) passes.
- **Commit:** `test(errors): delete obsolete test files and update test imports`

---

### Task 01.12: Delete `backend/error_codes.py`, `backend/utils/error_codes.py`, `backend/utils/pipeline_errors.py`

- **Goal:** Remove the three source files. After this task the backend root contains only
  `app.py` as a non-package Python module; no import site references the deleted paths.
- **Files:**
  - `backend/error_codes.py` (DELETE)
  - `backend/utils/error_codes.py` (DELETE)
  - `backend/utils/pipeline_errors.py` (DELETE)
- **Steps:**
  1. Before deleting, run:
     ```
     grep -rn "from error_codes\|from utils.error_codes\|from utils.pipeline_errors\|import error_codes\|import pipeline_errors" backend/ --include="*.py" | grep -v ".venv"
     ```
     Confirm zero results (all import sites were migrated in Tasks 01.8 and 01.9).
  2. Delete `backend/error_codes.py`.
  3. Delete `backend/utils/error_codes.py`.
  4. Delete `backend/utils/pipeline_errors.py`.
  5. Run the full test suite to confirm nothing is broken.
  6. Run `grep -rn "error_codes\|pipeline_errors" backend/ --include="*.py" | grep -v ".venv" | grep -v "backend/errors/"` and confirm zero results.

- **Acceptance:**
  - None of the three deleted files exist in the repo.
  - `pytest backend/tests/ -v` full suite passes with zero failures.
  - `python -c "from errors import ErrorCode, make_error_response, JunoError"` (from `backend/`) succeeds.
  - `python -c "import error_codes"` (from `backend/`) raises `ModuleNotFoundError`.
- **Commit:** `chore(cleanup): delete error_codes.py, utils/error_codes.py, utils/pipeline_errors.py`

---

## Verification

Run from the `backend/` directory (with the virtualenv activated):

```bash
# 1. Import smoke test — no Flask context required
python -c "from errors import ErrorCode, make_error_response, JunoError, build_error_data, build_error_data_from_exc, ERROR_CATALOG, ErrorInfo"

# 2. Completeness check passes at import time (AssertionError if any code missing from catalog)
python -c "import errors.codes"

# 3. Old modules are gone
python -c "import error_codes" 2>&1 | grep -q "ModuleNotFoundError" && echo "PASS: error_codes deleted" || echo "FAIL"
python -c "from utils import error_codes" 2>&1 | grep -q "ImportError\|ModuleNotFoundError" && echo "PASS: utils.error_codes deleted" || echo "FAIL"
python -c "from utils import pipeline_errors" 2>&1 | grep -q "ImportError\|ModuleNotFoundError" && echo "PASS: utils.pipeline_errors deleted" || echo "FAIL"

# 4. No stale import references (excluding the errors/ package itself)
grep -rn "from error_codes\|from utils.error_codes\|from utils.pipeline_errors" backend/ --include="*.py" | grep -v ".venv" | grep -v "backend/errors/"

# 5. Full test suite
pytest backend/tests/ -v

# 6. Lint
flake8 backend/errors/ --max-line-length=120
```

**"Done" looks like:** All six commands above complete with zero errors, zero stale import grep hits, and the full pytest suite green.
