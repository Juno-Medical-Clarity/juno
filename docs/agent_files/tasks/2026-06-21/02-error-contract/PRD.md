# PRD: Error Contract (SP2)

Phase 1, no dependencies. Defines a single, well-documented error shape used by every backend
endpoint and Firestore job doc. Every error has a code from a central registry, is logged,
carries a requestId, and the frontend understands and displays structured errors.

## 1. Problem

The backend emits errors in at least four incompatible shapes today:

1. **SSE pipeline errors** (`care_plan.py`, `batch.py`): `{"step": "error", "error": "..."}` —
   a string, no code, no requestId, not logged in a structured way.
2. **REST jsonify errors** (most route handlers): `jsonify({"error": "..."})` with varying HTTP
   status codes — a string, no code, no requestId.
3. **verify_firebase_token decorator** (`utils/firebase.py`): `jsonify({"error": "..."})` or
   `jsonify({"error": "...", "details": "..."})` with HTTP 401 — slightly richer but still ad hoc.
4. **Global Flask error handlers** (`app.py`): `jsonify({"error": "Endpoint not found"})` at 404
   and 500 — not structured, not logged.
5. **get_owned_doc_or_403** (`utils/firebase.py`): `jsonify({"error": "Not found"})` at 404 and
   `jsonify({"error": "Forbidden"})` at 403 — point returns in a utility function.

The frontend (`CarePlanPage.tsx`) reads the SSE error string raw (`event.error`) and displays it
directly. REST errors are caught only via `!res.ok`, discarding the body.

SP1 (Firebase Async Jobs) needs a well-defined `error_data` field shape for Firestore job docs —
which workers write without an HTTP request context. SP2 provides that shape.

## 2. Goals

1. Define one Pydantic `ApiResponse` model (backend) that is the single source of truth for the
   wire shape of every success and error response.
2. Define a central `ErrorCode` enum — every error code used anywhere in the codebase is listed
   here with a default message and a details template.
3. Provide a `make_error_response(code, path, details_vars, requestId)` helper that builds an
   `ApiResponse`, logs it structurally, and is callable from route handlers, the auth decorator,
   and global error handlers.
4. Replace all existing error patterns in: `care_plan.py`, `batch.py`, `grading.py`,
   `saved_outputs.py`, `utils/firebase.py` (decorator + `get_owned_doc_or_403`), and `app.py`
   global handlers.
5. Document the `ErrorDetail` shape as the SP1 interface contract for `error_data` in Firestore
   job docs, and make it usable without an HTTP request context.
6. Update the frontend `apiClient.ts` to parse structured error responses. Define a TypeScript
   `ApiError` type. Update `CarePlanPage.tsx` error display to use the structured shape.
7. Ship unit tests: every error code has message + details template, `make_error_response` output
   matches the contract, `ApiResponse` round-trips through Pydantic.

## 3. Non-Goals

- Not removing SSE from `care_plan.py` or `batch.py` — that is SP1. SP2 replaces the SSE
  `{"step":"error","error":"..."}` payload shape with `{"step":"error","error_data":{...}}` (see
  §4.3 transition note) so that the SSE channel already uses the structured shape when SP1 removes
  SSE entirely.
- Not adding job-level Firestore documents or Cloud Tasks — that is SP1.
- Not changing how grading scores are computed or displayed — that is SP5.
- Not wiring tests into CI — the test authoring is in scope; CI wiring is not.
- Not adding i18n or user-facing localisation of error messages.
- Not adding rate-limiting error codes beyond what already exists in the route handlers.

## 4. Architecture Decisions

### 4.1 `backend/models/errors.py` — Pydantic models for the wire shape

New file. All models are `JsonModel` subclasses (inheriting `extra="forbid"` and `to_dict`).

```python
# backend/models/errors.py
from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import Field
from .base import JsonModel


class StatusEnum(str, Enum):
    error       = "error"
    success     = "success"
    not_started = "not_started"
    processing  = "processing"
    completed   = "completed"


class ErrorDetail(JsonModel):
    """Structured error payload.

    Intentionally usable without an HTTP request context:
    - `path` is Optional (workers writing Firestore job docs have no path).
    - `timestamp` is an ISO-8601 UTC string; callers use datetime.now(timezone.utc).isoformat().
    - `code` is always a string (ErrorCode.value), not the enum, so it is JSON-serializable
      without extra config and safe to store in Firestore.
    """
    code: str                        # ErrorCode.value, e.g. "RESOURCE_NOT_FOUND"
    message: str                     # human-readable summary
    details: str = ""                # specific detail, may use template vars
    timestamp: str                   # ISO-8601 UTC string
    path: str | None = None          # request path; None when called from a worker


class ApiResponse(JsonModel):
    """Top-level envelope for every HTTP response.

    Success:  ApiResponse(status="success", data={...})
    Error:    ApiResponse(status="error", error=ErrorDetail(...))
    The HTTP status code lives on the HTTP layer, not duplicated here.
    """
    status: StatusEnum
    data: dict[str, Any] | None = None
    error: ErrorDetail | None = None
    requestId: str | None = None
```

