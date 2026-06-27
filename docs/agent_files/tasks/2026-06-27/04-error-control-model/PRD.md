# PRD: SP4 — Error Control Model

**Sub-project:** SP4  
**Branch context:** `athena_health_part1`  
**Date:** 2026-06-27  
**Status:** Planning — no implementation started

---

## 1. Problem

The Juno backend and frontend handle errors through two incompatible systems that have grown apart since SP2. SP3 Athena work will introduce new failure modes (auth failures, API errors, rate limits) that require well-defined error codes. Shipping SP3 on top of the current inconsistencies will make error surfaces harder to debug and harder for the frontend to render correctly.

**Specific inconsistencies as of 2026-06-27:**

1. **Two `make_error_response()` functions with incompatible return shapes.** `backend/utils/error_codes.py` (line 77) returns a Pydantic `ApiResponse` object. `backend/utils/error_handler.py` (line 148) returns a raw `(dict, int)` tuple. Same function name, two modules, two contracts. Callers that import from the wrong module get a silent type error only discoverable at runtime.

2. **`ErrorDetail` in `backend/models/errors.py` is missing fields the Firestore error shape has.** `ErrorDetail` has `code`, `message`, `details` (plural, required `str`), `timestamp`, `path`. The Firestore error dict written by `build_error_data()` in `error_handler.py` has `code`, `message`, `user_hint`, `retryable`, and `detail` (singular). The frontend `CarePlanJobPage.tsx` (lines 404–411) must defensively access `errData?.user_hint ?? errData?.message` and `errData?.detail ?? errData?.details ?? null` to handle both shapes.

3. **`jobs.ts` bypasses structured error handling for two high-traffic POST endpoints.** `createCarePlanJob` (line 21) and `createBatchJobs` (line 33) use raw `authenticatedFetch` and `res.text()` on failure. `ApiError` is never thrown from these paths; error boxes display raw JSON strings instead of structured messages.

4. **`datasets.py` bypasses the SP2 `ApiResponse` envelope on two live routes** (lines 29 and 31). Both `GCSFetchRequired` and `FileNotFoundError` handlers call bare `jsonify({"error": "..."})`. Any client that parses a structured `ApiErrorResponse` will silently get `undefined` for all fields.

5. **Zero Athena-specific error codes exist in `backend/utils/error_codes.py`.** The SP3 README (resolved in `docs/agent_files/tasks/2026-06-27/README.md`) names `ATHENA_AUTH_FAILED / ATHENA_API_ERROR / ATHENA_RATE_LIMIT_ERROR` as locked decisions, but none appear in the `ErrorCode` StrEnum or `_REGISTRY`.

6. **No `FirestoreJobError` TypeScript interface.** The frontend reads Firestore `error_data` as an untyped `any`-shaped dict via `jobDoc.error_data`. No interface enforces what fields are present or their types.

---

## 2. Goals

1. Single canonical `ErrorDetail` shape on HTTP — all routes return `ApiResponse` with a typed `ErrorDetail` that includes `user_hint` and `retryable` as optional fields.
2. Single canonical `FirestoreJobError` shape on Firestore — the worker always writes the same dict structure; the frontend always reads a typed interface.
3. Typed TypeScript interfaces for `ErrorDetail`, `ApiError`, and `FirestoreJobError` in `frontend/src/types/errors.ts`.
4. One authoritative `make_error_response()` in `backend/utils/error_codes.py`. The duplicate in `backend/utils/error_handler.py` is deleted; all callers migrated.
5. Global Flask error handlers for 404, 405, and 500 in `app.py` — all three use `make_error_response()`.
6. Athena error codes (`ATHENA_AUTH_FAILED`, `ATHENA_API_ERROR`, `ATHENA_RATE_LIMIT_ERROR`, `ATHENA_PATIENT_NOT_FOUND`, `ATHENA_TIMEOUT`) added to `backend/utils/error_codes.py` with `_REGISTRY` entries.
7. No bare `jsonify({"error": "..."})` calls in any route handler — all replaced with `make_error_response()`.
8. `createCarePlanJob` and `createBatchJobs` in `frontend/src/api/jobs.ts` switched to `authenticatedFetchJson` so `ApiError` is thrown on failures.
9. A React `ErrorBoundary` component added at `frontend/src/components/ErrorBoundary.tsx`.

