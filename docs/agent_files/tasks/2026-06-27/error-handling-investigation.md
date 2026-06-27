# Error Handling Investigation
Date: 2026-06-27

## Summary

The Juno backend runs **two parallel and incompatible error contracts**: the SP2 `ApiResponse` envelope
(`utils/error_codes.py`) used by public HTTP routes, and a separate pipeline/worker catalog
(`backend/error_codes.py` + `utils/error_handler.py`) that produces a structurally different dict
written to Firestore. This split is not merely cosmetic — the two `make_error_response()` functions
have the same name, live in different modules, and return incompatible shapes. The frontend handles
both shapes with fallback chaining on untyped data. Four route endpoints bypass the structured
envelope entirely with ad-hoc `jsonify({"error": "..."})` responses, and the jobs API client drops
structured error details for the two highest-traffic endpoints. Severity: **high** — any new feature
that crosses the API/worker boundary (e.g., Athena integration) will inherit this confusion
immediately.

---

## What Works Well

- `utils/error_codes.py:make_error_response()` is used correctly in the majority of authenticated
  routes: `care_plan_jobs.py`, `batch_jobs.py`, `grading.py`, `saved_outputs.py`, and the shared
  `firebase.py` auth decorators all call this function and return `.to_dict()` with a proper HTTP
  status code.
- The Flask 404/500 global handlers in `app.py` (lines 196-209) use `make_error_response()`,
  so unknown endpoints and unhandled 500s do return the SP2 envelope.
- `backend/models/errors.py` (`ErrorDetail`, `ApiResponse`) is a clean, typed Pydantic model — good
  single source of truth for the SP2 wire shape.
- The frontend `frontend/src/types/errors.ts` defines `ApiErrorDetail` / `ApiErrorResponse` / `ApiError`
  that correctly mirror the SP2 backend model, and `apiClient.ts:authenticatedFetchJson()` promotes
  structured `ApiError` exceptions for routes that use the JSON variant.
- `CarePlanJobPage.tsx` degrades gracefully when `error_data` fields are absent — it chains
  `user_hint ?? message` and `detail ?? details` so both the old SP2 shape and the new pipeline
  shape render without crashing.
- The worker's OIDC verification (`_verify_oidc_token`) is thorough and returns early 403s instead
  of leaking job details.
- `utils/error_handler.py:build_error_data_from_exc()` correctly classifies JunoError, Google API
  errors, and legacy RuntimeErrors before writing to Firestore — a sensible classifier exists; it
  just is not wired to the HTTP surface.

---

## Inconsistencies Found

### 1. Two Incompatible `make_error_response()` Functions

There are **two files named `error_codes.py`** and **two functions named `make_error_response()`**
that return completely different shapes:

| Location | Return type | Shape |
|----------|-------------|-------|
| `backend/utils/error_codes.py` (SP2) | `ApiResponse` Pydantic model | `{status, error: {code, message, details, timestamp, path}, requestId}` |
| `backend/utils/error_handler.py` | `(dict, int)` tuple | `{error: True, code, message, user_hint, detail, retryable, http_status}` |

The second function is **never called by any HTTP route handler** (it is only imported into `_classify_exc`
scaffolding internally) but it exists with the same name in a co-located file, which creates an
ongoing maintenance trap. Any developer searching for `make_error_response` gets two hits with no
obvious guidance on which to use.

### 2. Ad-hoc `jsonify({"error": "..."})` Bypasses the SP2 Envelope

Four endpoints return bare `{"error": "<string>"}` instead of the SP2 `ApiResponse`:

| File | Line | Status | Shape |
|------|------|--------|-------|
| `backend/routes/care_plan.py` | 53–55 | 410 | `{"error": "This SSE endpoint has been removed..."}` |
| `backend/routes/batch.py` | 22–25 | 410 | `{"error": "This SSE endpoint has been removed..."}` |
| `backend/routes/datasets.py` | 29 | 503 | `{"error": "On-demand GCS fetch not yet implemented (SP2)"}` |
| `backend/routes/datasets.py` | 31 | 404 | `{"error": "Not found"}` |

The deprecated endpoints at 410 are low-traffic but the two `datasets.py` deviations are on live
routes: the `GET /care_plan/datasets/<group>/<input_id>/<filename>` endpoint will return a raw
string on GCS-required files and on any path typo, bypassing `ApiError` promotion in the frontend.

### 3. Worker Uses a Completely Different Firestore Error Shape

The worker endpoint (`/internal/jobs/execute/<job_id>`) never returns JSON — it returns empty
strings with HTTP status codes 200/403/500. Errors are written to Firestore via `fail_job()` using
`build_error_data()` from `utils/error_handler.py`, which produces:

```json
{
  "code": "LLM_MAX_TOKENS",
  "message": "...",
  "user_hint": "...",
  "retryable": false,
  "detail": "..."
}
```

This is **structurally different** from the SP2 `ErrorDetail` the frontend types expect:

```json
{
  "code": "...",
  "message": "...",
  "details": "...",
  "timestamp": "...",
  "path": null
}
```

Key field-level differences:
- `user_hint` (Firestore) vs absent (SP2 HttpErrorDetail)
- `retryable` (Firestore) vs absent (SP2)
- `detail` singular (Firestore) vs `details` plural (SP2)
- `timestamp` and `path` (SP2) vs absent (Firestore)

The frontend `CarePlanJobPage.tsx` lines 405-411 patch over this with `??` chaining on untyped
`errData`, but the Firestore error_data dict has no TypeScript type.

### 4. `jobs.ts` Drops Structured Error Details for Highest-Traffic Endpoints

`frontend/src/api/jobs.ts` uses raw `authenticatedFetch` (not `authenticatedFetchJson`) for both
`createCarePlanJob` (line 22) and `createBatchJobs` (line 33). When the server returns an SP2
error envelope, the frontend only reads `.text()` and throws a plain `Error` with the raw JSON
string as the message. The typed `ApiError` with `code`, `details`, and `requestId` is never
constructed. `CarePlanPage.tsx` then displays `err.message` (the raw JSON string) in the error box.

### 5. Swallowed Errors — Not Surfaced to User

**Backend (legitimate degradation but undocumented):**
- `care_plan.py:195` — PDF merge failure caught, processing continues silently.
- `care_plan.py:286-288` — Term detection outer exception caught, empty terms used silently.
- `care_plan.py:329-331` — Clarify-actions step failure caught, falls back to simplified text.

**Frontend (user never sees the failure):**
- `CarePlanJobPage.tsx:64-79` (`handleSaveComment`) — `catch {}` block is completely empty; if
  the save fails the note area stays open but the user is not told anything.
- `CarePlanJobPage.tsx:128` — `updateCarePlanGrading(id, grading).catch(() => {})` — grading
  persistence failures are silently ignored (fire-and-forget with `.catch(() => {})`).
- `CarePlanJobPage.tsx:147-149` (`handleToggleShare`) — error only goes to `console.error`;
  no user-visible feedback if share toggle fails.

### 6. HTTP Status Code Inconsistency on Datasets Route

`datasets.py:29` returns 503 (Service Unavailable) for an unimplemented code path. This is the
wrong code — 501 (Not Implemented) or 404 would be more accurate and less alarming to monitoring
systems. More importantly, 503 is the same code used for Vertex AI availability failures
(`VERTEX_SERVICE_UNAVAILABLE`), polluting health dashboards.

### 7. Worker Uses Root-Level Pipeline Error Catalog, Not SP2 Catalog

`routes/worker.py:21` does `from error_codes import ErrorCode as PipelineErrorCode`, referencing
`backend/error_codes.py` (pipeline catalog with `EMPTY_DOCUMENT`, `JOB_TIMEOUT`, `UNKNOWN_ERROR`,
etc.). The public API routes reference `utils/error_codes.py` (SP2 catalog with `UNAUTHORIZED`,
`RESOURCE_NOT_FOUND`, etc.). The two catalogs have overlapping code names (`JOB_TIMEOUT` exists in
both, `UNSUPPORTED_FILE_TYPE` exists in both but with different field structures) and diverging
semantics. A developer working on the worker cannot use SP2 error codes without importing from
a different module, and vice versa.

---

## Missing Pieces

1. **No TypeScript type for Firestore `error_data`**: `CarePlanJobPage.tsx` reads `jobDoc.error_data`
   as untyped (`any`-equivalent). There is no `FirestoreErrorData` interface that covers the pipeline
   catalog shape (`user_hint`, `retryable`, `detail`).

2. **No React error boundary**: Neither `CarePlanPage.tsx` nor `CarePlanJobPage.tsx` is wrapped in a
   `<ErrorBoundary>` component. An uncaught render-time exception in these trees will white-screen
   the app with no graceful fallback or user message.

3. **No Athena-specific error codes in either registry**: The SP2 catalog (`utils/error_codes.py`)
   and the pipeline catalog (`backend/error_codes.py`) have zero Athena-specific codes. SP3 Athena
   integration will need at minimum: `ATHENA_AUTH_FAILED`, `ATHENA_PATIENT_NOT_FOUND`,
   `ATHENA_RATE_LIMITED`, `ATHENA_UNAVAILABLE`, `ATHENA_INVALID_RESPONSE`. Without them, all
   Athena errors will surface as `INTERNAL_ERROR` or `UNKNOWN_ERROR` with no actionable user
   message and no retryability signal.