**Design note on `data` typing.** `dict[str, Any]` is the pragmatic choice: success payloads are
built from `.to_dict()` results that are already `dict`, and a fully generic typed `data` would
require union types for every endpoint's response shape. SP5 (frontend) owns typed response shapes;
the backend wire contract only guarantees `{"status":"success","data":{...}}`.

**Why `code: str` not `code: ErrorCode`.** `ErrorCode` is defined in `error_codes.py` (§4.2), not
`errors.py`, to avoid a circular import (the helper in `error_codes.py` imports `ApiResponse`).
Storing the `.value` string directly keeps `ErrorDetail` self-contained, importable by SP1's
worker code, and serializable to Firestore without custom Pydantic config.

### 4.2 `backend/utils/error_codes.py` — error code registry and make_error_response helper

New file. Defines `ErrorCode` as a `StrEnum` (Python 3.11+; the backend already runs 3.12 per
Cloud Run) so that each member's `.value` equals its name string.

```python
# backend/utils/error_codes.py
from __future__ import annotations
import logging
from datetime import datetime, timezone
from enum import StrEnum
from flask import g

from models.errors import ApiResponse, ErrorDetail, StatusEnum

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    # Auth
    UNAUTHORIZED            = "UNAUTHORIZED"
    MISSING_AUTH_HEADER     = "MISSING_AUTH_HEADER"
    MALFORMED_AUTH_HEADER   = "MALFORMED_AUTH_HEADER"
    # Resource
    RESOURCE_NOT_FOUND      = "RESOURCE_NOT_FOUND"
    RESOURCE_FORBIDDEN      = "RESOURCE_FORBIDDEN"
    # Input
    INPUT_VALIDATION_ERROR  = "INPUT_VALIDATION_ERROR"
    INPUT_EMPTY             = "INPUT_EMPTY"
    UNSUPPORTED_FILE_TYPE   = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE          = "FILE_TOO_LARGE"
    UNKNOWN_VERSION         = "UNKNOWN_VERSION"
    # Pipeline / processing
    PIPELINE_ERROR          = "PIPELINE_ERROR"
    PIPELINE_INIT_ERROR     = "PIPELINE_INIT_ERROR"
    SIMPLIFICATION_FAILED   = "SIMPLIFICATION_FAILED"
    STRUCTURING_FAILED      = "STRUCTURING_FAILED"
    # Timeout
    TIMEOUT                 = "TIMEOUT"
    # Batch
    BATCH_TOO_LARGE         = "BATCH_TOO_LARGE"
    BATCH_INVALID_SELECTION = "BATCH_INVALID_SELECTION"
    DATASET_NOT_FOUND       = "DATASET_NOT_FOUND"
    # Grading / saving
    NO_SOURCE_TEXT          = "NO_SOURCE_TEXT"
    SAVE_FAILED             = "SAVE_FAILED"
    PDF_URL_UNAVAILABLE     = "PDF_URL_UNAVAILABLE"
    # General
    INTERNAL_ERROR          = "INTERNAL_ERROR"
    ENDPOINT_NOT_FOUND      = "ENDPOINT_NOT_FOUND"


# Registry: each code maps to (default_message, details_template).
# details_template uses {placeholder} vars that make_error_response fills in via .format(**details_vars).
_REGISTRY: dict[ErrorCode, tuple[str, str]] = {
    ErrorCode.UNAUTHORIZED:            ("Authentication failed",                        "Invalid or expired token: {detail}"),
    ErrorCode.MISSING_AUTH_HEADER:     ("No authorization header",                      "Request must include an Authorization: Bearer <token> header"),
    ErrorCode.MALFORMED_AUTH_HEADER:   ("Malformed Authorization header",               "Expected format: Authorization: Bearer <token>"),
    ErrorCode.RESOURCE_NOT_FOUND:      ("Resource not found",                           "{collection} document {doc_id} does not exist"),
    ErrorCode.RESOURCE_FORBIDDEN:      ("Access denied",                                "You do not own {collection} document {doc_id}"),
    ErrorCode.INPUT_VALIDATION_ERROR:  ("Invalid request input",                        "{field}: {reason}"),
    ErrorCode.INPUT_EMPTY:             ("Input appears to be empty or unreadable",      "Extracted text was empty after parsing"),
    ErrorCode.UNSUPPORTED_FILE_TYPE:   ("Unsupported file type",                        "File must be PDF, TXT, or DOCX; got {ext}"),
    ErrorCode.FILE_TOO_LARGE:          ("File exceeds size limit",                      "File size {size_mb}MB exceeds {limit_mb}MB limit"),
    ErrorCode.UNKNOWN_VERSION:         ("Unknown pipeline version",                     "Version {version} is not supported. Allowed: {allowed}"),
    ErrorCode.PIPELINE_ERROR:          ("Pipeline error",                               "Unexpected error during processing: {detail}"),
    ErrorCode.PIPELINE_INIT_ERROR:     ("Pipeline initialization failed",               "Could not initialize pipeline: {detail}"),
    ErrorCode.SIMPLIFICATION_FAILED:   ("Simplification step failed",                   "LLM simplification error: {detail}"),
    ErrorCode.STRUCTURING_FAILED:      ("Structuring step failed",                      "LLM structuring error: {detail}"),
    ErrorCode.TIMEOUT:                 ("Request timed out",                            "Operation exceeded time limit"),
    ErrorCode.BATCH_TOO_LARGE:         ("Batch request too large",                      "Requested {count} runs; maximum is {max_runs}"),
    ErrorCode.BATCH_INVALID_SELECTION: ("Invalid batch selection",                      "{detail}"),
    ErrorCode.DATASET_NOT_FOUND:       ("Dataset not found",                            "Dataset {group}/{input_id} does not exist"),
    ErrorCode.NO_SOURCE_TEXT:          ("No source text available",                     "Saved output {saved_id} has no raw text to re-grade"),
    ErrorCode.SAVE_FAILED:             ("Failed to save output",                        "Firestore write failed: {detail}"),
    ErrorCode.PDF_URL_UNAVAILABLE:     ("No input PDF stored for this output",          "Output {doc_id} has no associated PDF"),
    ErrorCode.INTERNAL_ERROR:          ("Internal server error",                        "An unexpected error occurred"),
    ErrorCode.ENDPOINT_NOT_FOUND:      ("Endpoint not found",                           "No route matches {method} {path}"),
}


def make_error_response(
    code: ErrorCode,
    path: str | None = None,
    details_vars: dict | None = None,
    requestId: str | None = None,
) -> ApiResponse:
    """Build a structured ApiResponse for an error and log it.

    Args:
        code:         ErrorCode member identifying the error type.
        path:         Request path (e.g. "/api/v1/care_plan/jobs/abc"). Pass None
                      when called outside an HTTP context (e.g. a Cloud Tasks worker).
        details_vars: Dict of {placeholder: value} pairs to fill the details template.
                      Unknown keys are silently ignored (uses str.format_map with a
                      SafeDict to avoid KeyError on partial templates).
        requestId:    Correlation ID. If None, falls back to g.session_id (when inside
                      a Flask request context); stays None if neither is available.
    Returns:
        An ApiResponse with status="error" and a fully populated ErrorDetail.
    """
    message, details_template = _REGISTRY.get(code, ("Unknown error", "{detail}"))
    details = _safe_format(details_template, details_vars or {})

    if requestId is None:
        try:
            requestId = getattr(g, "session_id", None)
        except RuntimeError:
            requestId = None  # no Flask app context (worker environment)

    timestamp = datetime.now(timezone.utc).isoformat()

    error_detail = ErrorDetail(
        code=code.value,
        message=message,
        details=details,
        timestamp=timestamp,
        path=path,
    )

    # Structured log — every field is a first-class key so Cloud Logging can filter on them.
    logger.error(
        "error_response",
        extra={
            "error_code": code.value,
            "error_message": message,
            "error_details": details,
            "request_id": requestId,
            "path": path,
            "timestamp": timestamp,
        },
    )

    return ApiResponse(
        status=StatusEnum.error,
        error=error_detail,
        requestId=requestId,
    )


class _SafeDict(dict):
    """Substitute missing keys with their placeholder text to avoid KeyError."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _safe_format(template: str, vars: dict) -> str:
    return template.format_map(_SafeDict(vars))
```

