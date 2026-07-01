# PRD: SP12 — Error System & Athena External API Consolidation

**Sub-project:** SP12
**Series:** 2026-06-29 backend cleanup (SP11–SP14)
**Date:** 2026-06-29
**Status:** Planning — no implementation started
**Depends on:** none
**Touches a file shared with SP13:** `backend/routes/worker.py` (see §4i / §9 for exact lines)

---

## 1. Problem

The Juno error system has grown two independent, inconsistent "classify an external failure into an `ErrorCode`" mechanisms, and the one that exists for Athena has a real, demonstrated bug:

1. **`AthenaAPIError` lives outside `errors/`.** It is the only `JunoError` subclass in the codebase and the only one not inside the `errors/` folder (it sits at `backend/models/external_api/athena_errors.py`). Every other piece of error logic (`JunoError`, `classify_finish_reason`, `make_error_response`, `build_error_data*`, `handle_exception`) lives in `errors/exceptions.py`. This split makes "where do I add a new error type" ambiguous.

2. **Athena status-code classification is scattered, not centralized, and the default is silently wrong.** `AthenaAPIError.__init__` takes `code: ErrorCode = ErrorCode.ATHENA_API_ERROR` as a flat default — it does not look at `status_code` at all. Every call site that wants correct classification (e.g. 429 → `ATHENA_RATE_LIMIT_ERROR`, token failure → `ATHENA_AUTH_FAILED`) must remember to pass `code=` explicitly. `backend/services/external_api/athena_client.py` happens to get this right today because both 429-raise sites (lines 88–92, 105–109) manually pass `code=ErrorCode.ATHENA_RATE_LIMIT_ERROR`. But this is fragile-by-construction, and **the bug is already live and locked-in by a test**:

   ```python
   # backend/tests/errors/test_exceptions.py:76-82 (CURRENT, as committed)
   def test_athena_api_error_is_juno_error():
       from errors import JunoError, ErrorCode
       from models.external_api.athena_errors import AthenaAPIError
       exc = AthenaAPIError(429, "rate limited")
       assert isinstance(exc, JunoError)
       assert exc.error_code == ErrorCode.ATHENA_API_ERROR   # <-- WRONG: this is a 429
       assert exc.status_code == 429
   ```

   This test constructs `AthenaAPIError(429, ...)` **without** an explicit `code=` kwarg — exactly what a future call site would naturally write — and asserts the resulting `error_code` is the generic `ATHENA_API_ERROR`, not `ATHENA_RATE_LIMIT_ERROR`. That assertion is currently *true* (it's the constructor's actual default behavior), and it is *wrong* behavior: a 429 should never classify as the generic API error. This is the bug the prior investigation flagged, precisely located: it lives in the constructor's default-parameter design, not in `athena_client.py`'s retry loop (see §4b/§9 for the full trace).

3. **No parallel error class for Vertex/Google API failures.** `classify_vertex_exception` (`errors/exceptions.py:76-102`) is a free function, not tied to any `JunoError` subclass. `utils/llm.py` calls it manually and re-raises a bare `JunoError` rather than a typed subclass, so Vertex failures don't get the same "one error class per external system" treatment Athena gets.

4. **`models/errors.py` name collides conceptually with `errors/`.** `backend/models/errors.py` is a pure-Pydantic wire-shape module (`StatusEnum`, `ErrorDetail`, `ApiResponse`) with zero logic. `backend/errors/` is a logic+data package (`codes.py`, `exceptions.py`). Both are correct, deliberate, and should stay separate — but the identical name (`errors.py` inside `models/`, `errors/` as a top-level package) makes every new contributor ask "why are there two error modules?"

5. **Athena code is split across two layers in a way that no longer reflects file count.** `services/external_api/` and `models/external_api/` are right as top-level concepts, but `models/external_api/athena_errors.py` is about to move out (into `errors/`), changing the file count in that layer and triggering this PRD's own file-count rule.

---

## 2. Goals

