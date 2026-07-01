# Tasks: SP12 — Error System & Athena External API Consolidation

## Prerequisites

Purpose: (1) move `AthenaAPIError` from `backend/models/external_api/athena_errors.py` into
`backend/errors/athena_errors.py`, fixing the live 429-classification bug at its root via a
new `classify()` classmethod; (2) introduce a parallel `VertexAPIError` in
`backend/errors/vertex_errors.py`, retiring the free function `classify_vertex_exception`;
(3) rename `backend/models/errors.py` → `backend/models/api_response.py` to stop colliding
with the `errors/` package name. All decisions are locked in PRD §9 (Q1–Q8 `[RESOLVED]`, Q9
`[DEFERRED]` — explicitly out of scope, Q10 is an SP13 coordination note, not a question).
No `[OPEN]` items exist.

This is a pure backend Python refactor. No HTTP wire-contract change, no frontend change, no
`errors/codes.py` data change, no deprecation shims (test-only codebase; locked decision —
PRD §3).

All work is under `backend/`. After every task, run from `backend/`:
```bash
python -m pytest tests/ -q
python -c "import errors, models, services.external_api"
```
both must stay green / succeed.

> Note: `routes/worker.py` is touched by Task 2 only, at exactly one line-group (the local
> import inside the `elif source_kind in ("athena_encounter", "athena_clinical_doc"):`
> branch). PRD §9 Q10: SP13 (routes/utils/services boundary cleanup) treats this line as
> already changed when it sequences its own edits to the same file — do not let Task 2 drift
> from the exact diff in PRD §4i.

---

## Tasks

### Task 1 — Rename `models/errors.py` → `models/api_response.py`

- **Goal:** Stop the name collision between the Pydantic wire-shape module
  `backend/models/errors.py` and the logic+data package `backend/errors/`. Pure rename; zero
  content change. (PRD §4h, §9 Q4.)
- **Files:**
  - `backend/models/errors.py` → renamed to `backend/models/api_response.py`
  - `backend/models/__init__.py`
  - `backend/models/job.py`
  - `backend/errors/exceptions.py`
  - `backend/tests/errors/test_exceptions.py`
  - `backend/tests/models/test_errors.py` → renamed to `backend/tests/models/test_api_response.py`
  - `backend/tests/models/test_job.py`
- **Steps:**
  1. `git mv backend/models/errors.py backend/models/api_response.py`. Content is byte-identical
     (`StatusEnum`, `ErrorDetail`, `ApiResponse` — no logic change).
  2. In `backend/models/__init__.py` line 4, change:
     ```python
     from .errors import ApiResponse, ErrorDetail, StatusEnum
     ```
     to:
     ```python
     from .api_response import ApiResponse, ErrorDetail, StatusEnum
     ```
  3. In `backend/models/job.py` line 10, change:
     ```python
     from .errors import ErrorDetail, StatusEnum
     ```
     to:
     ```python
     from .api_response import ErrorDetail, StatusEnum
     ```
  4. In `backend/errors/exceptions.py` line 26, change:
     ```python
     from models.errors import ApiResponse, ErrorDetail, StatusEnum
     ```
     to:
     ```python
     from models.api_response import ApiResponse, ErrorDetail, StatusEnum
     ```
  5. In `backend/tests/errors/test_exceptions.py`, inside
     `test_make_error_response_returns_api_response` (line 3), change:
     ```python
     from models.errors import ApiResponse, StatusEnum
     ```
     to:
     ```python
     from models.api_response import ApiResponse, StatusEnum
     ```
  6. `git mv backend/tests/models/test_errors.py backend/tests/models/test_api_response.py`.
     Inside the renamed file, update every `from models.errors import ...` (current lines 5,
     20, 29, 36) to `from models.api_response import ...`. The four test functions themselves
     (`test_api_response_error_round_trip`, `test_api_response_path_is_optional`,
     `test_api_response_extra_field_raises`, `test_status_enum_values`) are unchanged — their
     names already say `test_api_response_*`, only the import path moves.
  7. In `backend/tests/models/test_job.py` line 7, change:
     ```python
     from models.errors import StatusEnum, ErrorDetail
     ```
     to:
     ```python
     from models.api_response import StatusEnum, ErrorDetail
     ```
  8. Do NOT touch `backend/models/batch_requests.py` — out of scope for this task (PRD §4l;
     see Task 7 for why no batch_requests.py change is needed at all in this PRD).
- **Acceptance criteria:**
  - `backend/models/errors.py` no longer exists; `backend/models/api_response.py` exists with
    the unchanged `StatusEnum`/`ErrorDetail`/`ApiResponse` definitions.
  - `backend/tests/models/test_errors.py` no longer exists;
    `backend/tests/models/test_api_response.py` exists.
  - `grep -rn "models\.errors\b\|from \.errors import\|from models import errors\b" backend --include=*.py | grep -v '\.venv/'` returns no matches.
  - `cd backend && python -m pytest tests/models/test_api_response.py tests/models/test_job.py tests/errors/test_exceptions.py -q` passes.
- **Commit:** `refactor(backend): rename models/errors.py to models/api_response.py`

---