**requestId availability in `verify_firebase_token`.** The `@before_request` hook in `app.py`
sets `g.session_id` unconditionally (from `X-Session-Id` header or a generated UUID) before any
route handler or decorator runs. `verify_firebase_token` therefore always has a valid
`g.session_id` when called inside a Flask request context — confirmed by reading `app.py:54-73`.
The `try/except RuntimeError` guard in `make_error_response` is a defensive backstop for
worker/test contexts only.

**Logging fields.** Every structured error log emits: `error_code`, `error_message`,
`error_details`, `request_id`, `path`, `timestamp`. The `SessionIdFilter` in `logging_config.py`
auto-injects `session_id` from `g.session_id`, so logs are automatically correlated to the
session without extra work in `make_error_response`.

### 4.3 SSE error transition — what replaces `{"step":"error","error":"..."}`

SP1 removes SSE entirely from `care_plan.py` and `batch.py`. SP2 ships before SP1. To avoid the
frontend needing to handle two shapes during the SP1 window, SP2 changes the SSE error payload to:

```json
{ "step": "error", "error_data": { "code": "...", "message": "...", "details": "...", "timestamp": "...", "path": null, "requestId": "..." } }
```

The top-level `"error"` string key is replaced by `"error_data"` carrying an `ErrorDetail` dict.
SP2 must also update the frontend SSE parser in `CarePlanPage.tsx` to read `event.error_data`
instead of `event.error`. When SP1 lands it removes the SSE path entirely; the frontend switch to
Firestore polling makes the SSE event format moot.

Helper for SSE route use:

```python
# inside care_plan.py and batch.py
def _sse_error(code: ErrorCode, path: str, details_vars: dict | None = None) -> str:
    resp = make_error_response(code, path=path, details_vars=details_vars)
    return _sse({"step": "error", "error_data": resp.error.to_dict()})
```

This keeps the SSE channel intact for the transition window while adopting the structured shape.

### 4.4 Replace error patterns — endpoint-by-endpoint

**Old → new table (all endpoints)**

| Location | Old pattern | New pattern |
|---|---|---|
| `verify_firebase_token` (no header) | `jsonify({"error":"No authorization header"}), 401` | `make_error_response(MISSING_AUTH_HEADER, path).to_dict(), 401` |
| `verify_firebase_token` (malformed) | `jsonify({"error":"Malformed Authorization header"}), 401` | `make_error_response(MALFORMED_AUTH_HEADER, path).to_dict(), 401` |
| `verify_firebase_token` (invalid token) | `jsonify({"error":"Invalid or expired token","details":str(e)}), 401` | `make_error_response(UNAUTHORIZED, path, {"detail":str(e)}).to_dict(), 401` |
| `get_owned_doc_or_403` (not found) | `jsonify({"error":"Not found"}), 404` | `make_error_response(RESOURCE_NOT_FOUND, path, {"collection":collection,"doc_id":doc_id}).to_dict(), 404` |
| `get_owned_doc_or_403` (forbidden) | `jsonify({"error":"Forbidden"}), 403` | `make_error_response(RESOURCE_FORBIDDEN, path, {"collection":collection,"doc_id":doc_id}).to_dict(), 403` |
| `care_plan.py` version check | `{"error": f"Unknown version..."}, 400` | `make_error_response(UNKNOWN_VERSION, ...).to_dict(), 400` |
| `care_plan.py` SSE: input error | `_sse({"step":"error","error":"..."})` | `_sse_error(INPUT_VALIDATION_ERROR, "/care_plan", ...)` |
| `care_plan.py` SSE: empty input | `_sse({"step":"error","error":"Input appears..."})` | `_sse_error(INPUT_EMPTY, "/care_plan")` |
| `care_plan.py` SSE: simplify fail | `_sse({"step":"error","error":"Simplification failed:..."})` | `_sse_error(SIMPLIFICATION_FAILED, "/care_plan", {"detail":...})` |
| `care_plan.py` SSE: structure fail | `_sse({"step":"error","error":"Structuring failed:..."})` | `_sse_error(STRUCTURING_FAILED, "/care_plan", {"detail":...})` |
| `care_plan.py` SSE: pipeline init fail | `_sse({"step":"error","error":"Failed to initialize pipeline:..."})` | `_sse_error(PIPELINE_INIT_ERROR, "/care_plan", {"detail":...})` |
| `care_plan.py` SSE: unexpected error | `_sse({"step":"error","error":"Pipeline error:..."})` | `_sse_error(PIPELINE_ERROR, "/care_plan", {"detail":...})` |
| `batch.py` body not JSON object | `_sse({"step":"error","error":"Request body..."})` | `_sse_error(INPUT_VALIDATION_ERROR, "/care_plan/batch", {"field":"body","reason":"..."})` |
| `batch.py` unknown version | `_sse({"step":"error","error":"Unknown version..."})` | `_sse_error(UNKNOWN_VERSION, "/care_plan/batch", {"version":..., "allowed":...})` |
| `batch.py` no selections | `_sse({"step":"error","error":"Request must include selections"})` | `_sse_error(INPUT_VALIDATION_ERROR, "/care_plan/batch", {"field":"selections","reason":"..."})` |
| `batch.py` too many runs | `_sse({"step":"error","error":"Batch request exceeds..."})` | `_sse_error(BATCH_TOO_LARGE, "/care_plan/batch", {"count":total,"max_runs":MAX_BATCH_RUNS})` |
| `batch.py` FileNotFoundError/ValueError | `_sse({"step":"error","error":str(exc)})` | `_sse_error(BATCH_INVALID_SELECTION, "/care_plan/batch", {"detail":str(exc)})` |
| `batch.py` unexpected error | `_sse({"step":"error","error":"Batch pipeline error:..."})` | `_sse_error(PIPELINE_ERROR, "/care_plan/batch", {"detail":str(exc)})` |
| `grading.py` no source text | `jsonify({"error":"No source text..."}), 400` | `make_error_response(NO_SOURCE_TEXT, "/care_plan/grade", {"saved_id":saved_id}).to_dict(), 400` |
| `grading.py` no text in body | `jsonify({"error":"Provide either..."}), 400` | `make_error_response(INPUT_VALIDATION_ERROR, "/care_plan/grade", {"field":"text","reason":"..."}).to_dict(), 400` |
| `saved_outputs.py` rename: missing name | `jsonify({"error":"name is required"}), 400` | `make_error_response(INPUT_VALIDATION_ERROR, f"/care_plan/saved/{doc_id}", {"field":"name","reason":"required"}).to_dict(), 400` |
| `saved_outputs.py` rename: name too long | `jsonify({"error":"name too long..."}), 400` | `make_error_response(INPUT_VALIDATION_ERROR, f"/care_plan/saved/{doc_id}", {"field":"name","reason":"max 200 chars"}).to_dict(), 400` |
| `saved_outputs.py` no PDF stored | `jsonify({"error":"No input PDF..."}), 404` | `make_error_response(PDF_URL_UNAVAILABLE, f"/care_plan/saved/{doc_id}/input-pdf-url", {"doc_id":doc_id}).to_dict(), 404` |
| `saved_outputs.py` PDF URL failed | `jsonify({"error":f"Could not generate URL: {e}"}), 500` | `make_error_response(INTERNAL_ERROR, ...).to_dict(), 500` |
| `app.py` 404 handler | `jsonify({"error":"Endpoint not found"}), 404` | `make_error_response(ENDPOINT_NOT_FOUND, request.path, {"method":request.method,"path":request.path}).to_dict(), 404` |
| `app.py` 500 handler | `jsonify({"error":"Internal server error"}), 500` | `make_error_response(INTERNAL_ERROR, request.path).to_dict(), 500` |