1. Move `AthenaAPIError` into `errors/` (new file `errors/athena_errors.py`), and add a new `VertexAPIError` into `errors/` (new file `errors/vertex_errors.py`), both subclassing `JunoError`.
2. Give both error classes a `classify(...)` **classmethod** that is the single source of truth for status/exception → `ErrorCode` mapping, and make the constructor call it automatically when `code` is not explicitly passed — closing the exact bug in §1.2 at the root, not just patching the one test.
3. Retire the free function `classify_vertex_exception` — its logic becomes `VertexAPIError.classify`.
4. Rename `backend/models/errors.py` → `backend/models/api_response.py` and update every import site.
5. Apply the locked file-count rule to `services/external_api/` and `models/external_api/` post-consolidation, and decide (with reasoning, not just citing the rule) whether `AthenaEncounterSelection`/`AthenaClinicalDocSelection` move out of `models/batch_requests.py`.
6. Enumerate every call site touched so a follow-up implementation pass (and SP13, which shares `routes/worker.py`) has an exact diff list.

---

## 3. Non-Goals

- No change to `Constants.Athena`, `Markers.Athena`, or any retry/timeout tuning values — those are SP11 (Constants) and SP13 (Markers/Observability) territory.
- No change to the clinical-doc 404 → `ATHENA_API_ERROR` (502) behavior. This is correct and explicitly locked.
- No wiring-up of `ErrorCode.ATHENA_PATIENT_NOT_FOUND` — confirmed still unused (grep: only appears in `errors/codes.py` enum + catalog, never raised). Leaving it defined-but-unused is fine; it's reserved for a future patient-search endpoint that doesn't exist yet.
- No change to `errors/codes.py` data (no new `ErrorCode` members, no catalog edits). Verified not needed — see §4 reasoning.
- No deprecation shims, aliases, or compatibility layers for any moved symbol (test-only codebase; locked decision).
- No change to `JunoError` itself (`errors/exceptions.py:49-69`) — its signature and behavior are unaffected by this PRD.
- No DI/factory pattern for `AthenaClient` — out of scope, unrelated to error classification.

---

## 4. Architecture Decisions

### 4a. The bug, traced end-to-end

**Claim to verify:** "AthenaAPIError(429) yields ATHENA_API_ERROR instead of ATHENA_RATE_LIMIT_ERROR."

**Trace of `services/external_api/athena_client.py:_get()` (full method, current code):**

```python
def _get(self, path, retries=None, scope=None) -> dict:
    if retries is None:
        retries = Constants.Athena.MAX_RETRIES
    for attempt in range(retries + 1):
        token = self.get_token()
        resp = requests.get(...)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            if attempt == retries:
                ...
                raise AthenaAPIError(429, f"...", code=ErrorCode.ATHENA_RATE_LIMIT_ERROR)  # explicit, correct
            ...
            time.sleep(wait)
            continue
        ...
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)   # no code= — only reached for non-429, non-200
        return resp.json()
    raise AthenaAPIError(429, "...", code=ErrorCode.ATHENA_RATE_LIMIT_ERROR)  # explicit, correct (and unreachable — see below)
```

**Finding: the runtime path in `athena_client.py` is currently correct.** Every iteration of the loop either (a) hits `status_code == 429`, which always branches into the 429-block (raise-with-explicit-code or sleep-and-continue — it never falls through to the generic non-200 raise), or (b) hits some other status, which returns (200) or raises with the *correct* default (any non-429, non-200 status, e.g. 401/403/404/500/503, correctly wants the generic `ATHENA_API_ERROR`). The trailing `raise AthenaAPIError(429, ...)` after the `for` loop is **dead code** under any `retries >= 0` (every iteration always returns or raises from inside the loop body) — it only matters as a defensive fallback if `retries` were ever negative, which no caller does.

So: confirmed, the *retry-loop* path does not exhibit the bug. **The bug is one level down, in the class itself** — exactly as proven by the test in §1.2. `AthenaAPIError.__init__(status_code, body, code=ErrorCode.ATHENA_API_ERROR)` does no inspection of `status_code`; "correct" classification today is 100% dependent on every call site remembering to pass `code=` by hand. That's the "scattered, not centralized" problem the locked decisions call out, and `test_athena_api_error_is_juno_error` (constructing `AthenaAPIError(429, "rate limited")` with no `code=`) demonstrates the failure mode directly: it gets `ATHENA_API_ERROR`, not `ATHENA_RATE_LIMIT_ERROR`, and the test currently asserts that as correct.