4. **`get_dataset_file_route` has no `make_error_response()` wrapping at all**: The entire endpoint
   (`datasets.py:17-33`) uses ad-hoc error responses and does not call `make_error_response()` even
   once. If this route is extended (e.g., for GCS-backed dataset browsing in Athena integration),
   the ad-hoc pattern will propagate.

5. **No global Flask exception handler** beyond the 404/500 handlers: Unexpected exceptions inside
   blueprints that are not caught by route try/except blocks will not be serialized as `ApiResponse`.
   Flask's default 500 handler fires, but it delegates to `internal_error()` in `app.py` which does
   return the SP2 shape — this is actually covered, but only for unhandled 500s; exceptions that
   produce 4xx would not be caught.

6. **`authenticatedFetchJson` vs `authenticatedFetch` split is implicit**: There is no documented
   rule for which client function to use. `savedOutputs.ts` correctly uses `authenticatedFetchJson`
   for reads and `authenticatedFetch` for mutations (by design, to avoid parsing empty bodies), but
   `jobs.ts` uses `authenticatedFetch` for POST operations that do return error JSON. This is
   inconsistent and undocumented.

---

## Assessment

**YES — this needs a design pass before Athena work begins.**

The core problem is not that the codebase is broken today; most user-facing paths work because
`CarePlanJobPage` handles both error shapes with `??` fallbacks, and the public API routes are
mostly consistent. The problem is architectural: two `error_codes.py` files, two
`make_error_response()` functions, two Firestore vs HTTP error shapes, and an untyped Firestore
error_data dict create a pattern where every new feature (especially Athena, which crosses the
API/worker boundary) will replicate the confusion.

A design pass should define: (1) a single authoritative error catalog that covers both SP2 HTTP
errors and pipeline/Athena errors; (2) which error shape is used at each layer boundary (HTTP
response vs Firestore document vs SSE stream); (3) a typed `FirestoreErrorData` interface on the
frontend; and (4) a migration plan for the deprecated/ad-hoc routes in `datasets.py`. Without this,
SP3 Athena errors will arrive at the frontend as `UNKNOWN_ERROR` or raw JSON strings.

---

## Raw Notes Per File

### `backend/models/errors.py`
Clean SP2 Pydantic models: `ErrorDetail`, `ApiResponse`, `StatusEnum`. Well-documented. No issues.

### `backend/utils/error_codes.py`
SP2 error catalog + `make_error_response()` → `ApiResponse`. Used by all public HTTP routes.
`ErrorCode` StrEnum covers auth, resource, input, pipeline, batch, and general errors.
Missing: Athena codes, GCS-specific codes beyond `DATASET_DOWNLOAD_ERROR`.

### `backend/error_codes.py` (ROOT LEVEL)
Separate pipeline catalog used by worker and `utils/error_handler.py`. Has `ErrorInfo` dataclass
with `user_hint`, `retryable`, `http_status`. Covers LLM FinishReason variants, Vertex AI API
errors, and processing errors. `JOB_TIMEOUT` overlaps with SP2 catalog. Zero Athena codes.

### `backend/utils/error_handler.py`
Logic layer over root `error_codes.py`. Provides `JunoError`, `classify_vertex_exception`,
`classify_finish_reason`, `make_error_response()` (returns `(dict, int)` — naming collision with
SP2 function), `build_error_data()`, `build_error_data_from_exc()`, `handle_exception()`.
`make_error_response()` here is never used by any Flask route — it exists as dead API surface.

### `backend/app.py`
Flask app bootstrap. 404/500 handlers correctly use SP2 `make_error_response()`. Health check and
root endpoint use raw `jsonify` — acceptable for non-domain endpoints. Session ID middleware is
clean.

### `backend/utils/firebase.py`
`verify_firebase_token` and `require_admin` decorators correctly use SP2 `make_error_response()`.
`get_owned_doc_or_403()` helper correctly returns SP2 error tuples. `fail_job()` writes Firestore
error_data (shape from `build_error_data()`), not SP2 shape — this is the root of the cross-layer
shape split.