### Task 2 — Move `AthenaAPIError` into `errors/athena_errors.py`, fix 429-classification bug, update every consumer

- **Goal:** Close the bug described in PRD §1.2 / §4a at its root: `AthenaAPIError`'s
  constructor currently has a flat default (`code: ErrorCode = ErrorCode.ATHENA_API_ERROR`)
  that ignores `status_code`, so any call site that omits `code=` silently mis-classifies a
  429 as the generic error instead of `ATHENA_RATE_LIMIT_ERROR`. Fix: move the class into
  `errors/`, give it a `classify(status_code)` classmethod, and call it automatically from
  `__init__` whenever `code` is not passed. Update every import site so the old
  `models/external_api/athena_errors.py` can be deleted outright (no compat shim — PRD §3).
  (PRD §4b, §4f, §4i, §4j, §4k; partial §4e.)
- **Files:**
  - `backend/errors/athena_errors.py` (new)
  - `backend/models/external_api/athena_errors.py` (delete)
  - `backend/errors/__init__.py` (edit)
  - `backend/services/external_api/athena_client.py` (edit)
  - `backend/services/external_api/__init__.py` (edit)
  - `backend/models/external_api/__init__.py` (edit)
  - `backend/routes/worker.py` (edit — single line-group, line 231)
- **Steps:**
  1. Create `backend/errors/athena_errors.py`:
     ```python
     """errors/athena_errors.py — Athena Health API error type and classification."""
     from __future__ import annotations

     from errors.codes import ErrorCode
     from errors.exceptions import JunoError


     class AthenaAPIError(JunoError):
         """Raised when an Athena API call returns a non-200 HTTP status.

         Inherits JunoError so pipeline callers catch it uniformly. status_code
         and body are Athena-specific and remain available directly; the detail
         string also encodes them.

         Status-code -> ErrorCode mapping is centralized in classify(): callers
         that omit `code` get the correct classification automatically, including
         429 -> ATHENA_RATE_LIMIT_ERROR. Endpoint-context failures that can't be
         inferred from the status code alone (e.g. OAuth2 token-fetch failures,
         which must always be ATHENA_AUTH_FAILED regardless of which status code
         Athena happens to return) still pass `code` explicitly to override.
         """

         def __init__(
             self,
             status_code: int,
             body: str,
             code: ErrorCode | None = None,
         ) -> None:
             self.status_code = status_code
             self.body = body
             resolved_code = code if code is not None else self.classify(status_code)
             super().__init__(resolved_code, detail=f"status={status_code} body={body[:200]}")

         @classmethod
         def classify(cls, status_code: int) -> ErrorCode:
             """Single source of truth for Athena status-code -> ErrorCode mapping.

             429 always maps to ATHENA_RATE_LIMIT_ERROR. Everything else (401,
             403, 404, 500, 503, ...) maps to the generic ATHENA_API_ERROR. A
             clinical-document 404 intentionally maps to ATHENA_API_ERROR (502),
             not ATHENA_PATIENT_NOT_FOUND — that code is reserved for a future
             patient-search endpoint and is not wired up by this mapping.
             """
             if status_code == 429:
                 return ErrorCode.ATHENA_RATE_LIMIT_ERROR
             return ErrorCode.ATHENA_API_ERROR
     ```
  2. Delete `backend/models/external_api/athena_errors.py`
     (`git rm backend/models/external_api/athena_errors.py`).
  3. In `backend/errors/__init__.py`, add the new import and export (leave the existing
     `classify_vertex_exception` import/export alone — that is Task 4's job):
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
     from errors.athena_errors import AthenaAPIError

     __all__ = [
         "ERROR_CATALOG", "ErrorCode", "ErrorInfo",
         "JunoError",
         "make_error_response",
         "build_error_data",
         "build_error_data_from_exc",
         "handle_exception",
         "classify_vertex_exception",
         "classify_finish_reason",
         "AthenaAPIError",
     ]
     ```
  4. In `backend/services/external_api/athena_client.py`:
     - Replace the import block at lines 18–19:
       ```python
       from models.external_api.athena_errors import AthenaAPIError
       from errors import ErrorCode
       ```
       with:
       ```python
       from errors import AthenaAPIError, ErrorCode
       ```
     - In `_get()` (current lines 66–109), remove the now-redundant explicit
       `code=ErrorCode.ATHENA_RATE_LIMIT_ERROR` kwargs — the constructor now derives them
       automatically via `classify()`. Replace the full method body:
       ```python
       def _get(
           self,
           path: str,
           retries: int | None = None,
           scope: Scope | None = None,
       ) -> dict:
           """GET with retry on 429; raises AthenaAPIError on other non-200.

           AthenaAPIError(status_code, body) now classifies 429 -> RATE_LIMIT
           automatically (AthenaAPIError.classify) — no explicit code= needed here.
           """
           if retries is None:
               retries = Constants.Athena.MAX_RETRIES
           for attempt in range(retries + 1):
               token = self.get_token()
               resp = requests.get(
                   f"{Constants.Athena.BASE_URL}{path}",
                   headers={"Authorization": f"Bearer {token}"},
                   timeout=Constants.Athena.HTTP_TIMEOUT_GET_S,
               )
               if resp.status_code == 429:
                   wait = int(resp.headers.get("Retry-After", 60))
                   if attempt == retries:
                       if scope:
                           scope.add(Constants.Observability.DIM_STATUS_CODE, 429)
                           scope.add("retries", attempt)
                       raise AthenaAPIError(429, f"Rate limit exceeded after {retries} retries")
                   logger.warning(
                       "athena_client: rate limited on %s (attempt %d/%d), sleeping %ds",
                       path, attempt + 1, retries, wait,
                   )
                   time.sleep(wait)
                   continue
               if scope:
                   scope.add(Constants.Observability.DIM_STATUS_CODE, resp.status_code)
                   scope.add("retries", attempt)
               if resp.status_code != 200:
                   raise AthenaAPIError(resp.status_code, resp.text)
               return resp.json()
           # Unreachable under valid configs (retries >= 0): every iteration above
           # either returns or raises. Kept only as a defensive fallback for a
           # hypothetical retries < 0 misconfiguration.
           raise AthenaAPIError(429, "Rate limit: max retries exhausted")
       ```
     - Leave `get_token()` (current lines 29–64) byte-identical, including its explicit
       override `raise AthenaAPIError(resp.status_code, resp.text, code=ErrorCode.ATHENA_AUTH_FAILED)`
       — auth failures are endpoint-context, not status-code-derivable, so this override is
       intentional and stays.
  5. In `backend/services/external_api/__init__.py`, remove the `AthenaAPIError` re-export:
     ```python
     """services/external_api — Juno's outbound HTTP clients for external APIs."""
     from .athena_client import athena_client, AthenaClient

     __all__ = ["athena_client", "AthenaClient"]
     ```
  6. In `backend/models/external_api/__init__.py`, remove the `AthenaAPIError` import/export,
     keep the `athena_models` re-exports as-is:
     ```python
     """External API model re-exports."""

     from .athena_models import (
         AthenaTokenRequest,
         AthenaTokenResponse,
         AthenaEncounterSummaryRequest,
         AthenaEncounterSummaryResponse,
         AthenaClinicalDocumentMeta,
         AthenaClinicalDocumentListRequest,
         AthenaClinicalDocumentListResponse,
         AthenaClinicalDocumentContentRequest,
         AthenaClinicalDocumentContentResponse,
         AthenaPushDocumentRequest,
         AthenaPushDocumentResponse,
     )

     __all__ = [
         "AthenaTokenRequest",
         "AthenaTokenResponse",
         "AthenaEncounterSummaryRequest",
         "AthenaEncounterSummaryResponse",
         "AthenaClinicalDocumentMeta",
         "AthenaClinicalDocumentListRequest",
         "AthenaClinicalDocumentListResponse",
         "AthenaClinicalDocumentContentRequest",
         "AthenaClinicalDocumentContentResponse",
         "AthenaPushDocumentRequest",
         "AthenaPushDocumentResponse",
     ]
     ```
  7. In `backend/routes/worker.py`, line 231 (inside
     `elif source_kind in ("athena_encounter", "athena_clinical_doc"):`), change:
     ```python
                 from services.external_api import athena_client, AthenaAPIError
     ```
     to:
     ```python
                 from services.external_api import athena_client
                 from errors import AthenaAPIError
     ```
     Do not touch anything else in `worker.py` — not the `except AthenaAPIError as exc:` block
     (current line 245), not the top-level `from errors import ErrorCode, build_error_data, build_error_data_from_exc`
     import (current line 28), not any surrounding logic. This is the one line-group SP13
     expects already changed (PRD §9 Q10).
- **Acceptance criteria:**
  - `backend/models/external_api/athena_errors.py` no longer exists.
  - `backend/errors/athena_errors.py` exists, defines `AthenaAPIError(JunoError)` with a
    `classify(status_code: int) -> ErrorCode` classmethod, and the constructor calls it
    automatically when `code` is omitted.
  - `grep -rn "models\.external_api\.athena_errors\|models\.external_api import.*AthenaAPIError" backend --include=*.py | grep -v '\.venv/'` returns no matches.
  - `grep -n "AthenaAPIError" backend/services/external_api/__init__.py backend/models/external_api/__init__.py` returns no matches.
  - `cd backend && python -c "from errors import AthenaAPIError, ErrorCode; e = AthenaAPIError(429, 'x'); assert e.error_code == ErrorCode.ATHENA_RATE_LIMIT_ERROR; print('ok')"` prints `ok`.
  - `backend/models/external_api/` contains exactly one content file (`athena_models.py`,
    plus `__init__.py`); `backend/services/external_api/` contains exactly one content file
    (`athena_client.py`, plus `__init__.py`) — confirms the PRD §4l file-count rule still
    holds flat (no `athena/` subfolder) after this move. No edit to
    `backend/models/batch_requests.py` is needed or made (PRD §4l: `AthenaEncounterSelection`/
    `AthenaClinicalDocSelection` stay where they are — verify with
    `git status backend/models/batch_requests.py` showing no changes).
- **Commit:** `fix(backend): move AthenaAPIError into errors/, classify 429 by construction`

---

### Task 3 — Fix the bug-locking test and update `test_athena_client.py`'s import

- **Goal:** `tests/errors/test_exceptions.py::test_athena_api_error_is_juno_error` currently
  asserts the *buggy* pre-Task-2 behavior (`AthenaAPIError(429, ...)` without `code=` yields
  `ATHENA_API_ERROR`). After Task 2, that assertion is false and the test fails — this task
  corrects it to assert the fixed behavior, and adds direct coverage of the new `classify()`
  classmethod. (PRD §7.1.)
- **Files:**
  - `backend/tests/errors/test_exceptions.py`
  - `backend/tests/services/external_api/test_athena_client.py`
- **Steps:**
  1. In `backend/tests/errors/test_exceptions.py`, replace the existing
     `test_athena_api_error_is_juno_error` (current lines 76–82):
     ```python
     def test_athena_api_error_is_juno_error():
         from errors import JunoError, ErrorCode
         from models.external_api.athena_errors import AthenaAPIError
         exc = AthenaAPIError(429, "rate limited")
         assert isinstance(exc, JunoError)
         assert exc.error_code == ErrorCode.ATHENA_API_ERROR
         assert exc.status_code == 429
     ```
     with:
     ```python
     def test_athena_api_error_is_juno_error():
         from errors import JunoError, ErrorCode, AthenaAPIError
         exc = AthenaAPIError(429, "rate limited")
         assert isinstance(exc, JunoError)
         assert exc.error_code == ErrorCode.ATHENA_RATE_LIMIT_ERROR
         assert exc.status_code == 429


     def test_athena_api_error_defaults_non_429_to_generic_api_error():
         from errors import ErrorCode, AthenaAPIError
         exc = AthenaAPIError(503, "service unavailable")
         assert exc.error_code == ErrorCode.ATHENA_API_ERROR


     def test_athena_api_error_classify_directly():
         from errors import ErrorCode, AthenaAPIError
         assert AthenaAPIError.classify(429) == ErrorCode.ATHENA_RATE_LIMIT_ERROR
         assert AthenaAPIError.classify(500) == ErrorCode.ATHENA_API_ERROR


     def test_athena_api_error_explicit_code_overrides_classification():
         from errors import ErrorCode, AthenaAPIError
         exc = AthenaAPIError(429, "token failure", code=ErrorCode.ATHENA_AUTH_FAILED)
         assert exc.error_code == ErrorCode.ATHENA_AUTH_FAILED
     ```
  2. In `backend/tests/services/external_api/test_athena_client.py`, line 9, change:
     ```python
     from models.external_api.athena_errors import AthenaAPIError
     ```
     to combine with the existing `from errors import ErrorCode` (current line 10) into one
     import:
     ```python
     from errors import AthenaAPIError, ErrorCode
     ```
     (delete the now-duplicate standalone `from errors import ErrorCode` line). No other line
     in this file changes — `test_get_raises_rate_limit_error_code_after_exhausted_retries`
     and `test_get_raises_athena_api_error_on_non_200` already assert on `.error_code` /
     `.status_code`, not on the presence of an explicit `code=` kwarg, so they pass unchanged
     against the simplified `_get()` from Task 2.
- **Acceptance criteria:**
  - `cd backend && python -m pytest tests/errors/test_exceptions.py tests/services/external_api/test_athena_client.py -q` passes, with 3 new test functions present (`test_athena_api_error_defaults_non_429_to_generic_api_error`, `test_athena_api_error_classify_directly`, `test_athena_api_error_explicit_code_overrides_classification`).
  - `grep -n "models.external_api.athena_errors" backend/tests/services/external_api/test_athena_client.py` returns no matches.
  - `grep -n "ATHENA_API_ERROR$" backend/tests/errors/test_exceptions.py` (i.e. asserting the old buggy default for a 429 case) returns no matches inside `test_athena_api_error_is_juno_error`.
- **Commit:** `test(backend): lock in AthenaAPIError 429 classification fix, not the bug`

---

### Task 4 — Add `VertexAPIError` to `errors/vertex_errors.py`, retire `classify_vertex_exception`

- **Goal:** Give Vertex/Google API failures the same "one error class per external system"
  treatment Athena now has. `classify_vertex_exception` (a free function in
  `errors/exceptions.py`) becomes `VertexAPIError.classify` (a classmethod), matching
  `AthenaAPIError`'s shape from Task 2. (PRD §4c, §4d, §4e.)
- **Files:**
  - `backend/errors/vertex_errors.py` (new)
  - `backend/errors/exceptions.py` (edit)
  - `backend/errors/__init__.py` (edit)
- **Steps:**
  1. Create `backend/errors/vertex_errors.py`:
     ```python
     """errors/vertex_errors.py — Vertex AI / Google API error type and classification."""
     from __future__ import annotations

     from errors.codes import ErrorCode
     from errors.exceptions import JunoError


     class VertexAPIError(JunoError):
         """Raised when a Vertex AI google.api_core call fails.

         Wraps the raw google.api_core exception and classifies it into a
         JunoError ErrorCode via VertexAPIError.classify(). Callers that need to
         handle Vertex AI failures uniformly catch VertexAPIError (or JunoError)
         instead of reaching into google.api_core.exceptions directly.
         """

         def __init__(self, original: Exception, detail: str | None = None) -> None:
             self.original_exc = original
             code = self.classify(original)
             super().__init__(code, detail=detail or str(original), original=original)

         @classmethod
         def classify(cls, exc: Exception) -> ErrorCode:
             """Map a google.api_core.exceptions.* instance to the matching ErrorCode.

             Returns ErrorCode.UNKNOWN_ERROR if google-api-core is not installed
             or the exception type is not in the mapping below.
             """
             try:
                 from google.api_core import exceptions as _gexc
             except ImportError:
                 return ErrorCode.UNKNOWN_ERROR

             _TYPE_MAP = [
                 (_gexc.ResourceExhausted,   ErrorCode.VERTEX_QUOTA_EXCEEDED),
                 (_gexc.DeadlineExceeded,    ErrorCode.VERTEX_DEADLINE_EXCEEDED),
                 (_gexc.InvalidArgument,     ErrorCode.VERTEX_INVALID_ARGUMENT),
                 (_gexc.PermissionDenied,    ErrorCode.VERTEX_PERMISSION_DENIED),
                 (_gexc.NotFound,            ErrorCode.VERTEX_NOT_FOUND),
                 (_gexc.ServiceUnavailable,  ErrorCode.VERTEX_SERVICE_UNAVAILABLE),
                 (_gexc.InternalServerError, ErrorCode.VERTEX_INTERNAL_ERROR),
                 (_gexc.Unauthenticated,     ErrorCode.VERTEX_UNAUTHENTICATED),
                 (_gexc.Aborted,             ErrorCode.VERTEX_ABORTED),
             ]
             for exc_type, code in _TYPE_MAP:
                 if isinstance(exc, exc_type):
                     return code
             return ErrorCode.UNKNOWN_ERROR
     ```
     Naming is locked to `VertexAPIError`, not `GoogleAPIError` (PRD §4c rationale / §9 Q2) —
     do not rename.
  2. In `backend/errors/exceptions.py`:
     - Delete the module docstring's `classify_vertex_exception` bullet (current line 11:
       `  - classify_vertex_exception: map google.api_core exceptions → ErrorCode`) and
       replace it with a one-line pointer:
       ```
         - (Athena/Vertex per-system error classes and their classify() classmethods live in
           errors/athena_errors.py and errors/vertex_errors.py, not in this module.)
       ```
     - Delete the entire `classify_vertex_exception` function (current lines 72–102, including
       its `# ---` section-header comments).
     - Replace `_classify_exc` (current lines 136–157):
       ```python
       def _classify_exc(exc: Exception) -> tuple[ErrorCode, str]:
           """
           Return ``(error_code, detail_str)`` for any exception.

           Priority:
           1. JunoError — already classified; use its error_code and detail.
           2. google.api_core.exceptions.GoogleAPICallError → classify_vertex_exception.
           3. Everything else → UNKNOWN_ERROR.
           """
           if isinstance(exc, JunoError):
               detail = exc.detail or str(exc.original or exc)
               return exc.error_code, detail

           # Google API errors
           try:
               from google.api_core import exceptions as _gexc
               if isinstance(exc, _gexc.GoogleAPICallError):
                   return classify_vertex_exception(exc), str(exc)
           except ImportError:
               pass

           return ErrorCode.UNKNOWN_ERROR, str(exc)
       ```
       with:
       ```python
       def _classify_exc(exc: Exception) -> tuple[ErrorCode, str]:
           """
           Return ``(error_code, detail_str)`` for any exception.

           Priority:
           1. JunoError — already classified; use its error_code and detail.
           2. google.api_core.exceptions.GoogleAPICallError → VertexAPIError.classify.
           3. Everything else → UNKNOWN_ERROR.
           """
           if isinstance(exc, JunoError):
               detail = exc.detail or str(exc.original or exc)
               return exc.error_code, detail

           # Google API errors — deferred import avoids a module-level cycle with
           # errors.vertex_errors (which imports JunoError from this module).
           try:
               from google.api_core import exceptions as _gexc
               from errors.vertex_errors import VertexAPIError
               if isinstance(exc, _gexc.GoogleAPICallError):
                   return VertexAPIError.classify(exc), str(exc)
           except ImportError:
               pass

           return ErrorCode.UNKNOWN_ERROR, str(exc)
       ```
       Note the `from errors.vertex_errors import VertexAPIError` is deferred (inside the
       function body, not at module scope) — `errors/vertex_errors.py` imports `JunoError`
       from this module, so a module-level import here would create a circular import.
  3. In `backend/errors/__init__.py`, remove `classify_vertex_exception` and add
     `VertexAPIError`, producing the final state:
     ```python
     from errors.codes import ERROR_CATALOG, ErrorCode, ErrorInfo
     from errors.exceptions import (
         JunoError,
         make_error_response,
         build_error_data,
         build_error_data_from_exc,
         handle_exception,
         classify_finish_reason,
     )
     from errors.athena_errors import AthenaAPIError
     from errors.vertex_errors import VertexAPIError

     __all__ = [
         "ERROR_CATALOG", "ErrorCode", "ErrorInfo",
         "JunoError",
         "make_error_response",
         "build_error_data",
         "build_error_data_from_exc",
         "handle_exception",
         "classify_finish_reason",
         "AthenaAPIError",
         "VertexAPIError",
     ]
     ```
  4. Do NOT touch `backend/errors/codes.py` — no new `ErrorCode` members, no catalog edits
     (PRD §3, §4d).
- **Acceptance criteria:**
  - `backend/errors/vertex_errors.py` exists, defines `VertexAPIError(JunoError)` with a
    `classify(exc: Exception) -> ErrorCode` classmethod matching the type-map above.
  - `grep -rn "classify_vertex_exception" backend --include=*.py | grep -v '\.venv/'` returns
    no matches anywhere (function deleted, no remaining references).
  - `cd backend && python -c "from errors import VertexAPIError, ErrorCode; from google.api_core import exceptions as g; e = VertexAPIError(g.ResourceExhausted('x')); assert e.error_code == ErrorCode.VERTEX_QUOTA_EXCEEDED; print('ok')"` prints `ok`.
  - `cd backend && python -c "import errors"` succeeds with no `ImportError` (confirms the
    deferred-import fix avoids the `errors.exceptions` ↔ `errors.vertex_errors` cycle).
- **Commit:** `refactor(backend): introduce VertexAPIError, retire classify_vertex_exception`

---

### Task 5 — Wire `utils/llm.py` to raise `VertexAPIError` instead of a bare `JunoError`

- **Goal:** `utils/llm.py` currently calls the free function `classify_vertex_exception` and
  manually re-raises a bare `JunoError`. Switch it to raise `VertexAPIError` directly, so
  Vertex failures get the same typed-exception treatment as Athena failures (callers that
  want to distinguish "this came from Vertex" can `except VertexAPIError`; everything that
  currently does `except JunoError` keeps working since `VertexAPIError` subclasses it). No
  `ErrorCode`-level behavior change. (PRD §4g.)
- **Files:**
  - `backend/utils/llm.py`
- **Steps:**
  1. Line 27, change:
     ```python
     from errors import ErrorCode, JunoError, classify_finish_reason, classify_vertex_exception
     ```
     to:
     ```python
     from errors import ErrorCode, JunoError, VertexAPIError, classify_finish_reason
     ```
  2. Lines 71–84 (the `except Exception as api_exc:` block inside `generate_text`), change:
     ```python
         except Exception as api_exc:
             # Classify google.api_core exceptions; re-raise others as UNKNOWN_ERROR
             try:
                 from google.api_core import exceptions as _gexc
                 if isinstance(api_exc, _gexc.GoogleAPICallError):
                     error_code = classify_vertex_exception(api_exc)
                     raise JunoError(error_code, detail=str(api_exc), original=api_exc) from api_exc
             except ImportError:
                 pass
             raise JunoError(
                 ErrorCode.UNKNOWN_ERROR,
                 detail=f"Vertex AI generate_content raised an unexpected error: {api_exc}",
                 original=api_exc,
             ) from api_exc
     ```
     to:
     ```python
         except Exception as api_exc:
             # Classify google.api_core exceptions via VertexAPIError; re-raise others as UNKNOWN_ERROR
             try:
                 from google.api_core import exceptions as _gexc
                 if isinstance(api_exc, _gexc.GoogleAPICallError):
                     raise VertexAPIError(api_exc) from api_exc
             except ImportError:
                 pass
             raise JunoError(
                 ErrorCode.UNKNOWN_ERROR,
                 detail=f"Vertex AI generate_content raised an unexpected error: {api_exc}",
                 original=api_exc,
             ) from api_exc
     ```
  3. Do not change any other line in `utils/llm.py` (the `LLMClient.__init__`, the
     no-candidates / max-tokens checks below this block, `generate_json`, etc. are all out of
     scope).
- **Acceptance criteria:**
  - `grep -n "classify_vertex_exception" backend/utils/llm.py` returns no matches.
  - `grep -n "VertexAPIError" backend/utils/llm.py` shows the import and the
    `raise VertexAPIError(api_exc) from api_exc` line.
  - `cd backend && python -m pytest tests/utils/test_llm.py -q` passes unchanged (no test in
    this file currently exercises the `GoogleAPICallError` branch — see Task 6 for new
    coverage).
- **Commit:** `refactor(backend): raise VertexAPIError from utils/llm.py instead of classify_vertex_exception`

---

### Task 6 — Add `VertexAPIError.classify` parity tests and an `utils/llm.py` Vertex-failure test

- **Goal:** PRD §7.2 calls for porting the implicit type-map coverage (previously only
  exercised indirectly through `classify_vertex_exception`) into a direct test of
  `VertexAPIError.classify`. PRD §7.3 calls for asserting `utils/llm.py` raises specifically
  `VertexAPIError` on a `GoogleAPICallError`. Neither test currently exists in the repo
  (confirmed: no test file references `GoogleAPICallError`, `classify_vertex_exception`, or
  `VertexAPIError` before this task) — both are net-new additions, not edits to an existing
  test.
- **Files:**
  - `backend/tests/errors/test_exceptions.py`
  - `backend/tests/utils/test_llm.py`
- **Steps:**
  1. In `backend/tests/errors/test_exceptions.py`, add (anywhere after the Athena tests added
     in Task 3; google-api-core is an installed dependency in this repo so no skip-guard is
     needed):
     ```python
     def test_vertex_api_error_classify_type_map():
         from errors import ErrorCode, VertexAPIError
         from google.api_core import exceptions as gexc

         cases = [
             (gexc.ResourceExhausted("x"), ErrorCode.VERTEX_QUOTA_EXCEEDED),
             (gexc.DeadlineExceeded("x"), ErrorCode.VERTEX_DEADLINE_EXCEEDED),
             (gexc.InvalidArgument("x"), ErrorCode.VERTEX_INVALID_ARGUMENT),
             (gexc.PermissionDenied("x"), ErrorCode.VERTEX_PERMISSION_DENIED),
             (gexc.NotFound("x"), ErrorCode.VERTEX_NOT_FOUND),
             (gexc.ServiceUnavailable("x"), ErrorCode.VERTEX_SERVICE_UNAVAILABLE),
             (gexc.InternalServerError("x"), ErrorCode.VERTEX_INTERNAL_ERROR),
             (gexc.Unauthenticated("x"), ErrorCode.VERTEX_UNAUTHENTICATED),
             (gexc.Aborted("x"), ErrorCode.VERTEX_ABORTED),
         ]
         for exc, expected_code in cases:
             assert VertexAPIError.classify(exc) == expected_code


     def test_vertex_api_error_classify_unmapped_type_returns_unknown():
         from errors import ErrorCode, VertexAPIError
         assert VertexAPIError.classify(ValueError("not a google exception")) == ErrorCode.UNKNOWN_ERROR


     def test_vertex_api_error_is_juno_error():
         from errors import JunoError, ErrorCode, VertexAPIError
         from google.api_core import exceptions as gexc
         original = gexc.ResourceExhausted("quota")
         exc = VertexAPIError(original)
         assert isinstance(exc, JunoError)
         assert exc.error_code == ErrorCode.VERTEX_QUOTA_EXCEEDED
         assert exc.original is original
     ```
     (The `classify()`-vs-`ImportError`-fallback path is already implicitly covered by Task 4's
     `python -c` acceptance check at import time; google-api-core is always importable in this
     repo's venv, so an explicit `ImportError` branch test is not practically constructible
     here and is not required.)
  2. In `backend/tests/utils/test_llm.py`, add a new test exercising the `generate_text`
     except-block from Task 5. Follow the existing `vertex_env` fixture pattern used by every
     other test in this file (see e.g. `test_generate_text_returns_stripped_text`,
     `test_generate_text_no_candidates_raises`):
     ```python
     def test_generate_text_vertex_failure_raises_vertex_api_error(vertex_env):
         mock_vertexai, mock_GenerativeModel, _, _, mock_FinishReason, _ = vertex_env
         mock_model_instance = MagicMock()
         mock_GenerativeModel.return_value = mock_model_instance

         from google.api_core import exceptions as gexc
         mock_model_instance.generate_content.side_effect = gexc.ResourceExhausted("quota exceeded")

         from errors import ErrorCode, VertexAPIError
         from utils.llm import LLMClient
         client = LLMClient()
         with pytest.raises(VertexAPIError) as exc_info:
             client.generate_text("prompt")
         assert exc_info.value.error_code == ErrorCode.VERTEX_QUOTA_EXCEEDED
     ```
     Place it near the other `generate_text`-failure tests (after
     `test_generate_text_no_candidates_raises`, before the `generate_json` tests section).
- **Acceptance criteria:**
  - `cd backend && python -m pytest tests/errors/test_exceptions.py -k vertex_api_error -q` runs 3 passing tests.
  - `cd backend && python -m pytest tests/utils/test_llm.py -k vertex_api_error -q` runs 1 passing test.
  - `cd backend && python -m pytest tests/ -q` passes in full.
- **Commit:** `test(backend): add VertexAPIError.classify parity tests and utils/llm.py Vertex-failure coverage`

---

### Task 7 — Repo-wide import-path sweep and final verification

- **Goal:** Mechanically confirm every import site touched by Tasks 1–6 was actually updated
  (PRD §7.5) and that the export surfaces of `models/external_api/__init__.py` /
  `services/external_api/__init__.py` no longer mention `AthenaAPIError` (PRD §7.6). This is a
  verification-only task — if any grep below returns an unexpected hit, fix the missed site
  before closing this task; do not add new source changes beyond fixing a missed site.
- **Files:** none new — read-only verification across `backend/` (excluding `backend/.venv/`).
- **Steps:**
  1. Run, from the repo root:
     ```bash
     grep -rn "models\.errors\b\|from \.errors import\|models\.external_api\.athena_errors\|services\.external_api import.*AthenaAPIError\|classify_vertex_exception" backend --include=*.py | grep -v '/\.venv/'
     ```
     Expected: zero matches.
  2. Run:
     ```bash
     cd backend && python -c "import errors, models, services.external_api; print('import ok')"
     ```
     Expected: prints `import ok` with no traceback.
  3. Run the full backend test suite:
     ```bash
     cd backend && python -m pytest tests/ -q
     ```
     Expected: all tests pass (no failures, no errors, no unexpected skips related to this
     PRD's files).
  4. Confirm the two `__init__.py` export surfaces from Task 2 (PRD §7.6):
     ```bash
     grep -n "AthenaAPIError" backend/models/external_api/__init__.py backend/services/external_api/__init__.py
     ```
     Expected: zero matches in both files.
  5. Confirm the final directory shape matches PRD §4m:
     ```bash
     ls backend/errors/        # expect: __init__.py codes.py exceptions.py athena_errors.py vertex_errors.py (+ __pycache__)
     ls backend/models/external_api/   # expect: __init__.py athena_models.py (+ __pycache__) — athena_errors.py gone
     ls backend/services/external_api/ # expect: __init__.py athena_client.py (+ __pycache__)
     ls backend/models/ | grep -i "errors\|api_response"   # expect: api_response.py only, no errors.py
     ```
- **Acceptance criteria:**
  - All five commands above produce exactly the expected output described in each step.
  - No source-code changes are committed as part of this task unless step 1–5 surfaced a
    missed import site from an earlier task, in which case the fix is a one-line import
    correction in the affected file, re-verified by re-running step 1–3.
- **Commit:** `chore(backend): verify SP12 import-path sweep is complete` (omit this commit
  entirely if no fix was needed and you'd rather fold the verification into Task 6's commit —
  either is acceptable since this task makes no required code change in the common case).

---

## Verification

Run all commands from `backend/`:

```bash
# 1. Full backend test suite
python -m pytest tests/ -q

# 2. Import sanity check
python -c "import errors, models, services.external_api"

# 3. Targeted regression tests for this PRD
python -m pytest tests/errors/test_exceptions.py tests/models/test_api_response.py \
  tests/models/test_job.py tests/services/external_api/test_athena_client.py \
  tests/utils/test_llm.py -q
```

Targeted greps (run from repo root; all must return zero matches):

```bash
grep -rn "models\.errors\b\|from \.errors import" backend --include=*.py | grep -v '/\.venv/'
grep -rn "models\.external_api\.athena_errors" backend --include=*.py | grep -v '/\.venv/'
grep -rn "services\.external_api import.*AthenaAPIError" backend --include=*.py | grep -v '/\.venv/'
grep -rn "classify_vertex_exception" backend --include=*.py | grep -v '/\.venv/'
```

### Definition of done

- All seven tasks committed (one logical commit each — Task 7 may be a no-op commit or folded
  into Task 6 if no missed site is found), in order.
- `backend/models/errors.py` and `backend/models/external_api/athena_errors.py` no longer
  exist; `backend/models/api_response.py` and `backend/errors/athena_errors.py` exist.
- `backend/errors/vertex_errors.py` exists; `classify_vertex_exception` no longer exists
  anywhere in `backend/` (excluding `.venv`).
- `AthenaAPIError(429, body)` with no explicit `code=` now classifies as
  `ErrorCode.ATHENA_RATE_LIMIT_ERROR` (the bug from PRD §1.2 is fixed and locked in by a test).
- `python -m pytest tests/ -q` passes in full from `backend/`.
- Every targeted grep above returns no matches.
- No changes to `backend/errors/codes.py`, `backend/models/batch_requests.py`, or any
  frontend file (all explicitly out of scope per PRD §3 / §6).

---

## Summary of what requires you (not a dev agent)

**None.** This matches PRD §8 ("Manual Intervention Required From You: None") exactly — the
PRD's own verification found:
- `backend/cloudbuild.yaml` and `.github/workflows/ci.yml` contain no references to any file
  path touched by this PRD (`models/errors.py`, `models/external_api/*`,
  `services/external_api/*`, `errors/*`) — already grepped by the PRD author, zero hits.
- No environment variables, secrets, GCP console steps, or Firestore/storage migrations are
  implicated — this is a pure Python module-reorganization with no schema or infra surface.

The one cross-team item is **not** a manual step for you, but a sequencing note: PRD §9 Q10
flags that SP13 (Observability/Routes Cleanup, a sibling sub-project, see
`docs/agent_files/tasks/2026-06-29/13-observability-routes-cleanup/PRD.md`) also edits
`backend/routes/worker.py`. SP13's own PRD (§3, confirmed by reading it) already accounts for
Task 2's one-line-group change here as a given and does not re-touch it — so as long as Task 2
in this file is applied before or independently of SP13's edits to the same file, no merge
conflict requiring your judgment should arise. If SP13 is implemented first, this task's
Step 7 in Task 2 should be re-diffed against whatever `routes/worker.py` looks like at that
point before applying, since SP13 also relocates the imports above `execute_job`.

PRD §9 Q9 (`ErrorCode.ATHENA_PATIENT_NOT_FOUND` remains defined-but-unused) is `[DEFERRED]`,
not something this task list implements — no action needed, confirmed out of scope.