---

## 3. Non-Goals

- No UI redesign of error display pages. `CarePlanJobPage.tsx` error state rendering is kept as-is.
- No changes to logging or metrics infrastructure (`utils/juno_logger.py`, `utils/markers.py`, OpenTelemetry).
- No changes to Athena integration logic itself — SP4 only adds the error codes SP3 will reference.
- No renaming of HTTP fields callers already depend on. `requestId` (camelCase) stays camelCase to match the existing TypeScript client. `details` (plural) stays plural on `ErrorDetail`. Backward compatibility is the priority for success responses.
- No `request_id` generation at runtime — `requestId` remains nullable (`None`/`null`) throughout. A future sub-project can wire in UUID generation.
- No changes to the pipeline-level error catalog in `backend/error_codes.py` (`ERROR_CATALOG`, `ErrorInfo`, pipeline `ErrorCode`). That system is not being merged — only the duplicate `make_error_response` is removed.

---

## 4. Architecture Decisions

### 4a. Canonical Error Shape (Backend)

**File:** `backend/models/errors.py`

The current `ErrorDetail` has no `user_hint` or `retryable` fields and uses a required `details: str = ""`. The new shape adds both missing fields as optional and relaxes `details` to `Optional[str]` so the Firestore subset can omit it:

```python
from typing import Any, Optional

class ErrorDetail(JsonModel):
    code: str
    message: str
    details: Optional[str] = None       # was `str = ""` — relaxed to Optional
    timestamp: str
    path: Optional[str] = None
    user_hint: Optional[str] = None     # new — from error_handler.py's Firestore shape
    retryable: bool = False             # new — from error_handler.py's Firestore shape
```

`ApiResponse` already uses `Optional` for all fields; no changes needed there. Reproduced here for reference:

```python
class ApiResponse(JsonModel):
    status: StatusEnum
    data: Optional[Any] = None
    error: Optional[ErrorDetail] = None
    requestId: Optional[str] = None     # camelCase preserved — TypeScript client depends on it
```

---

### 4b. Single `make_error_response()` in `backend/utils/error_codes.py`

**File:** `backend/utils/error_codes.py`

Add `user_hint` and `retryable` as optional kwargs. These flow into the `ErrorDetail` so routes can pass user-facing hints for errors where the registry's default is insufficient:

```python
def make_error_response(
    code: ErrorCode,
    path: str | None = None,
    details_vars: dict | None = None,
    requestId: str | None = None,
    user_hint: str | None = None,
    retryable: bool = False,
) -> ApiResponse:
    """Build a structured ApiResponse for an error and log it."""
    message, details_template = _REGISTRY.get(code, ("Unknown error", "{detail}"))
    details = _safe_format(details_template, details_vars or {})

    if requestId is None:
        try:
            requestId = getattr(g, "session_id", None)
        except RuntimeError:
            requestId = None

    timestamp = datetime.now(timezone.utc).isoformat()

    error_detail = ErrorDetail(
        code=code.value,
        message=message,
        details=details or None,        # convert empty string to None
        timestamp=timestamp,
        path=path,
        user_hint=user_hint,
        retryable=retryable,
    )
    # ... logger.error(...) unchanged ...
    return ApiResponse(
        status=StatusEnum.error,
        error=error_detail,
        requestId=requestId,
    )
```

**`backend/utils/error_handler.py` — what to delete and what to move:**