**Fix:** move the classification into a `classify(status_code)` classmethod that the constructor calls automatically whenever `code` is omitted, so 429 is correctly classified *by construction*, everywhere, including any future call site and including this exact test (which gets a corrected assertion — see §7).

---

### 4b. `errors/athena_errors.py` (new — moved from `models/external_api/athena_errors.py`)

**Before** (`backend/models/external_api/athena_errors.py`):
```python
"""Athena Health API error types."""
from errors import ErrorCode, JunoError


class AthenaAPIError(JunoError):
    def __init__(
        self,
        status_code: int,
        body: str,
        code: ErrorCode = ErrorCode.ATHENA_API_ERROR,
    ) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(code, detail=f"status={status_code} body={body[:200]}")
```

**After** (`backend/errors/athena_errors.py`):
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

`models/external_api/athena_errors.py` is **deleted**.

---

### 4c. `errors/vertex_errors.py` (new)

**Before:** no Vertex/Google error class exists; `errors/exceptions.py` has a free function:
```python
# errors/exceptions.py:76-102 (current)
def classify_vertex_exception(exc: Exception) -> ErrorCode:
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

**After** (`backend/errors/vertex_errors.py`, new file):
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

**Naming decision:** `VertexAPIError`, not `GoogleAPIError`. Rationale: every existing `ErrorCode` member for this category is prefixed `VERTEX_*` (`VERTEX_QUOTA_EXCEEDED`, etc.), the only consumer (`utils/llm.py`) is exclusively about Vertex AI generation calls, and the codebase's vocabulary throughout (`Constants.Llm`, docstrings) already says "Vertex AI," not "Google APIs" generally. `GoogleAPIError` would also be misleading once/if GCS or Firestore exceptions (also `google.api_core`-based, in a totally different failure domain) ever need classifying — reserving "Google" for a broader future umbrella avoids a name collision later. **[RESOLVED]** — see §9 if you disagree before implementation.

---

### 4d. `errors/exceptions.py` — before/after

**Before** (`backend/errors/exceptions.py`, relevant excerpts):
```python
from models.errors import ApiResponse, ErrorDetail, StatusEnum
...
def classify_vertex_exception(exc: Exception) -> ErrorCode:
    ...  # full body — see §4c "Before"
...
def _classify_exc(exc: Exception) -> tuple[ErrorCode, str]:
    if isinstance(exc, JunoError):
        detail = exc.detail or str(exc.original or exc)
        return exc.error_code, detail
    try:
        from google.api_core import exceptions as _gexc
        if isinstance(exc, _gexc.GoogleAPICallError):
            return classify_vertex_exception(exc), str(exc)
    except ImportError:
        pass
    return ErrorCode.UNKNOWN_ERROR, str(exc)
```

**After:**
```python
from models.api_response import ApiResponse, ErrorDetail, StatusEnum
...
# classify_vertex_exception REMOVED — logic now lives at VertexAPIError.classify
# (errors/vertex_errors.py). Not imported at module level here: importing
# errors.vertex_errors from errors.exceptions at module scope would create a
# cycle (vertex_errors.py imports JunoError from this module). _classify_exc
# does a deferred (function-body) import instead, exactly like its existing
# deferred google.api_core import below.
...
def _classify_exc(exc: Exception) -> tuple[ErrorCode, str]:
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

Module docstring (lines 1-18) loses its `classify_vertex_exception` bullet (line 11) and gains a one-line pointer to `errors/vertex_errors.py` / `errors/athena_errors.py` for the per-system error classes.

**`errors/codes.py` — NOT touched.** No new `ErrorCode` members, no catalog edits. Verified: `ATHENA_PATIENT_NOT_FOUND` stays defined-but-unused (out of scope, confirmed fine); all status-mapping logic this PRD adds is classmethod logic on the error classes, not new catalog data.

---

### 4e. `errors/__init__.py` — before/after

**Before:**
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

**After:**
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

`classify_vertex_exception` is no longer exported anywhere — replaced by `VertexAPIError.classify`.

---

### 4f. `services/external_api/athena_client.py` — updated `_get()` (centralization removes manual `code=` for the rate-limit cases)