### `backend/routes/care_plan.py`
Deprecated SSE endpoint (line 53): ad-hoc `jsonify({"error": "..."})` at 410 — minor, deprecated.
`_sse_error()` uses SP2 `make_error_response()` to build SSE payloads — correct within SSE.
`_sse_error_rich()` uses `build_error_data_from_exc()` — writes pipeline catalog shape into SSE.
Worker then reads this SSE stream and passes the dict to `fail_job()`. This is the bridge between
the two error shapes; it works but is undocumented.
Several pipeline steps swallow exceptions gracefully (lines 195, 286-288, 329-331).

### `backend/routes/batch_jobs.py`
Fully SP2 compliant. All error returns use `make_error_response().to_dict()`. Success returns bare
`jsonify({"batch_run_id": ..., "job_ids": ...})` at 202 — acceptable (not an error path).

### `backend/routes/batch.py`
Deprecated SSE batch endpoint (line 22): ad-hoc `jsonify({"error": "..."})` at 410 — minor.
`_resolve_requested_runs()` raises `ValueError`/`FileNotFoundError` — correctly caught by callers.

### `backend/routes/worker.py`
Does NOT use SP2 `ApiResponse` — returns `"", 200/403/500` (empty string bodies).
Uses root-level `error_codes.py` (`PipelineErrorCode`). Correctly calls `build_error_data()` and
`build_error_data_from_exc()` for Firestore writes. HTTP contract is intentionally minimal
(Cloud Tasks only needs the status code), so empty bodies are appropriate — but this means the
worker is on a completely separate error contract from the public API.

### `backend/routes/datasets.py`
Two live ad-hoc error responses (lines 29, 31) — `jsonify({"error": "..."})`. No use of
`make_error_response()` anywhere in this file. Status 503 for unimplemented feature is wrong
(should be 501 or 404).

### `backend/routes/grading.py`
Fully SP2 compliant. All error paths use `make_error_response().to_dict()` with correct codes and
400 status codes. `_score_safe()` swallows scoring exceptions (acceptable graceful degradation).

### `backend/routes/saved_outputs.py`
Fully SP2 compliant. All error paths use `make_error_response().to_dict()`. GCS exception at line
229 handled with `INTERNAL_ERROR` at 500 — correct.

### `backend/routes/admin.py`
No error handling beyond `@require_admin` decorator. No try/except. Any Firestore failure would
bubble up as an unhandled 500 — covered by global handler but loses structured context.

### `backend/routes/care_plan_jobs.py`
Fully SP2 compliant. `ValueError`/`FileNotFoundError` from `_resolve_input_for_job` correctly
caught and returned as `INPUT_VALIDATION_ERROR` at 400. Enqueue failures use `INTERNAL_ERROR` at 500.

### `frontend/src/types/errors.ts`
`ApiErrorDetail` matches SP2 `ErrorDetail` field-for-field (code, message, details plural,
timestamp, path). `ApiError` class is well-structured. No type for Firestore error_data shape.

### `frontend/src/api/apiClient.ts`
`authenticatedFetchJson()` correctly promotes SP2 error envelopes to `ApiError`. Falls back to
plain `Error` for non-SP2 error bodies. Clean.

### `frontend/src/api/jobs.ts`
PROBLEM: Uses raw `authenticatedFetch` for both `createCarePlanJob` and `createBatchJobs`. SP2
error bodies are read as `.text()` and thrown as plain `Error`, losing all structured fields.

### `frontend/src/api/datasets.ts`
Uses raw `authenticatedFetch`. Errors are thrown as plain `Error` with status code string only.
The ad-hoc `{"error": "..."}` from the backend would never be promoted to `ApiError` here anyway.

### `frontend/src/api/savedOutputs.ts`
Mixed: `listSavedOutputs()` and `getSavedOutput()` and `getInputPdfUrl()` use `authenticatedFetchJson`
(correct). Mutation helpers (`renameSavedOutput`, `updateJobComment`, `updateCarePlanNote`,
`updateCarePlanGrading`, `shareOutput`, `deleteSavedOutput`) use raw `authenticatedFetch` and throw
plain `Error` on failure — acceptable since these return empty bodies on success, but error details
are still lost.

### `frontend/src/pages/care-plan/CarePlanPage.tsx`
Catches `createCarePlanJob` and `createBatchJobs` errors and sets `error` state. Because `jobs.ts`
uses raw fetch, the `err.message` shown in the error box will be a raw JSON string like
`'{"status":"error","error":{...}}'` rather than a human-readable message.

### `frontend/src/pages/care-plan/CarePlanJobPage.tsx`
Handles both SP2 and Firestore error_data shapes via `??` chaining (lines 405-411). No TypeScript
type for `errData`. Three swallowed errors (handleSaveComment, updateCarePlanGrading, handleToggleShare).
No error boundary wrapping the component tree.