The duplicate `make_error_response()` (line 148, returns `(dict, int)`) is **deleted** — no migration, it has no confirmed callers in the routes.

The remaining functions (`JunoError`, `classify_vertex_exception`, `classify_finish_reason`, `_classify_exc`, `build_error_data`, `build_error_data_from_exc`, `handle_exception`) are **moved** to a new file: **`backend/utils/pipeline_errors.py`**. This preserves the separation between the HTTP error catalog (`utils/error_codes.py`) and the pipeline-level error classification logic that depends on `backend/error_codes.py`'s `ERROR_CATALOG`.

The whole `error_handler.py` file is then deleted.

**Callers to migrate** (update import from `utils.error_handler` → `utils.pipeline_errors`):

| File | Import being changed |
|---|---|
| `backend/routes/worker.py` line 22 | `from utils.error_handler import build_error_data, build_error_data_from_exc` |
| `backend/routes/care_plan.py` line 37 | `from utils.error_handler import build_error_data_from_exc` |

---

### 4c. Athena Error Codes

**File:** `backend/utils/error_codes.py`

Add to the `ErrorCode` StrEnum under a new `# Athena` section:

```python
class ErrorCode(StrEnum):
    # ... existing codes unchanged ...

    # Athena Health
    ATHENA_AUTH_FAILED       = "ATHENA_AUTH_FAILED"
    ATHENA_API_ERROR         = "ATHENA_API_ERROR"
    ATHENA_RATE_LIMIT_ERROR  = "ATHENA_RATE_LIMIT_ERROR"
    ATHENA_PATIENT_NOT_FOUND = "ATHENA_PATIENT_NOT_FOUND"
    ATHENA_TIMEOUT           = "ATHENA_TIMEOUT"
```

Add to `_REGISTRY`:

```python
_REGISTRY: dict[ErrorCode, tuple[str, str]] = {
    # ... existing entries unchanged ...

    # Athena Health
    ErrorCode.ATHENA_AUTH_FAILED:       ("Athena Health authentication failed",          "OAuth2 token request failed: {detail}"),
    ErrorCode.ATHENA_API_ERROR:         ("Athena Health API error",                      "Athena API returned an error for {athena_api_path}: {detail}"),
    ErrorCode.ATHENA_RATE_LIMIT_ERROR:  ("Athena Health rate limit exceeded",            "Rate limit hit on {athena_api_path}; retry after {retry_after}s"),
    ErrorCode.ATHENA_PATIENT_NOT_FOUND: ("Athena Health patient not found",              "No patient found for practiceId={practice_id} patientId={patient_id}"),
    ErrorCode.ATHENA_TIMEOUT:           ("Athena Health API request timed out",          "Request to {athena_api_path} exceeded the timeout of {timeout_s}s"),
}
```

These codes will be used by the SP3 `AthenaClient` when it raises errors. SP4 only registers the codes; SP3 wires the raises.

---

### 4d. Global Flask Error Handlers in `app.py`

**File:** `backend/app.py`

The 404 and 500 handlers already exist and already call `make_error_response()`. Add the missing 405 handler between them:

```python
@app.errorhandler(404)
def not_found(error):
    return make_error_response(
        ErrorCode.ENDPOINT_NOT_FOUND,
        request.path,
        {"method": request.method, "path": request.path},
    ).to_dict(), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return make_error_response(
        ErrorCode.ENDPOINT_NOT_FOUND,
        request.path,
        {"method": request.method, "path": request.path},
    ).to_dict(), 405


@app.errorhandler(500)
def internal_error(error):
    return make_error_response(
        ErrorCode.INTERNAL_ERROR,
        request.path,
    ).to_dict(), 500
```

No other changes to `app.py`.

---

### 4e. Route Migration

**File:** `backend/routes/datasets.py`

Two bare `jsonify({"error": "..."})` calls on lines 29 and 31 must use `make_error_response()` instead. Add the import at the top of `datasets.py`:

```python
from flask import Blueprint, jsonify, request
from utils.error_codes import make_error_response, ErrorCode
```

Old vs. new:

| Line | Before | After |
|---|---|---|
| 29 (GCSFetchRequired) | `return jsonify({"error": "On-demand GCS fetch not yet implemented (SP2)"}), 503` | `return make_error_response(ErrorCode.DATASET_DOWNLOAD_ERROR, request.path, {"group": group, "input_id": input_id, "detail": "GCS fetch not yet implemented (SP2)"}).to_dict(), 503` |
| 31 (FileNotFoundError) | `return jsonify({"error": "Not found"}), 404` | `return make_error_response(ErrorCode.DATASET_NOT_FOUND, request.path, {"group": group, "input_id": input_id}).to_dict(), 404` |

**Policy:** No route handler in any `backend/routes/` file may call bare `jsonify({"error": ...})`. All error responses go through `make_error_response()`. This policy applies to all future routes as well.

---

### 4f. Firestore Error Shape (`FirestoreJobError`)

The worker writes a subset of `ErrorDetail` to Firestore. It intentionally omits `path` and `requestId` — those are HTTP-layer concepts with no meaning inside a background job.

**Canonical Firestore error dict** (what `fail_job()` receives as `error_data`):

```json
{
  "code": "LLM_MAX_TOKENS",
  "message": "LLM generation stopped at the output token limit...",
  "user_hint": "The document was too long to process in full...",
  "retryable": false,
  "details": "Traceback: ...",
  "timestamp": "2026-06-27T12:00:00.000000+00:00"
}
```

Fields:

| Field | Type | Notes |
|---|---|---|
| `code` | `string` | `ErrorCode` value from either namespace (pipeline or SP2) |
| `message` | `string` | Developer-facing description |
| `user_hint` | `string \| null` | User-facing actionable message; null for SP2 codes that don't set it |
| `retryable` | `boolean` | Whether the same job can be re-submitted |
| `details` | `string \| null` | Exception string or extra context; null if not applicable |
| `timestamp` | `string` | ISO-8601 UTC (e.g. `datetime.now(timezone.utc).isoformat()`) |

**What to change in `backend/utils/pipeline_errors.py`** (the new home of `build_error_data`):

The current `build_error_data()` omits `timestamp` and uses `"detail"` (singular). The new version uses `"details"` (plural, matching `ErrorDetail`) and adds `"timestamp"`:

```python
def build_error_data(error_code: ErrorCode, detail: str = "") -> dict:
    """Build the error_data dict written to Firestore on job failure."""
    info = ERROR_CATALOG[error_code]
    return {
        "code": info.code,
        "message": info.message,
        "user_hint": info.user_hint,
        "retryable": info.retryable,
        "details": detail or None,                             # was "detail" singular — renamed
        "timestamp": datetime.now(timezone.utc).isoformat(),  # new field
    }
```

---

### 4g. Frontend TypeScript Interfaces

**File:** `frontend/src/types/errors.ts`

Replace the current interfaces with the three canonical interfaces:

```typescript
// Mirrors backend models/errors.py ErrorDetail — keep in sync.
export interface ApiErrorDetail {
  code: string;
  message: string;
  details: string | null;      // was `string` (non-nullable) — relaxed to nullable
  timestamp: string;
  path: string | null;
  user_hint: string | null;    // new — was absent
  retryable: boolean;          // new — was absent
}

// Thrown by authenticatedFetchJson when the server returns an ApiResponse with status="error".
export class ApiError extends Error {
  readonly code: string;
  readonly details: string | null;
  readonly requestId: string | null;
  readonly path: string | null;
  readonly userHint: string | null;   // new — mapped from detail.user_hint
  readonly retryable: boolean;        // new — mapped from detail.retryable

  constructor(detail: ApiErrorDetail, requestId: string | null) {
    super(detail.message);
    this.name = 'ApiError';
    this.code = detail.code;
    this.details = detail.details;
    this.requestId = requestId;
    this.path = detail.path;
    this.userHint = detail.user_hint;
    this.retryable = detail.retryable;
  }
}

// Mirrors the Firestore error_data dict written by worker.py's fail_job() call.
// Does NOT include path or requestId — those are HTTP-only fields.
export interface FirestoreJobError {
  code: string;
  message: string;
  user_hint: string | null;
  retryable: boolean;
  details: string | null;
  timestamp: string;            // ISO-8601 UTC
}

// Keep existing ApiErrorResponse, ApiSuccessResponse, ApiResponse, ApiStatus unchanged.
```