**Before** (current file, full `_get`):
```python
from models.external_api.athena_errors import AthenaAPIError
from errors import ErrorCode
...
def _get(self, path, retries=None, scope=None) -> dict:
    if retries is None:
        retries = Constants.Athena.MAX_RETRIES
    for attempt in range(retries + 1):
        token = self.get_token()
        resp = requests.get(...)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            if attempt == retries:
                if scope:
                    scope.add(Constants.Observability.DIM_STATUS_CODE, 429)
                    scope.add("retries", attempt)
                raise AthenaAPIError(
                    429,
                    f"Rate limit exceeded after {retries} retries",
                    code=ErrorCode.ATHENA_RATE_LIMIT_ERROR,
                )
            logger.warning(...)
            time.sleep(wait)
            continue
        if scope:
            scope.add(Constants.Observability.DIM_STATUS_CODE, resp.status_code)
            scope.add("retries", attempt)
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)
        return resp.json()
    raise AthenaAPIError(
        429,
        "Rate limit: max retries exhausted",
        code=ErrorCode.ATHENA_RATE_LIMIT_ERROR,
    )
```

**After:**
```python
from errors import AthenaAPIError, ErrorCode
...
def _get(self, path, retries=None, scope=None) -> dict:
    """GET with retry on 429; raises AthenaAPIError on other non-200.

    AthenaAPIError(status_code, body) now classifies 429 -> RATE_LIMIT
    automatically (AthenaAPIError.classify) — no explicit code= needed here.
    """
    if retries is None:
        retries = Constants.Athena.MAX_RETRIES
    for attempt in range(retries + 1):
        token = self.get_token()
        resp = requests.get(...)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            if attempt == retries:
                if scope:
                    scope.add(Constants.Observability.DIM_STATUS_CODE, 429)
                    scope.add("retries", attempt)
                raise AthenaAPIError(429, f"Rate limit exceeded after {retries} retries")
            logger.warning(...)
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

`get_token()` is **unchanged in behavior** but keeps its explicit override (auth failures are endpoint-context, not status-code-derivable — see §4b docstring):
```python
if resp.status_code != 200:
    raise AthenaAPIError(resp.status_code, resp.text, code=ErrorCode.ATHENA_AUTH_FAILED)
```

Only the import line changes (`from models.external_api.athena_errors import AthenaAPIError` → `from errors import AthenaAPIError`); the rest of `get_token()` is byte-identical.

---

### 4g. `utils/llm.py` — wrap Vertex failures in `VertexAPIError`

**Before** (lines 27, 71-84):
```python
from errors import ErrorCode, JunoError, classify_finish_reason, classify_vertex_exception
...
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

**After:**
```python
from errors import ErrorCode, JunoError, VertexAPIError, classify_finish_reason
...
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

Behavior is unchanged at the `ErrorCode` level (same mapping, now sourced from `VertexAPIError.classify` instead of the free function) — the only visible change is that callers catching `except JunoError` still catch it (since `VertexAPIError` subclasses `JunoError`), and anything that specifically wants to distinguish "this came from Vertex" can now `except VertexAPIError` instead of checking `.original` manually. No existing call site does this distinction today, so this is additive, not breaking.

---

### 4h. `models/errors.py` → `models/api_response.py` rename

**New name:** `models/api_response.py`. Rationale: the module's two real exports are `ApiResponse` and the things `ApiResponse` is built from (`ErrorDetail`, `StatusEnum`); "api_response" names the actual content instead of colliding with the unrelated `errors/` package name. No file content changes — pure rename, no logic touched.

**Every import site to update** (verified via grep, all in `backend/`):

| File | Old | New |
|---|---|---|
| `errors/exceptions.py:26` | `from models.errors import ApiResponse, ErrorDetail, StatusEnum` | `from models.api_response import ApiResponse, ErrorDetail, StatusEnum` |
| `models/__init__.py:4` | `from .errors import ApiResponse, ErrorDetail, StatusEnum` | `from .api_response import ApiResponse, ErrorDetail, StatusEnum` |
| `models/job.py:10` | `from .errors import ErrorDetail, StatusEnum` | `from .api_response import ErrorDetail, StatusEnum` |
| `tests/errors/test_exceptions.py:3` | `from models.errors import ApiResponse, StatusEnum` | `from models.api_response import ApiResponse, StatusEnum` |
| `tests/models/test_errors.py` (5 occurrences: lines 3, 5, 20, 29, 36) | `from models.errors import ...` | `from models.api_response import ...` |
| `tests/models/test_job.py:7` | `from models.errors import StatusEnum, ErrorDetail` | `from models.api_response import StatusEnum, ErrorDetail` |

**Test file rename:** `tests/models/test_errors.py` → `tests/models/test_api_response.py`, to match the source file rename and avoid the same `errors.py`-vs-`errors/` ambiguity in the test tree. Confirmed by content inspection: every test in this file (`test_api_response_error_round_trip`, `test_api_response_path_is_optional`, `test_api_response_extra_field_raises`, `test_status_enum_values`) already exercises `ApiResponse`/`ErrorDetail`/`StatusEnum` only — the test names themselves already say `test_api_response_*`, so the file name is simply catching up to content that already moved on. This rename is now locked (see §9 Q8) and is part of this PRD's scope, not deferred to the implementation task's discretion.

---

### 4i. `routes/worker.py` — Athena import update (SHARED FILE WITH SP13 — see §9)

**Before** (line 231, inside the `elif source_kind in ("athena_encounter", "athena_clinical_doc"):` branch starting at line 230):
```python
            elif source_kind in ("athena_encounter", "athena_clinical_doc"):
                from services.external_api import athena_client, AthenaAPIError