**`get_owned_doc_or_403` path argument.** The helper has no access to `request.path` today. The
path must be passed in by callers, or the helper must be changed to accept it. Resolution: add an
optional `path: str | None = None` parameter to `get_owned_doc_or_403`. All call-sites pass
`request.path` explicitly. This is a clean change with no behavioral impact on callers that omit
it.

**Success responses.** Route handlers that currently return `jsonify({"outputs": ...})` or similar
do NOT need to be wrapped in `ApiResponse(status="success", ...)`. The success path is a lower
priority for SP2 — it is in the Non-Goals boundary unless the owner specifically wants it. Routes
continue to return their existing success payloads. SP2 focuses entirely on the error shape. This
avoids a large sweeping change to every route's success path and lets SP1 and SP3 adopt
`ApiResponse` for new endpoints they create.

> [RESOLVED: Success responses are out of scope for SP2. Only error responses adopt ApiResponse.
> New endpoints created by SP1 will return ApiResponse for both success and error from day one.]

### 4.5 SP1 interface contract — `ErrorDetail` as Firestore `error_data`

SP1 (Firebase Async Jobs) writes job documents to Firestore. When a job fails, the worker writes
an `error_data` field. SP2 defines the shape that field must use:

```
Firestore job document (owned by SP1):
{
  "status": "error",           // StatusEnum value
  "error_data": {              // ErrorDetail.to_dict() output
    "code": "PIPELINE_ERROR",
    "message": "Pipeline error",
    "details": "Unexpected error during processing: ...",
    "timestamp": "2026-06-21T13:00:00Z",
    "path": null               // workers have no HTTP path — must be omitted / null
  }
  // no requestId on Firestore docs — requestId is an HTTP-layer concept
}
```

**Worker usage pattern (no Flask context):**

```python
from utils.error_codes import make_error_response, ErrorCode

error_resp = make_error_response(
    ErrorCode.PIPELINE_ERROR,
    path=None,          # no HTTP path in a worker
    details_vars={"detail": str(exc)},
    requestId=None,     # no request context
)
error_detail_dict = error_resp.error.to_dict()
# Write error_detail_dict to Firestore job doc as "error_data"
```

`make_error_response` is safe to call outside a Flask context: the `g.session_id` access is
wrapped in `try/except RuntimeError`. The structured log call (to `logger.error`) is also safe
in a worker that has its own logger.

**Key constraint for SP1 implementers:** `ErrorDetail.path` is `None` for all worker-originated
errors. Never use the Firestore `error_data` as a direct HTTP response; SP1 must re-wrap it in an
`ApiResponse` when surfacing job errors via the REST status endpoint.

### 4.6 `backend/models/__init__.py` — export additions

Add `ErrorDetail`, `ApiResponse`, `StatusEnum` to the model exports:

```python
from .errors import ApiResponse, ErrorDetail, StatusEnum
```

No removal of existing exports. The error models are additive.

### 4.7 Frontend — TypeScript types and apiClient update

**New file: `frontend/src/types/errors.ts`**

```typescript
// frontend/src/types/errors.ts
// Mirrors backend models/errors.py — keep in sync with StatusEnum and ErrorDetail.

export type ApiStatus = 'error' | 'success' | 'not_started' | 'processing' | 'completed';

export interface ApiErrorDetail {
  code: string;           // ErrorCode value, e.g. "RESOURCE_NOT_FOUND"
  message: string;        // human-readable summary
  details: string;        // specific detail string
  timestamp: string;      // ISO-8601 UTC
  path: string | null;    // request path; null for worker-originated errors
}

export interface ApiErrorResponse {
  status: 'error';
  error: ApiErrorDetail;
  requestId: string | null;
}

export interface ApiSuccessResponse<T = Record<string, unknown>> {
  status: 'success';
  data: T;
  requestId: string | null;
}

/** Discriminated union for a parsed API response envelope. */
export type ApiResponse<T = Record<string, unknown>> =
  | ApiSuccessResponse<T>
  | ApiErrorResponse;

/** Error thrown by authenticatedFetchJson when the server returns an error body. */
export class ApiError extends Error {
  readonly code: string;
  readonly details: string;
  readonly requestId: string | null;
  readonly path: string | null;

  constructor(detail: ApiErrorDetail, requestId: string | null) {
    super(detail.message);
    this.name = 'ApiError';
    this.code = detail.code;
    this.details = detail.details;
    this.requestId = requestId;
    this.path = detail.path;
  }
}
```