`CarePlanJobPage.tsx` already reads `jobDoc.error_data` with `errData?.user_hint`, `errData?.retryable`, etc. After this change, the `jobDoc.error_data` field should be typed as `FirestoreJobError | null` rather than `any`. That typing change is done in the `JobDoc` TypeScript type (wherever `jobDoc` is defined), not in `errors.ts`.

---

### 4h. `apiClient.ts` Error Parsing

**File:** `frontend/src/api/apiClient.ts`

`authenticatedFetchJson` already correctly parses `ApiErrorResponse` and throws `ApiError` on non-2xx responses. The only change needed is updating the `ApiError` constructor call to pass through the two new fields (`user_hint`, `retryable`) — which happens automatically because `ApiError`'s constructor signature accepts `ApiErrorDetail` and the new fields are on that interface.

---

### 4i. `jobs.ts` Migration

**File:** `frontend/src/api/jobs.ts`

Both `createCarePlanJob` and `createBatchJobs` currently call raw `authenticatedFetch`, read `res.text()` on error, and throw a plain `Error`. This bypasses the structured `ApiError` path.

**`createCarePlanJob`** — switch to `authenticatedFetchJson`:

```typescript
// Before:
export async function createCarePlanJob(formData: FormData): Promise<CreateJobResponse> {
  const res = await authenticatedFetch(`${API_URL}${CARE_PLAN_JOBS_PATH}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error: ${res.status}`);
  }
  return res.json();
}

// After:
export async function createCarePlanJob(formData: FormData): Promise<CreateJobResponse> {
  return authenticatedFetchJson<CreateJobResponse>(`${API_URL}${CARE_PLAN_JOBS_PATH}`, {
    method: 'POST',
    body: formData,
    // No Content-Type header — browser sets multipart/form-data with boundary automatically
  });
}
```

**`createBatchJobs`** — same pattern:

```typescript
// Before:
export async function createBatchJobs(body: CreateBatchJobsRequest): Promise<CreateBatchJobsResponse> {
  const res = await authenticatedFetch(`${API_URL}${CARE_PLAN_BATCH_JOBS_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error: ${res.status}`);
  }
  return res.json();
}

// After:
export async function createBatchJobs(body: CreateBatchJobsRequest): Promise<CreateBatchJobsResponse> {
  return authenticatedFetchJson<CreateBatchJobsResponse>(`${API_URL}${CARE_PLAN_BATCH_JOBS_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
```

Update the import at the top of `jobs.ts`:

```typescript
// Before:
import { authenticatedFetch } from './apiClient';

// After:
import { authenticatedFetchJson } from './apiClient';
```

---

### 4j. React Error Boundary

**File:** `frontend/src/components/ErrorBoundary.tsx` (new file)

A simple class component that catches render errors and displays a fallback. Used per-page to prevent one page's crash from taking down navigation.

```typescript
import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('[ErrorBoundary] caught render error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          style={{
            padding: '80px 32px',
            textAlign: 'center',
            color: 'var(--error, #DC2626)',
          }}
        >
          Something went wrong. Please refresh the page.
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
```

Usage in a page (example for `CarePlanJobPage`):

```tsx
// In the page's parent route or App.tsx:
<ErrorBoundary>
  <CarePlanJobPage />
</ErrorBoundary>
```

The placement decision (per-page vs. global) is marked `[OPEN]` in section 9.

---

## 5. API Change Summary

All changes to the HTTP error response are additive — no existing fields are removed or renamed.

| Route | Change |
|---|---|
| `GET /care_plan/datasets/{group}/{input_id}/{filename}` | Error responses now return `ApiResponse` envelope instead of bare `{"error": "..."}`. HTTP status codes unchanged (503, 404). |
| `POST /care_plan/jobs` | On error, now throws `ApiError` on the client instead of plain `Error`. HTTP contract unchanged. |
| `POST /care_plan/batch/jobs` | Same as above. |
| All routes (405 responses) | Now return `ApiResponse` envelope for method-not-allowed instead of Flask's default HTML. |
| All routes (error responses) | `ErrorDetail` gains two new optional fields: `user_hint` (string \| null) and `retryable` (bool, default false). Clients that don't read these fields are unaffected. |

**Success responses are unchanged.** No `data` field shapes change.

---

## 6. Frontend Change Summary

| File | Change |
|---|---|
| `frontend/src/types/errors.ts` | Add `user_hint`, `retryable` to `ApiErrorDetail`; add `userHint`, `retryable` to `ApiError` class; add new `FirestoreJobError` interface. |
| `frontend/src/api/jobs.ts` | Switch `createCarePlanJob` and `createBatchJobs` from raw `authenticatedFetch` to `authenticatedFetchJson`. Remove `res.text()` error paths. |
| `frontend/src/api/apiClient.ts` | No logic changes. `ApiError` constructor automatically captures `user_hint` and `retryable` via the updated `ApiErrorDetail` type. |
| `frontend/src/components/ErrorBoundary.tsx` | New file. |
| `frontend/src/pages/care-plan/CarePlanJobPage.tsx` | No logic changes. Existing `errData?.user_hint ?? errData?.message` and `errData?.detail ?? errData?.details` defensive reads continue to work. Optionally: type `jobDoc.error_data` as `FirestoreJobError \| null`. |

---

## 7. Testing

### Backend unit tests

**`backend/tests/utils/test_error_codes.py`** — add or update:

- `test_make_error_response_includes_user_hint`: call `make_error_response(ErrorCode.PIPELINE_ERROR, user_hint="Try again")` and assert `response.error.user_hint == "Try again"`.
- `test_make_error_response_includes_retryable`: call with `retryable=True` and assert `response.error.retryable is True`.
- `test_make_error_response_default_retryable_false`: call without `retryable` kwarg and assert `response.error.retryable is False`.
- `test_make_error_response_details_none_when_empty`: call with no `details_vars` and assert `response.error.details is None` (not `""`).
- `test_athena_error_codes_registered`: for each new Athena code, assert it is in `_REGISTRY` and `make_error_response(code, "/test")` does not raise.

**`backend/tests/utils/test_pipeline_errors.py`** (new file for the moved module):

- `test_build_error_data_includes_timestamp`: call `build_error_data(ErrorCode.JOB_TIMEOUT)` and assert `"timestamp"` key is present and parses as ISO-8601.
- `test_build_error_data_uses_details_key`: assert result dict has `"details"` key (plural), not `"detail"`.
- `test_build_error_data_from_exc_juno_error`: raise a `JunoError(ErrorCode.LLM_MAX_TOKENS, "too big")`, pass to `build_error_data_from_exc`, assert `result["code"] == "LLM_MAX_TOKENS"` and `result["user_hint"]` is non-empty.

### Frontend unit tests

**`frontend/src/api/__tests__/jobs.test.ts`** — add:

- `test createCarePlanJob throws ApiError on 422`: mock `authenticatedFetchJson` to throw `ApiError`; assert caller receives `ApiError` (not plain `Error`).
- `test createBatchJobs throws ApiError on 400`: same pattern.

**`frontend/src/components/__tests__/ErrorBoundary.test.tsx`** — add:

- `test renders fallback on render error`: mount `<ErrorBoundary fallback={<div>fallback</div>}><ThrowOnRender /></ErrorBoundary>`; assert fallback is rendered after throw.
- `test renders children when no error`: assert children render normally.

### Manual integration tests

1. Call `POST /care_plan/batch/jobs` with an invalid body; confirm the response body is a full `ApiResponse` with `status: "error"`, `error.code`, `error.user_hint`.
2. Call `GET /care_plan/datasets/nonexistent-group/0001/question.txt`; confirm the response is `ApiResponse` (not `{"error": "Not found"}`).
3. Call a route with wrong HTTP method (e.g. `GET /care_plan/jobs`); confirm the 405 response is `ApiResponse`.
4. Trigger a batch job that fails; open the `CarePlanJobPage` for the job; confirm all error fields render (message, code badge, retryable indicator, technical detail box).

---

## 8. Manual Intervention Required

None. SP4 is entirely code changes — no GCS bucket setup, no Cloud Run env vars, no Firestore schema migration (Firestore is schemaless; the new `timestamp` and renamed `details` key land naturally on new job writes).

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Whether to delete `error_handler.py` entirely vs. only its `make_error_response`. | [RESOLVED: delete the file entirely. Move `JunoError`, classification functions, `build_error_data`, `build_error_data_from_exc`, `handle_exception` to new `backend/utils/pipeline_errors.py`. Migrate 3 import sites: `worker.py` (2 functions), `care_plan.py` (1 function).] |
| Q2 | `user_hint` and `retryable` fields in HTTP `ErrorDetail`. | [RESOLVED: add as Optional to `ErrorDetail`; `user_hint` defaults to `None`, `retryable` defaults to `False`. Existing callers that don't set them get null/false — backward compatible.] |
| Q3 | Athena error code naming convention. | [RESOLVED: `ATHENA_AUTH_FAILED / ATHENA_API_ERROR / ATHENA_RATE_LIMIT_ERROR / ATHENA_PATIENT_NOT_FOUND / ATHENA_TIMEOUT` — consistent with SP3 README locked decisions.] |
| Q4 | Whether `ErrorBoundary` is per-page or global (wrapping all of `App.tsx`). | [RESOLVED — per-page ErrorBoundary wrapping CarePlanJobPage and BatchPage; global fallback around App.tsx as last resort only] |
| Q5 | Whether to add `request_id` generation (UUID per request via `before_request`). | [DEFERRED — `requestId` stays `null` for now. A dedicated sub-project can wire UUID generation once structured logging is audited end-to-end.] |
| Q6 | Whether `CarePlanJobPage.tsx` should read `jobDoc.error_data` as `FirestoreJobError \| null` (typed) vs. keeping it as the existing untyped shape. | [RESOLVED: update the `JobDoc` type to use `FirestoreJobError \| null` for `error_data`. The JSX in `CarePlanJobPage.tsx` already accesses exactly the fields that `FirestoreJobError` defines — no logic changes needed, only a type annotation.] |
| Q7 | What SP2 `ErrorCode` to use for the `GCSFetchRequired` 503 response in `datasets.py`. | [RESOLVED: use `DATASET_DOWNLOAD_ERROR` (already in `_REGISTRY`) for the 503 response — it signals "the requested data is not locally available." Use `DATASET_NOT_FOUND` for the 404 response when `FileNotFoundError` is raised.] |
| Q8 | Should `handle_exception()` from `error_handler.py` (which returns `(dict, int)`) be migrated to `pipeline_errors.py` or dropped? | [RESOLVED: move to `pipeline_errors.py` as-is. It is a convenience wrapper used in tests and may be needed by SP3 worker error handling for Google API exceptions. Do not drop.] |
