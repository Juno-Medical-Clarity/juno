# Tasks: SP4 — Unified Error Control Model

**Sub-project:** SP4  
**Branch:** `athena_health_part1`  
**PRD source:** `docs/agent_files/tasks/2026-06-27/04-error-control-model/PRD.md`  
**Fresh authoring** — no prior TASKS.md existed.

---

### Task 1 — Update `ErrorDetail` and `ApiResponse` in `backend/models/errors.py`

**Traced to PRD §4a**

- **Files:** `/root/projects/juno/backend/models/errors.py`
- **Changes:** Update the `ErrorDetail` class:
  - Change `details: str = ""` to `details: Optional[str] = None`
  - Add `user_hint: Optional[str] = None` after `path`
  - Add `retryable: bool = False` after `user_hint`
  - Ensure `from typing import Any, Optional` is imported

  Before:
  ```python
  class ErrorDetail(JsonModel):
      code: str
      message: str
      details: str = ""
      timestamp: str
      path: Optional[str] = None
  ```

  After:
  ```python
  class ErrorDetail(JsonModel):
      code: str
      message: str
      details: Optional[str] = None
      timestamp: str
      path: Optional[str] = None
      user_hint: Optional[str] = None     # new — from error_handler.py's Firestore shape
      retryable: bool = False             # new — from error_handler.py's Firestore shape
  ```

  `ApiResponse` does not need changes.

- **Acceptance criteria:**
  - `python -c "from models.errors import ErrorDetail; e = ErrorDetail(code='X', message='Y', timestamp='Z'); assert e.details is None; assert e.user_hint is None; assert e.retryable is False; print('OK')"` (run from `backend/`) exits 0 and prints `OK`.
  - `python -c "from models.errors import ErrorDetail; e = ErrorDetail(code='X', message='Y', timestamp='Z', user_hint='Try again', retryable=True); assert e.user_hint == 'Try again'; assert e.retryable is True; print('OK')"` exits 0 and prints `OK`.

---

### Task 2 — Update `make_error_response()` in `backend/utils/error_codes.py`

**Traced to PRD §4b**

- **Files:** `/root/projects/juno/backend/utils/error_codes.py`
- **Changes:** Add `user_hint` and `retryable` kwargs to `make_error_response()` and pass them through to `ErrorDetail`. Also convert empty `details` string to `None`:

  Before (signature only):
  ```python
  def make_error_response(
      code: ErrorCode,
      path: str | None = None,
      details_vars: dict | None = None,
      requestId: str | None = None,
  ) -> ApiResponse:
  ```

  After:
  ```python
  def make_error_response(
      code: ErrorCode,
      path: str | None = None,
      details_vars: dict | None = None,
      requestId: str | None = None,
      user_hint: str | None = None,
      retryable: bool = False,
  ) -> ApiResponse:
  ```

  In the body, update the `ErrorDetail(...)` constructor call to pass the new fields and convert empty details to None:
  ```python
  error_detail = ErrorDetail(
      code=code.value,
      message=message,
      details=details or None,        # convert empty string to None
      timestamp=timestamp,
      path=path,
      user_hint=user_hint,
      retryable=retryable,
  )
  ```

- **Acceptance criteria:**
  - `python -c "from utils.error_codes import make_error_response, ErrorCode; r = make_error_response(ErrorCode.PIPELINE_ERROR, user_hint='Try again', retryable=True); assert r.error.user_hint == 'Try again'; assert r.error.retryable is True; print('OK')"` (run from `backend/`) exits 0 and prints `OK`.
  - `python -c "from utils.error_codes import make_error_response, ErrorCode; r = make_error_response(ErrorCode.PIPELINE_ERROR); assert r.error.retryable is False; assert r.error.user_hint is None; print('OK')"` exits 0 and prints `OK`.

---

### Task 3 — Add Athena error codes to `backend/utils/error_codes.py`