**Update `frontend/src/api/apiClient.ts`**

Current `authenticatedFetch` returns a raw `Response` and callers check `res.ok` and discard the
body on error. Add a new helper `authenticatedFetchJson<T>` that:
1. Makes the authenticated request.
2. On `!res.ok`: tries to parse the body as `ApiErrorResponse`. If parsing succeeds and
   `body.status === "error"`, throws `ApiError`. Otherwise falls back to throwing a plain `Error`
   with the status code.
3. On success: returns the parsed JSON.

```typescript
// frontend/src/api/apiClient.ts  (additions — keep existing authenticatedFetch)
import type { ApiErrorResponse } from '../types/errors';
import { ApiError } from '../types/errors';

export async function authenticatedFetchJson<T = Record<string, unknown>>(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<T> {
  const res = await authenticatedFetch(input, init);
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = null; }
    if (
      body &&
      typeof body === 'object' &&
      (body as Record<string, unknown>).status === 'error' &&
      (body as ApiErrorResponse).error
    ) {
      const errBody = body as ApiErrorResponse;
      throw new ApiError(errBody.error, errBody.requestId ?? null);
    }
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}
```

**Keep `authenticatedFetch`.** The SSE routes (`POST /care_plan`, `POST /care_plan/batch`) return
`text/event-stream` and cannot be consumed via `authenticatedFetchJson`. Callers of SSE routes
keep using `authenticatedFetch` directly and handle the `text/event-stream` body manually. The
SSE event parser in `CarePlanPage.tsx` must be updated to read `event.error_data` instead of
`event.error` (see §4.3).

**Update `frontend/src/api/savedOutputs.ts`.** Switch all calls from `authenticatedFetch` +
manual `!res.ok` checks to `authenticatedFetchJson`. Example for `listSavedOutputs`:

```typescript
export async function listSavedOutputs(): Promise<SavedOutputMeta[]> {
  const json = await authenticatedFetchJson<{ outputs: SavedOutputMeta[] }>(
    `${API_URL}${SAVED_OUTPUTS_PATH}`,
  );
  return json.outputs;
}
```

Apply the same pattern to `getSavedOutput`, `renameSavedOutput`, `deleteSavedOutput`,
`getInputPdfUrl`. Callers that catch errors will now receive an `ApiError` when the server returns
a structured error body.

**Update `CarePlanPage.tsx` — error display.** The SSE parser currently reads:

```typescript
if (event.error) throw new Error(event.error);   // old SSE shape
```

After SP2 this becomes:

```typescript
if (event.step === 'error' && event.error_data) {
  const detail = event.error_data as import('../../types/errors').ApiErrorDetail;
  throw new ApiError(detail, null);
}
```

The error state type changes from `string | null` to `string | null` (still a string for display
— extract `err.message` from the caught `ApiError`). The `error-box` render at line 463 stays
as-is: it displays `error` string, and call-sites set `setError(err instanceof ApiError ?
err.message : 'An unexpected error occurred.')`. The richer `code` and `details` are available on
the `ApiError` instance for future use by SP3 (Ad Hoc UI Polish).

**`frontend/src/types/envelope.ts` — no changes needed.** The success response envelope
(`CarePlanInternal`) is unaffected by SP2. The SSE `step: "result"` payload remains a raw
`CarePlanInternal` dict (not wrapped in `ApiResponse`), as noted in §4.4.

## 5. API Change Summary

SP2 changes no endpoint URLs, HTTP methods, or success response shapes. All changes are to error
response bodies only.

**Error body shape — before:**
```json
{ "error": "Human-readable string" }
```

**Error body shape — after:**
```json
{
  "status": "error",
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Resource not found",
    "details": "care_plan_outputs document abc123 does not exist",
    "timestamp": "2026-06-21T13:30:00Z",
    "path": "/care_plan/saved/abc123"
  },
  "requestId": "sess-uuid-here"
}
```

**SSE error event — before:**
```json
{ "step": "error", "error": "Simplification failed: ..." }
```

**SSE error event — after:**
```json
{
  "step": "error",
  "error_data": {
    "code": "SIMPLIFICATION_FAILED",
    "message": "Simplification step failed",
    "details": "LLM simplification error: ...",
    "timestamp": "2026-06-21T13:30:00Z",
    "path": null
  }
}
```