```

**After:**
```python
            elif source_kind in ("athena_encounter", "athena_clinical_doc"):
                from services.external_api import athena_client
                from errors import AthenaAPIError
```

No other line in this block changes — `except AthenaAPIError as exc:` (line 245) and the `build_error_data_from_exc(exc)` call (line 246) are unaffected; `AthenaAPIError` still has `.status_code` and is still a `JunoError`.

The top-level import at `routes/worker.py:28` (`from errors import ErrorCode, build_error_data, build_error_data_from_exc`) is untouched — `AthenaAPIError` is imported locally inside the `elif` branch (matching the existing local-import style for `athena_client`), not added to the top-level import block.

---

### 4j. `services/external_api/__init__.py` — stop re-exporting `AthenaAPIError`

**Before:**
```python
"""services/external_api — Juno's outbound HTTP clients for external APIs."""
from .athena_client import athena_client, AthenaClient
from models.external_api.athena_errors import AthenaAPIError

__all__ = ["athena_client", "AthenaClient", "AthenaAPIError"]
```

**After:**
```python
"""services/external_api — Juno's outbound HTTP clients for external APIs."""
from .athena_client import athena_client, AthenaClient

__all__ = ["athena_client", "AthenaClient"]
```

**Decision:** do not re-export `AthenaAPIError` from `services/external_api/` anymore. It now lives in `errors/`, which is already the canonical place every other error type is imported from; re-exporting it from `services/external_api/` would just recreate a second "where do I import this from" path. Every consumer (`routes/worker.py`, `tests/services/external_api/test_athena_client.py`) switches to `from errors import AthenaAPIError`.

---

### 4k. `models/external_api/__init__.py` — drop `AthenaAPIError`, keep models

**Before:**
```python
from .athena_errors import AthenaAPIError
from .athena_models import (
    AthenaTokenRequest, AthenaTokenResponse, AthenaEncounterSummaryRequest,
    AthenaEncounterSummaryResponse, AthenaClinicalDocumentMeta,
    AthenaClinicalDocumentListRequest, AthenaClinicalDocumentListResponse,
    AthenaClinicalDocumentContentRequest, AthenaClinicalDocumentContentResponse,
    AthenaPushDocumentRequest, AthenaPushDocumentResponse,
)
__all__ = ["AthenaAPIError", "AthenaTokenRequest", ...]
```

**After:**
```python
"""External API model re-exports."""
from .athena_models import (
    AthenaTokenRequest, AthenaTokenResponse, AthenaEncounterSummaryRequest,
    AthenaEncounterSummaryResponse, AthenaClinicalDocumentMeta,
    AthenaClinicalDocumentListRequest, AthenaClinicalDocumentListResponse,
    AthenaClinicalDocumentContentRequest, AthenaClinicalDocumentContentResponse,
    AthenaPushDocumentRequest, AthenaPushDocumentResponse,
)
__all__ = [
    "AthenaTokenRequest", "AthenaTokenResponse", "AthenaEncounterSummaryRequest",
    "AthenaEncounterSummaryResponse", "AthenaClinicalDocumentMeta",
    "AthenaClinicalDocumentListRequest", "AthenaClinicalDocumentListResponse",
    "AthenaClinicalDocumentContentRequest", "AthenaClinicalDocumentContentResponse",
    "AthenaPushDocumentRequest", "AthenaPushDocumentResponse",
]
```

---

### 4l. File-count rule applied — `services/external_api/` and `models/external_api/`

**`services/external_api/` file count after this PRD: 1** (`athena_client.py`; `__init__.py` doesn't count as a "content" file under the rule). **Stays flat** — no `services/external_api/athena/` subfolder. No change to this layer's directory shape; only `athena_client.py`'s two import lines change (§4f) and `__init__.py` drops one re-export (§4j).

**`models/external_api/` file count after this PRD: 1** (`athena_models.py`; `athena_errors.py` is moving out to `errors/`, so it no longer counts here). **Stays flat** — no `models/external_api/athena/` subfolder, file keeps its current name `athena_models.py` (no rename needed; it's already correctly named and is the only file in the directory).

**Decision: `AthenaEncounterSelection` / `AthenaClinicalDocSelection` (`models/batch_requests.py:15,30`) do NOT move into `models/external_api/`.**

Reasoning: these two models are not Athena *external API wire contracts* (they don't represent anything Athena's REST API sends or receives) — they are part of Juno's own **batch-job request schema**, just happening to carry Athena-specific identifiers (`athena_practice_id`, `athena_encounter_id`, etc.). They are defined together with `GcsDatasetSelection` and combined into one discriminated union for a single purpose: validating `POST /care_plan/batch/jobs` request bodies:

```python
Selection = Annotated[
    Union[AthenaEncounterSelection, AthenaClinicalDocSelection, GcsDatasetSelection],
    Field(discriminator="input_source_kind"),
]
```

Moving two of the three union members into `models/external_api/` while leaving `GcsDatasetSelection` in `models/batch_requests.py` would split one cohesive, jointly-reviewed discriminated union across two files for no benefit — `routes/batch_jobs.py` would need to import from two places to reconstruct one schema concept, and the file that currently fully describes "what a batch job selection can look like" would no longer fully describe it. The "1 file → flat" outcome in `models/external_api/` is correct either way (even if these moved, it would only become 2 files, which by the rule would mean nesting `models/external_api/athena/` — see below for what was considered and rejected).

**What was considered and rejected:** moving the two selection models into `models/external_api/athena_selections.py`, which would make this layer's file count 2 (`athena_models.py` + `athena_selections.py`) and, by the locked rule, trigger nesting into `models/external_api/athena/{models.py,selections.py}`. Rejected because (a) it fragments the `Selection` union as described above, and (b) the rule's intent (per its own worked example) is to avoid namespace collisions once *multiple external APIs* share a layer — `models/external_api/` is 100% Athena today regardless of this decision, so there is no disambiguation need yet. If a second EHR integration is ever added, *that* is the right trigger to introduce the `athena/` subfolder for both files at once, not this PRD.

**No changes needed to `models/batch_requests.py` content** as a result of this PRD — `AthenaEncounterSelection` and `AthenaClinicalDocSelection` stay exactly where they are, unchanged. `routes/batch_jobs.py`'s existing import (`from models.batch_requests import BatchJobsRequest, AthenaEncounterSelection, AthenaClinicalDocSelection, GcsDatasetSelection`) is untouched.

---

### 4m. Final directory trees

```
backend/errors/
  __init__.py          # updated re-exports (§4e)
  codes.py             # UNCHANGED
  exceptions.py        # classify_vertex_exception removed; _classify_exc updated (§4d)
  athena_errors.py      # NEW — AthenaAPIError(JunoError) + classify() (moved + fixed, §4b)
  vertex_errors.py      # NEW — VertexAPIError(JunoError) + classify() (§4c)