**Traced to PRD §4c**

- **Files:** `/root/projects/juno/backend/utils/error_codes.py`
- **Changes:**

  Add to the `ErrorCode` StrEnum under a new `# Athena Health` section (after existing codes):
  ```python
  # Athena Health
  ATHENA_AUTH_FAILED       = "ATHENA_AUTH_FAILED"
  ATHENA_API_ERROR         = "ATHENA_API_ERROR"
  ATHENA_RATE_LIMIT_ERROR  = "ATHENA_RATE_LIMIT_ERROR"
  ATHENA_PATIENT_NOT_FOUND = "ATHENA_PATIENT_NOT_FOUND"
  ATHENA_TIMEOUT           = "ATHENA_TIMEOUT"
  ```

  Add to `_REGISTRY` under a new `# Athena Health` comment:
  ```python
  # Athena Health
  ErrorCode.ATHENA_AUTH_FAILED:       ("Athena Health authentication failed",          "OAuth2 token request failed: {detail}"),
  ErrorCode.ATHENA_API_ERROR:         ("Athena Health API error",                      "Athena API returned an error for {athena_api_path}: {detail}"),
  ErrorCode.ATHENA_RATE_LIMIT_ERROR:  ("Athena Health rate limit exceeded",            "Rate limit hit on {athena_api_path}; retry after {retry_after}s"),
  ErrorCode.ATHENA_PATIENT_NOT_FOUND: ("Athena Health patient not found",              "No patient found for practiceId={practice_id} patientId={patient_id}"),
  ErrorCode.ATHENA_TIMEOUT:           ("Athena Health API request timed out",          "Request to {athena_api_path} exceeded the timeout of {timeout_s}s"),
  ```

- **Acceptance criteria:**
  - `python -c "from utils.error_codes import ErrorCode, _REGISTRY; assert ErrorCode.ATHENA_AUTH_FAILED in _REGISTRY; assert ErrorCode.ATHENA_TIMEOUT in _REGISTRY; print('OK')"` (run from `backend/`) exits 0 and prints `OK`.
  - `python -c "from utils.error_codes import make_error_response, ErrorCode; r = make_error_response(ErrorCode.ATHENA_AUTH_FAILED, '/test'); assert r.error.code == 'ATHENA_AUTH_FAILED'; print('OK')"` exits 0 and prints `OK`.

---

### Task 4 — Add 405 error handler in `backend/app.py`

**Traced to PRD §4d**

- **Files:** `/root/projects/juno/backend/app.py`
- **Changes:** Add a `method_not_allowed` handler between the existing `not_found` (404) and `internal_error` (500) handlers. The new handler:

  ```python
  @app.errorhandler(405)
  def method_not_allowed(error):
      return make_error_response(
          ErrorCode.ENDPOINT_NOT_FOUND,
          request.path,
          {"method": request.method, "path": request.path},
      ).to_dict(), 405
  ```

  No imports need to change — `make_error_response`, `ErrorCode`, and `request` are already imported in `app.py`.

- **Acceptance criteria:**
  - `curl -X GET http://localhost:5000/care_plan/jobs` (a POST-only route) returns a JSON body with `"status": "error"` and HTTP 405 (requires the server to be running).
  - Alternatively: write a quick Flask test client test that calls a POST-only route with GET and asserts `response.status_code == 405` and `response.json["status"] == "error"`.

---

### Task 5 — Create `backend/utils/pipeline_errors.py`

**Traced to PRD §4b, §4f**