HTTP status codes are unchanged. The `X-Session-Id` header (already echoed on all responses) is
now also reflected as `requestId` in the error body.

## 6. Frontend Change Summary

Three files change; no new pages or routes.

| File | Change |
|---|---|
| `frontend/src/types/errors.ts` | New file: `ApiStatus`, `ApiErrorDetail`, `ApiErrorResponse`, `ApiSuccessResponse`, `ApiError` class |
| `frontend/src/api/apiClient.ts` | Add `authenticatedFetchJson<T>` helper; keep existing `authenticatedFetch` |
| `frontend/src/api/savedOutputs.ts` | Switch all calls to `authenticatedFetchJson`; remove manual `!res.ok` guards |
| `frontend/src/pages/care-plan/CarePlanPage.tsx` | Update SSE error parser to read `event.error_data`; `setError` from `ApiError.message` |

**No change to SSE success path** (`step === "result"` event) — the `data` field shape is
unchanged. No change to batch SSE progress events. No change to `CarePlanInternal`, `envelope.ts`,
or `carePlan.ts` types.

## 7. Testing

New test file: `backend/tests/utils/test_error_codes.py`

### 7.1 Registry completeness

```python
def test_all_error_codes_in_registry():
    """Every ErrorCode member has an entry in _REGISTRY."""
    from utils.error_codes import ErrorCode, _REGISTRY
    missing = [code for code in ErrorCode if code not in _REGISTRY]
    assert missing == [], f"ErrorCodes missing from registry: {missing}"

def test_all_registry_entries_have_message_and_template():
    """Every _REGISTRY entry is a (str, str) tuple with non-empty strings."""
    from utils.error_codes import _REGISTRY
    for code, (message, template) in _REGISTRY.items():
        assert isinstance(message, str) and message, f"{code}: message is empty"
        assert isinstance(template, str) and template, f"{code}: details template is empty"
```

### 7.2 make_error_response output shape

```python
def test_make_error_response_returns_api_response():
    from utils.error_codes import make_error_response, ErrorCode
    from models.errors import ApiResponse, StatusEnum
    resp = make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path="/test", details_vars={"collection":"c","doc_id":"d"})
    assert isinstance(resp, ApiResponse)
    assert resp.status == StatusEnum.error
    assert resp.error is not None
    assert resp.error.code == "RESOURCE_NOT_FOUND"
    assert "c" in resp.error.details or "d" in resp.error.details

def test_make_error_response_fills_details_template():
    from utils.error_codes import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.UNKNOWN_VERSION, path="/test", details_vars={"version":"3.0","allowed":"1.2"})
    assert "3.0" in resp.error.details
    assert "1.2" in resp.error.details

def test_make_error_response_handles_missing_template_vars():
    """Partial template fill leaves unfilled placeholders as {key} text."""
    from utils.error_codes import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path="/test")
    assert "{collection}" in resp.error.details or resp.error.details  # no KeyError raised

def test_make_error_response_no_flask_context_does_not_raise():
    """Callable outside a Flask request context (e.g. worker)."""
    from utils.error_codes import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.TIMEOUT, path=None)
    assert resp.requestId is None  # no g.session_id outside app context

def test_make_error_response_uses_g_session_id(app_context):
    """Within a Flask request context, requestId is taken from g.session_id."""
    from flask import g
    from utils.error_codes import make_error_response, ErrorCode
    g.session_id = "sess-abc-123"
    resp = make_error_response(ErrorCode.INTERNAL_ERROR, path="/test")
    assert resp.requestId == "sess-abc-123"

def test_make_error_response_logs_error(caplog):
    import logging
    from utils.error_codes import make_error_response, ErrorCode
    with caplog.at_level(logging.ERROR, logger="utils.error_codes"):
        make_error_response(ErrorCode.UNAUTHORIZED, path="/test", details_vars={"detail":"expired"})
    assert any("UNAUTHORIZED" in r.getMessage() or getattr(r, "error_code", "") == "UNAUTHORIZED"
                for r in caplog.records)
```

### 7.3 ApiResponse Pydantic round-trip

New test file: `backend/tests/models/test_errors.py`

```python
def test_api_response_error_round_trip():
    from models.errors import ApiResponse, ErrorDetail, StatusEnum
    detail = ErrorDetail(code="INTERNAL_ERROR", message="msg", details="det",
                         timestamp="2026-01-01T00:00:00Z", path="/test")
    resp = ApiResponse(status=StatusEnum.error, error=detail, requestId="req-1")
    d = resp.to_dict()
    assert d["status"] == "error"
    assert d["error"]["code"] == "INTERNAL_ERROR"
    assert d["requestId"] == "req-1"
    # round-trip
    resp2 = ApiResponse.from_dict(d)
    assert resp2.error.code == "INTERNAL_ERROR"

def test_api_response_path_is_optional():
    from models.errors import ApiResponse, ErrorDetail, StatusEnum
    detail = ErrorDetail(code="TIMEOUT", message="timed out", details="",
                         timestamp="2026-01-01T00:00:00Z")  # path omitted
    resp = ApiResponse(status=StatusEnum.error, error=detail)
    d = resp.to_dict()
    assert d["error"]["path"] is None

def test_api_response_extra_field_raises():
    from models.errors import ApiResponse
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ApiResponse(status="error", unknown_field="x")

def test_status_enum_values():
    from models.errors import StatusEnum
    assert set(e.value for e in StatusEnum) == {"error","success","not_started","processing","completed"}
```