backend/services/external_api/
  __init__.py          # drops AthenaAPIError re-export (§4j)
  athena_client.py      # import line + _get() simplification only (§4f)

backend/models/external_api/
  __init__.py          # drops AthenaAPIError export (§4k)
  athena_models.py      # UNCHANGED content
  # athena_errors.py — DELETED (moved to errors/)

backend/models/
  api_response.py        # RENAMED from errors.py, content unchanged (§4h)
  job.py               # import line only (§4h)
  __init__.py          # import line only (§4h)
  batch_requests.py     # UNCHANGED (§4l)
```

---

## 5. API Change Summary

No HTTP wire-contract changes. This is an internal Python refactor:

| Change | Visible to HTTP callers? | Visible to Python importers? |
|---|---|---|
| `AthenaAPIError` moves to `errors/athena_errors.py` | No | Yes — import path changes (§4i, §4j) |
| `AthenaAPIError` default classification fixed (429 → rate-limit, by construction) | Yes — a 429 against an Athena-backed job now correctly reports `ATHENA_RATE_LIMIT_ERROR` / `retryable=true` to the frontend instead of being silently merged into the path that already worked correctly in production (the retry loop), so end-user-visible behavior is unchanged in the one path that matters (`athena_client.py`); the fix's externally-visible value is making it impossible for a *future* call site to regress this silently | Yes — `AthenaAPIError(429, body)` without `code=` now returns a different `error_code` than before |
| `VertexAPIError` introduced | No | Yes — new importable symbol; `classify_vertex_exception` removed |
| `models/errors.py` → `models/api_response.py` | No | Yes — import path changes (§4h) |
| `services/external_api/__init__.py` drops `AthenaAPIError` re-export | No | Yes — `from services.external_api import AthenaAPIError` breaks; use `from errors import AthenaAPIError` |

---

## 6. Frontend Change Summary

N/A. Entirely backend Python; no TypeScript, no HTTP contract change, no new/removed JSON fields in `ApiResponse`/`ErrorDetail`.

---

## 7. Testing

This section describes testing **strategy**, not a task list (a separate TASKS.md pass will enumerate concrete test edits).

**1. Lock in the bug fix, not the bug.** `tests/errors/test_exceptions.py::test_athena_api_error_is_juno_error` currently asserts `AthenaAPIError(429, "rate limited").error_code == ErrorCode.ATHENA_API_ERROR`. This assertion must be corrected to `ErrorCode.ATHENA_RATE_LIMIT_ERROR` as part of this work — leaving it as-is would mean the test suite continues to certify the bug as correct behavior. Add a second case alongside it asserting a non-429, non-special status (e.g. 503) still defaults to `ATHENA_API_ERROR`, and a third asserting `AthenaAPIError.classify(429) == ErrorCode.ATHENA_RATE_LIMIT_ERROR` / `AthenaAPIError.classify(500) == ErrorCode.ATHENA_API_ERROR` directly against the classmethod.

**2. `VertexAPIError.classify` parity test.** Port the existing (implicit, via `classify_vertex_exception`) type-map coverage into a direct test of `VertexAPIError.classify(exc)` for each `google.api_core.exceptions.*` type listed in §4c, plus the `ImportError` fallback path and the "unmapped exception type → UNKNOWN_ERROR" path.

**3. `utils/llm.py` Vertex-failure path.** Existing tests that simulate a `GoogleAPICallError` from `generate_content` and assert the resulting `JunoError.error_code` should continue to pass unchanged (since `VertexAPIError` is a `JunoError` and carries the same `error_code`); add one assertion that the raised exception is specifically `isinstance(exc, VertexAPIError)`.

**4. `athena_client.py` retry-loop regression coverage.** `tests/services/external_api/test_athena_client.py::test_get_raises_rate_limit_error_code_after_exhausted_retries` and `test_get_raises_athena_api_error_on_non_200` (503 case) already exist and should continue to pass unchanged after the `_get()` simplification in §4f — they test observable behavior (the resulting `error_code`), not the presence/absence of an explicit `code=` kwarg, so the centralization should be invisible to them. Run them before and after the change to confirm.

**5. Import-path sweep.** After the moves in §4b/§4h/§4j/§4k, run a full-repo import check (e.g. `python -c "import errors, models, services.external_api"` plus the existing test suite) to catch any missed import-site update — the grep-derived list in §4 is believed exhaustive but should be re-verified mechanically (e.g. `grep -rn "models.errors\|models\.athena_errors\|services.external_api import.*AthenaAPIError\|classify_vertex_exception"`) as a final check before considering the migration complete.

**6. `models/external_api/__init__.py` / `services/external_api/__init__.py` export-surface tests**, if any exist asserting `__all__` contents, need updating to drop `AthenaAPIError`.

**7. File move for tests.** `tests/models/test_errors.py` is renamed to `tests/models/test_api_response.py` (§4h, §9 Q8) — update accordingly; no behavior change, pure path rename.

---

## 8. Manual Intervention Required From You

**None.** Verified:
- `backend/cloudbuild.yaml` and `.github/workflows/ci.yml` contain no references to any file path touched by this PRD (`models/errors.py`, `models/external_api/*`, `services/external_api/*`, `errors/*`) — grepped, zero hits.
- No environment variables, secrets, GCP console steps, or Firestore/storage migrations are implicated — this is a pure Python module-reorganization with no schema or infra surface.

---

## 9. Open Questions & Decisions

| # | Status | Item |
|---|---|---|
| Q1 | [RESOLVED] | `AthenaAPIError` → `errors/athena_errors.py`; `VertexAPIError` (new) → `errors/vertex_errors.py`. Both subclass `JunoError` and expose `classify()` as a classmethod. |
| Q2 | [RESOLVED] | New Vertex/Google error class is named `VertexAPIError`, not `GoogleAPIError` — see §4c naming rationale. Revisit only if a second non-Vertex Google API (GCS/Firestore exception classification) is added later; that would be the natural trigger for a broader `GoogleAPIError` umbrella, not this PRD. |
| Q3 | [RESOLVED] | The 429-mapping bug is real but lives in `AthenaAPIError.__init__`'s flat default parameter, not in `athena_client.py`'s retry loop (which is currently correct only because every call site manually overrides). Proven by `tests/errors/test_exceptions.py::test_athena_api_error_is_juno_error`, which currently asserts the buggy default as correct. Fixed by making the constructor call `classify(status_code)` automatically when `code` is omitted. |
| Q4 | [RESOLVED] | `models/errors.py` renamed to `models/api_response.py`. All 6 import-site groups enumerated in §4h. |
| Q5 | [RESOLVED] | `AthenaEncounterSelection`/`AthenaClinicalDocSelection` stay in `models/batch_requests.py` — not moved into `models/external_api/`. See §4l for full reasoning (avoids fragmenting the `Selection` discriminated union; `models/external_api/` ends up flat at 1 file either way). |
| Q6 | [RESOLVED] | `services/external_api/` (1 file: `athena_client.py`) and `models/external_api/` (1 file: `athena_models.py`) both stay flat — no `athena/` subfolder in either layer, per the locked file-count rule. |
| Q7 | [RESOLVED] | `services/external_api/__init__.py` and `models/external_api/__init__.py` both stop re-exporting `AthenaAPIError` once it moves to `errors/`; all consumers import it from `errors` directly, matching every other error type. |
| Q8 | [RESOLVED: rename tests/models/test_errors.py to tests/models/test_api_response.py; the file's own test names already say `test_api_response_*` and it tests only ApiResponse/ErrorDetail/StatusEnum, so the filename should match the production module rename (§4h) and stop colliding with `errors/`.] | `tests/models/test_errors.py` → `tests/models/test_api_response.py` rename, alongside the import-path update in the same file (§4h). |
| Q9 | [DEFERRED] | `ErrorCode.ATHENA_PATIENT_NOT_FOUND` remains unused after this PRD (confirmed out of scope) — wiring it up to a real patient-lookup-failure path is a future feature, not a cleanup item. |
| Q10 | **SP13 coordination — not a question, a heads-up.** | This PRD changes exactly one line-group in `routes/worker.py`: the local import inside the `elif source_kind in ("athena_encounter", "athena_clinical_doc"):` branch (current line 231: `from services.external_api import athena_client, AthenaAPIError` → split into two lines, §4i). Nothing else in `worker.py` changes — not the `except AthenaAPIError as exc:` block, not the top-level `from errors import ErrorCode, build_error_data, build_error_data_from_exc` import, not any surrounding logic. SP13 (routes/utils/services boundary cleanup), which also touches `routes/worker.py`, should treat this one import line as already-changed when sequencing its own edits to this file, to avoid a merge clobber. |

---