- **Files:** `/root/projects/juno/backend/utils/pipeline_errors.py` (new file)
- **Changes:** Move the following from `backend/utils/error_handler.py` to this new file (copy the exact implementations):
  - `JunoError` class
  - `classify_vertex_exception()`
  - `classify_finish_reason()`
  - `_classify_exc()`
  - `build_error_data()`
  - `build_error_data_from_exc()`
  - `handle_exception()`

  Additionally, update `build_error_data()` to use `"details"` (plural) and add a `"timestamp"` field:

  Before (in error_handler.py):
  ```python
  def build_error_data(error_code: ErrorCode, detail: str = "") -> dict:
      info = ERROR_CATALOG[error_code]
      return {
          "code": info.code,
          "message": info.message,
          "user_hint": info.user_hint,
          "retryable": info.retryable,
          "detail": detail or None,
      }
  ```

  After (in pipeline_errors.py):
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
          "timestamp": datetime.now(timezone.utc).isoformat(),  # new field
      }
  ```

  Ensure all necessary imports are present in `pipeline_errors.py` (copy imports from `error_handler.py` as needed, including `datetime`, `timezone`, `ERROR_CATALOG`, `ErrorCode`, etc.).

- **Acceptance criteria:**
  - `python -c "from utils.pipeline_errors import JunoError, build_error_data, build_error_data_from_exc, handle_exception; print('OK')"` (run from `backend/`) exits 0 and prints `OK`.
  - `python -c "from utils.pipeline_errors import build_error_data; from error_codes import ErrorCode; r = build_error_data(ErrorCode.JOB_TIMEOUT); assert 'timestamp' in r; assert 'details' in r; assert 'detail' not in r; print('OK')"` exits 0 and prints `OK`.

---

### Task 6 — Delete `backend/utils/error_handler.py`

**Traced to PRD §4b (Q1 resolved)**

- **Files:** `/root/projects/juno/backend/utils/error_handler.py` (delete)
- **Changes:** Delete the file. This is safe only after Task 5 is complete and Task 7 has migrated all import sites.

  ```bash
  git rm backend/utils/error_handler.py
  ```

  Or simply delete the file from the filesystem — it will be staged for deletion in the commit.

- **Acceptance criteria:**
  - `ls /root/projects/juno/backend/utils/error_handler.py` returns a "no such file" error.
  - `python -c "from utils.pipeline_errors import build_error_data; print('OK')"` (run from `backend/`) still exits 0.

---

### Task 7 — Migrate import sites for pipeline_errors

**Traced to PRD §4b**

- **Files:**
  - `/root/projects/juno/backend/routes/worker.py` (line 22)
  - `/root/projects/juno/backend/routes/care_plan.py` (line 37)
- **Changes:**

  In `worker.py`, change:
  ```python
  from utils.error_handler import build_error_data, build_error_data_from_exc
  ```
  To:
  ```python
  from utils.pipeline_errors import build_error_data, build_error_data_from_exc
  ```

  In `care_plan.py`, change:
  ```python
  from utils.error_handler import build_error_data_from_exc
  ```
  To:
  ```python
  from utils.pipeline_errors import build_error_data_from_exc
  ```

  Note: The line numbers (22 and 37) are approximate — search for the `from utils.error_handler import` pattern in each file.

- **Acceptance criteria:**
  - `grep -r "error_handler" /root/projects/juno/backend/routes/` returns no matches.
  - `python -c "import sys; sys.path.insert(0, 'backend'); from routes.worker import *; print('OK')"` (or equivalent import check) does not raise `ImportError`.

---

### Task 8 — Fix `datasets.py` bare jsonify calls

**Traced to PRD §4e**

- **Files:** `/root/projects/juno/backend/routes/datasets.py`
- **Changes:** Replace 2 bare `jsonify({"error": "..."})` calls with `make_error_response()`.

  First, add the import for `make_error_response` and `ErrorCode` at the top of `datasets.py`:
  ```python
  from utils.error_codes import make_error_response, ErrorCode
  ```

  Then replace the error responses in `get_dataset_file_route`:

  | Before | After |
  |---|---|
  | `return jsonify({"error": "On-demand GCS fetch not yet implemented (SP2)"}), 503` | `return make_error_response(ErrorCode.DATASET_DOWNLOAD_ERROR, request.path, {"group": group, "input_id": input_id, "detail": "GCS fetch not yet implemented (SP2)"}).to_dict(), 503` |
  | `return jsonify({"error": "Not found"}), 404` | `return make_error_response(ErrorCode.DATASET_NOT_FOUND, request.path, {"group": group, "input_id": input_id}).to_dict(), 404` |

- **Acceptance criteria:**
  - `grep -n 'jsonify({"error"' /root/projects/juno/backend/routes/datasets.py` returns no matches.
  - `GET /care_plan/datasets/nonexistent-group/0001/question.txt` returns a JSON body with `"status": "error"` and `"error": {"code": "DATASET_NOT_FOUND", ...}`.

---

### Task 9 — Update `frontend/src/types/errors.ts`

**Traced to PRD §4g**

- **Files:** `/root/projects/juno/frontend/src/types/errors.ts`
- **Changes:** Update `ApiErrorDetail` interface, `ApiError` class, and add `FirestoreJobError` interface.

  Update `ApiErrorDetail` — add `user_hint` and `retryable`, relax `details` to nullable:
  ```typescript
  export interface ApiErrorDetail {
    code: string;
    message: string;
    details: string | null;
    timestamp: string;
    path: string | null;
    user_hint: string | null;    // new — was absent
    retryable: boolean;          // new — was absent
  }
  ```

  Update `ApiError` class — add `userHint` and `retryable` fields:
  ```typescript
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
  ```

  Add `FirestoreJobError` interface (after `ApiError`):
  ```typescript
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
  ```

  Keep existing `ApiErrorResponse`, `ApiSuccessResponse`, `ApiResponse`, `ApiStatus` unchanged.

- **Acceptance criteria:**
  - `npx tsc --noEmit` (run from `frontend/`) exits 0 with no type errors.
  - `FirestoreJobError` is exported and importable.
  - `ApiError` has `userHint` and `retryable` properties.

---

### Task 10 — Migrate `jobs.ts` to `authenticatedFetchJson`

**Traced to PRD §4i**

- **Files:** `/root/projects/juno/frontend/src/api/jobs.ts`
- **Changes:** Switch `createCarePlanJob` and `createBatchJobs` from raw `authenticatedFetch` to `authenticatedFetchJson`.

  Update the import:
  ```typescript
  // Before:
  import { authenticatedFetch } from './apiClient';

  // After:
  import { authenticatedFetchJson } from './apiClient';
  ```

  Replace `createCarePlanJob`:
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

  Replace `createBatchJobs`:
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

- **Acceptance criteria:**
  - `grep -n "authenticatedFetch[^J]" /root/projects/juno/frontend/src/api/jobs.ts` returns no matches (no raw `authenticatedFetch` calls remain).
  - `npx tsc --noEmit` (run from `frontend/`) exits 0.

---

### Task 11 — Type `jobDoc.error_data` as `FirestoreJobError | null`

**Traced to PRD §4g, Q6**

- **Files:** Find the file where `JobDoc` TypeScript type is defined (likely in `frontend/src/types/` or `frontend/src/api/`). Search: `grep -rn "error_data" /root/projects/juno/frontend/src/`.
- **Changes:** Update the `error_data` field in the `JobDoc` type from `any` (or untyped) to `FirestoreJobError | null`.

  Import `FirestoreJobError` at the top of the file:
  ```typescript
  import type { FirestoreJobError } from '../types/errors';
  ```
  (adjust the import path based on file location)

  Then change:
  ```typescript
  error_data?: any;
  ```
  To:
  ```typescript
  error_data?: FirestoreJobError | null;
  ```

- **Acceptance criteria:**
  - `npx tsc --noEmit` (run from `frontend/`) exits 0.
  - `grep -n "error_data" /root/projects/juno/frontend/src/` shows `FirestoreJobError` in the type annotation (not `any`).

---

### Task 12 — Create `frontend/src/components/ErrorBoundary.tsx`

**Traced to PRD §4j**

- **Files:** `/root/projects/juno/frontend/src/components/ErrorBoundary.tsx` (new file)
- **Changes:** Create the file with the following exact content:

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

- **Acceptance criteria:**
  - `npx tsc --noEmit` (run from `frontend/`) exits 0.
  - The file exports both `ErrorBoundary` (named) and `default ErrorBoundary`.

---

### Task 13 — Wire ErrorBoundary in pages

**Traced to PRD §4j, Q4 resolved**

- **Files:**
  - `/root/projects/juno/frontend/src/App.tsx` (add global fallback)
  - The file that renders `CarePlanJobPage` (search: `grep -rn "CarePlanJobPage" /root/projects/juno/frontend/src/`)
  - The file that renders `BatchPage` (search: `grep -rn "BatchPage" /root/projects/juno/frontend/src/`)
- **Changes:**

  For per-page wrapping (in the router or wherever pages are rendered), wrap each page with `<ErrorBoundary>`:
  ```tsx
  import ErrorBoundary from '../components/ErrorBoundary';

  // Before:
  <Route path="/care-plan/:jobId" element={<CarePlanJobPage />} />

  // After:
  <Route path="/care-plan/:jobId" element={
    <ErrorBoundary>
      <CarePlanJobPage />
    </ErrorBoundary>
  } />
  ```

  Apply the same pattern for `BatchPage`.

  For the global fallback in `App.tsx`, wrap the entire app tree:
  ```tsx
  import ErrorBoundary from './components/ErrorBoundary';

  // In the render/return:
  <ErrorBoundary fallback={<div style={{ padding: '40px', textAlign: 'center' }}>A fatal error occurred. Please refresh.</div>}>
    {/* existing app content */}
  </ErrorBoundary>
  ```

- **Acceptance criteria:**
  - `npx tsc --noEmit` (run from `frontend/`) exits 0.
  - `grep -n "ErrorBoundary" /root/projects/juno/frontend/src/App.tsx` shows at least one match.

---

### Task 14 — Backend tests

**Traced to PRD §7**

- **Files:**
  - `/root/projects/juno/backend/tests/utils/test_error_codes.py` (add or create)
  - `/root/projects/juno/backend/tests/utils/test_pipeline_errors.py` (new file)
- **Changes:**

  In `test_error_codes.py`, add these tests:
  ```python
  def test_make_error_response_includes_user_hint():
      r = make_error_response(ErrorCode.PIPELINE_ERROR, user_hint="Try again")
      assert r.error.user_hint == "Try again"

  def test_make_error_response_includes_retryable():
      r = make_error_response(ErrorCode.PIPELINE_ERROR, retryable=True)
      assert r.error.retryable is True

  def test_make_error_response_default_retryable_false():
      r = make_error_response(ErrorCode.PIPELINE_ERROR)
      assert r.error.retryable is False

  def test_make_error_response_details_none_when_empty():
      r = make_error_response(ErrorCode.PIPELINE_ERROR)
      assert r.error.details is None

  def test_athena_error_codes_registered():
      from utils.error_codes import _REGISTRY
      athena_codes = [
          ErrorCode.ATHENA_AUTH_FAILED,
          ErrorCode.ATHENA_API_ERROR,
          ErrorCode.ATHENA_RATE_LIMIT_ERROR,
          ErrorCode.ATHENA_PATIENT_NOT_FOUND,
          ErrorCode.ATHENA_TIMEOUT,
      ]
      for code in athena_codes:
          assert code in _REGISTRY, f"{code} not in _REGISTRY"
          r = make_error_response(code, "/test")
          assert r.error.code == code.value
  ```

  Create `test_pipeline_errors.py` with:
  ```python
  import pytest
  from datetime import datetime
  from utils.pipeline_errors import JunoError, build_error_data, build_error_data_from_exc
  from error_codes import ErrorCode


  def test_build_error_data_includes_timestamp():
      result = build_error_data(ErrorCode.JOB_TIMEOUT)
      assert "timestamp" in result
      # Should parse as ISO-8601
      datetime.fromisoformat(result["timestamp"])


  def test_build_error_data_uses_details_key():
      result = build_error_data(ErrorCode.JOB_TIMEOUT, detail="some detail")
      assert "details" in result
      assert "detail" not in result


  def test_build_error_data_from_exc_juno_error():
      try:
          raise JunoError(ErrorCode.LLM_MAX_TOKENS, "too big")
      except JunoError as exc:
          result = build_error_data_from_exc(exc)
      assert result["code"] == "LLM_MAX_TOKENS"
      assert result.get("user_hint") is not None
  ```

- **Acceptance criteria:**
  - `pytest backend/tests/utils/test_error_codes.py -v` (run from repo root) passes all new tests.
  - `pytest backend/tests/utils/test_pipeline_errors.py -v` (run from repo root) passes all 3 tests.

---

### Task 15 — Frontend tests

**Traced to PRD §7**

- **Files:**
  - `/root/projects/juno/frontend/src/api/__tests__/jobs.test.ts` (new file)
  - `/root/projects/juno/frontend/src/components/__tests__/ErrorBoundary.test.tsx` (new file)
- **Changes:**

  Create `jobs.test.ts`:
  ```typescript
  import { createCarePlanJob, createBatchJobs } from '../jobs';
  import { ApiError } from '../../types/errors';
  import * as apiClient from '../apiClient';

  jest.mock('../apiClient');

  const mockAuthenticatedFetchJson = apiClient.authenticatedFetchJson as jest.MockedFunction<typeof apiClient.authenticatedFetchJson>;

  describe('createCarePlanJob', () => {
    it('throws ApiError on 422', async () => {
      const err = new ApiError(
        { code: 'VALIDATION_ERROR', message: 'Invalid form', details: null, timestamp: '', path: null, user_hint: null, retryable: false },
        null
      );
      mockAuthenticatedFetchJson.mockRejectedValue(err);

      await expect(createCarePlanJob(new FormData())).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('createBatchJobs', () => {
    it('throws ApiError on 400', async () => {
      const err = new ApiError(
        { code: 'VALIDATION_ERROR', message: 'Bad request', details: null, timestamp: '', path: null, user_hint: null, retryable: false },
        null
      );
      mockAuthenticatedFetchJson.mockRejectedValue(err);

      await expect(createBatchJobs({ jobs: [] } as any)).rejects.toBeInstanceOf(ApiError);
    });
  });
  ```

  Create `ErrorBoundary.test.tsx`:
  ```typescript
  import React from 'react';
  import { render, screen } from '@testing-library/react';
  import { ErrorBoundary } from '../ErrorBoundary';

  const ThrowOnRender = () => {
    throw new Error('Test render error');
  };

  // Suppress console.error output for expected errors
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('ErrorBoundary', () => {
    it('renders fallback on render error', () => {
      render(
        <ErrorBoundary fallback={<div>fallback content</div>}>
          <ThrowOnRender />
        </ErrorBoundary>
      );
      expect(screen.getByText('fallback content')).toBeInTheDocument();
    });

    it('renders children when no error', () => {
      render(
        <ErrorBoundary>
          <div>child content</div>
        </ErrorBoundary>
      );
      expect(screen.getByText('child content')).toBeInTheDocument();
    });
  });
  ```

- **Acceptance criteria:**
  - `npx jest frontend/src/api/__tests__/jobs.test.ts` (run from repo root) passes.
  - `npx jest frontend/src/components/__tests__/ErrorBoundary.test.tsx` passes.

---

## Summary of what requires you (not a dev agent)

None — all tasks are pure code changes with no infra setup or manual steps required. See PRD §8 (Manual Intervention Required: None).