### 7.4 Route-level regression tests

Extend existing route tests to assert that error responses now match the structured shape:

- `test_saved_outputs_route.py`: assert 404 and 403 responses contain `"status": "error"` and
  an `"error"` object with a `"code"` key.
- `test_grading_route.py`: assert 400 responses for missing text carry the structured shape.
- `test_care_plan_auth.py`: assert 401 from `verify_firebase_token` carries `"code":
  "UNAUTHORIZED"` or `"MISSING_AUTH_HEADER"`.

These are additive assertions on existing tests, not new test files.

## 8. Manual Intervention Required From You

1. **Decide whether success responses should be wrapped in `ApiResponse`.** SP2's scope (§4.4)
   intentionally excludes wrapping success payloads in `{"status":"success","data":{...}}` to
   limit the blast radius. If you want all responses — success and error — to use `ApiResponse`,
   say so before implementation begins; the scope change affects every route handler.

2. **Confirm the SSE transition shape** `{"step":"error","error_data":{...}}` is acceptable to
   the frontend during the SP1 window. The alternative is keeping `{"step":"error","error":"..."}` 
   for SSE (preserving current frontend) and only changing REST error bodies now, then having SP1
   eliminate SSE entirely without a transition shape. Both are viable; the PRD assumes the
   transition shape.

3. **Decide on `authenticatedFetchJson` rollout.** SP2 scopes this to `savedOutputs.ts` and the
   SSE error parser in `CarePlanPage.tsx`. If you want `datasets.ts` and other API modules
   converted too, include them explicitly before the implementation task is written.

## 9. Open Questions & Decisions

1. **Success responses in `ApiResponse` wrapper.**
   `[RESOLVED: Deferred. Only error responses adopt ApiResponse in SP2. Success paths unchanged.
   New endpoints created by SP1 will use ApiResponse for both success and error from day one.]`

2. **SSE transition shape vs. immediate SSE removal.**
   `[RESOLVED: The {"step":"error","error_data":{...}} transition shape is acceptable. SP1 should
   land immediately after SP2 to keep the window short. Frontend must handle the new SSE error
   shape during the transition window.]`

3. **`get_owned_doc_or_403` path parameter.**
   `[RESOLVED: Add `path: str | None = None` parameter to `get_owned_doc_or_403`. All call-sites
   pass `request.path`. This is a minor, backward-compatible signature change with no behavioral
   impact.]`

4. **ErrorCode naming convention.**
   `[RESOLVED: SCREAMING_SNAKE_CASE strings, equal to the enum member name (via StrEnum). No
   numeric codes, no namespacing prefix. Easy to search, human-readable in logs and Firestore.]`

5. **`ErrorDetail.code` type: string vs. `ErrorCode` enum.**
   `[RESOLVED: string (the `.value`). Avoids circular imports between `models/errors.py` and
   `utils/error_codes.py`, and makes `ErrorDetail` serializable to Firestore without Pydantic
   custom serializers. The `make_error_response` helper accepts `ErrorCode` enum members and
   writes `.value`.]`

6. **`make_error_response` logging level.**
   `[RESOLVED: `logger.error(...)`. Every structured error is logged at ERROR so it surfaces in
   Cloud Logging error dashboards without additional filtering. Callers do not log separately.]`

7. **`authenticatedFetch` vs. `authenticatedFetchJson` split.**
   `[RESOLVED: Keep both. SSE routes need the raw Response stream; `authenticatedFetch` stays for
   those. JSON REST routes use `authenticatedFetchJson`. This avoids complicating the streaming
   path.]`

8. **`CarePlanPage.tsx` error state type.**
   `[RESOLVED: `error` state remains `string | null` — the component always displays a string.
   The `ApiError` class is caught at the call site and `err.message` is extracted before
   `setError`. The richer `code` and `details` are available on the thrown `ApiError` for future
   display enhancement in SP3.]`

9. **Worker / Cloud Tasks usage of `make_error_response`.**
   `[RESOLVED: Safe to call with `path=None` and `requestId=None` outside Flask context. The
   `try/except RuntimeError` guard around `g.session_id` is the only concession to the worker
   environment. SP1 must not pass an HTTP `ApiResponse` body to Firestore — only the inner
   `ErrorDetail.to_dict()` goes in `error_data`.]`

10. **Frontend `datasets.ts` and other API modules.**
    `[DEFERRED]` — Only `savedOutputs.ts` and the SSE error parser in `CarePlanPage.tsx` are
    in scope for SP2. Other API modules (`datasets.ts`, potential future grading API calls) should
    adopt `authenticatedFetchJson` when they are next modified.
