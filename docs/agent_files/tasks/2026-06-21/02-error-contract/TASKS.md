# Tasks: Error Contract (SP2)

Read `PRD.md` in this folder first. SP2 is **Phase 1** with no dependencies — it can land immediately.

**Assumed interfaces (state up front, adapt if wrong):**
- `backend/models/base.py` provides `JsonModel` with `to_dict()` / `from_dict()` / `extra="forbid"` — all new Pydantic models subclass it.
- `backend/app.py` already sets `g.session_id` unconditionally in `before_request` (line 62) before any route or decorator runs.
- The Flask app already has `@app.errorhandler(404)` and `@app.errorhandler(500)` (lines 157–163 of `app.py`).
- SP1 and SP3 import `ApiError` from `frontend/src/types/errors.ts` — that file must be created before those sub-projects land.

---

### Task 1 — Create `backend/models/errors.py` — Pydantic wire-shape models

- **Files:** `backend/models/errors.py` *(new)*
- **Changes:**
  - Create the file with exactly the three classes from PRD §4.1:
    - `StatusEnum(str, Enum)` — five values: `"error"`, `"success"`, `"not_started"`, `"processing"`, `"completed"`.
    - `ErrorDetail(JsonModel)` — fields: `code: str`, `message: str`, `details: str = ""`, `timestamp: str`, `path: str | None = None`.
    - `ApiResponse(JsonModel)` — fields: `status: StatusEnum`, `data: dict[str, Any] | None = None`, `error: ErrorDetail | None = None`, `requestId: str | None = None`.
  - Add `from __future__ import annotations` at the top.
  - Import `StatusEnum`, `ErrorDetail`, `ApiResponse` from `.base` (already provides `JsonModel`).
  - Add a module docstring: `"""Pydantic models for the SP2 error contract wire shape."""`
- **Acceptance criteria:**
  - `python -c "from models.errors import ApiResponse, ErrorDetail, StatusEnum; print('ok')"` exits 0 from `backend/`.
  - `ApiResponse(status="error", unknown_field="x")` raises `pydantic.ValidationError` (extra="forbid" inherited from JsonModel).
  - `ErrorDetail(code="X", message="m", timestamp="t")` — `path` defaults to `None`.
  - `ApiResponse(status="success", data={"x": 1}).to_dict()["status"]` returns `"success"`.

---

### Task 2 — Update `backend/models/__init__.py` — add error model exports

- **Files:** `backend/models/__init__.py`
- **Changes:**
  - After the existing `from .base import JsonModel, VersionedModel` line, add:
    ```python
    from .errors import ApiResponse, ErrorDetail, StatusEnum
    ```
  - Add `"ApiResponse"`, `"ErrorDetail"`, `"StatusEnum"` to the `__all__` list.
  - Do not remove any existing exports.
- **Acceptance criteria:**
  - `python -c "from models import ApiResponse, ErrorDetail, StatusEnum; print('ok')"` exits 0 from `backend/`.
  - Existing test `backend/tests/models/test_exports.py` still passes (run `pytest tests/models/test_exports.py`).

---

### Task 3 — Create `backend/utils/error_codes.py` — `ErrorCode` registry and `make_error_response` helper

- **Files:** `backend/utils/error_codes.py` *(new)*
- **Changes:**
  - Create the file with exactly the content from PRD §4.2:
    - `ErrorCode(StrEnum)` — all 23 members listed in PRD §4.2, in the groupings shown (Auth, Resource, Input, Pipeline/processing, Timeout, Batch, Grading/saving, General).
    - `_REGISTRY: dict[ErrorCode, tuple[str, str]]` — all 23 entries mapping each `ErrorCode` to `(default_message, details_template)` exactly as listed in PRD §4.2.
    - `_SafeDict(dict)` — with `__missing__` returning `f"{{{key}}}"`.
    - `_safe_format(template: str, vars: dict) -> str` — calls `template.format_map(_SafeDict(vars))`.
    - `make_error_response(code, path, details_vars, requestId) -> ApiResponse` — exactly as shown in PRD §4.2; uses `try/except RuntimeError` around `g.session_id`; logs via `logger.error("error_response", extra={...})` with all six fields.
  - Module-level `logger = logging.getLogger(__name__)`.
- **Acceptance criteria:**
  - `python -c "from utils.error_codes import make_error_response, ErrorCode; print('ok')"` exits 0 from `backend/`.
  - Calling `make_error_response(ErrorCode.TIMEOUT, path=None)` outside a Flask context (no `g`) does not raise; returns `ApiResponse` with `requestId=None`.
  - `make_error_response(ErrorCode.RESOURCE_NOT_FOUND, "/test", {"collection": "c", "doc_id": "d"}).error.details` contains `"c"` and `"d"`.
  - `make_error_response(ErrorCode.RESOURCE_NOT_FOUND, "/test")` — no `details_vars` — does not raise a `KeyError`; unfilled placeholders remain as `{collection}` etc.

---

### Task 4 — Update `backend/utils/firebase.py` — structured errors in `verify_firebase_token` and `get_owned_doc_or_403`

- **Files:** `backend/utils/firebase.py`
- **Changes:**
  1. Add imports at the top of the file (after existing imports):
     ```python
     from utils.error_codes import make_error_response, ErrorCode
     ```
  2. In `verify_firebase_token` (lines 51–83), replace the three `jsonify({"error": ...})` returns with `make_error_response(...).to_dict()` per the PRD §4.4 table:
     - No header → `make_error_response(ErrorCode.MISSING_AUTH_HEADER, request.path).to_dict(), 401`
     - Malformed header (`len(parts) != 2 or parts[0] != 'Bearer'`) → `make_error_response(ErrorCode.MALFORMED_AUTH_HEADER, request.path).to_dict(), 401`
     - `except Exception as e` → `make_error_response(ErrorCode.UNAUTHORIZED, request.path, {"detail": str(e)}).to_dict(), 401`
     - Remove the `jsonify(...)` wrapper from all three — `make_error_response().to_dict()` returns a plain dict; Flask accepts `(dict, status_code)` directly.
  3. Change the `get_owned_doc_or_403` signature (line 86) to add `path: str | None = None`:
     ```python
     def get_owned_doc_or_403(db, collection: str, doc_id: str, user_id: str, path: str | None = None):
     ```
  4. In `get_owned_doc_or_403`, replace the two `jsonify(...)` returns:
     - Not found → `make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path, {"collection": collection, "doc_id": doc_id}).to_dict(), 404`
     - Forbidden → `make_error_response(ErrorCode.RESOURCE_FORBIDDEN, path, {"collection": collection, "doc_id": doc_id}).to_dict(), 403`
  5. **Update all call-sites of `get_owned_doc_or_403`** to pass `path=request.path`:
     - `backend/routes/saved_outputs.py` — four call-sites (lines 64, 83, 104, 135): add `path=request.path` to each.
     - `backend/routes/grading.py` — one call-site (line 33): add `path=request.path`.
- **Acceptance criteria:**
  - `pytest tests/utils/test_firebase.py` passes.
  - A request with no Authorization header to any protected endpoint returns JSON with `{"status": "error", "error": {"code": "MISSING_AUTH_HEADER", ...}}` and HTTP 401.
  - A request with `Authorization: NotBearer token` returns `{"error": {"code": "MALFORMED_AUTH_HEADER", ...}}` and HTTP 401.
  - `pytest tests/routes/test_care_plan_auth.py` passes.

---

### Task 5 — Update `backend/app.py` — structured global error handlers

- **Files:** `backend/app.py`
- **Changes:**
  - Add import near the top (after existing imports):
    ```python
    from utils.error_codes import make_error_response, ErrorCode
    ```
  - Replace the `not_found` handler (lines 157–159):
    ```python
    @app.errorhandler(404)
    def not_found(error):
        return make_error_response(
            ErrorCode.ENDPOINT_NOT_FOUND,
            request.path,
            {"method": request.method, "path": request.path},
        ).to_dict(), 404
    ```
  - Replace the `internal_error` handler (lines 161–163):
    ```python
    @app.errorhandler(500)
    def internal_error(error):
        return make_error_response(
            ErrorCode.INTERNAL_ERROR,
            request.path,
        ).to_dict(), 500
    ```
- **Acceptance criteria:**
  - `GET /nonexistent-path` returns `{"status": "error", "error": {"code": "ENDPOINT_NOT_FOUND", ...}}` with HTTP 404.
  - `pytest tests/routes/test_health_route.py` still passes (health endpoint unaffected).

---

### Task 6 — Update `backend/routes/grading.py` — structured error responses

- **Files:** `backend/routes/grading.py`
- **Changes:**
  - Add import:
    ```python
    from utils.error_codes import make_error_response, ErrorCode
    ```
  - Replace `jsonify({"error": "No source text found in saved output"}), 400` (line 44):
    ```python
    make_error_response(
        ErrorCode.NO_SOURCE_TEXT,
        request.path,
        {"saved_id": saved_id},
    ).to_dict(), 400
    ```
  - Replace `jsonify({"error": "Provide either 'saved_id' or 'text'"}), 400` (line 58):
    ```python
    make_error_response(
        ErrorCode.INPUT_VALIDATION_ERROR,
        request.path,
        {"field": "text", "reason": "provide either 'saved_id' or 'text'"},
    ).to_dict(), 400
    ```
  - Remove `from flask import Blueprint, jsonify, request` → change to `from flask import Blueprint, request` (drop `jsonify` if no longer used; keep `jsonify` only if the success `return jsonify({"grading": ...})` lines stay as-is — they do, so keep `jsonify` in the import).
- **Acceptance criteria:**
  - `POST /care_plan/grade` with `{}` body (no `saved_id`, no `text`) returns `{"status": "error", "error": {"code": "INPUT_VALIDATION_ERROR", ...}}` and HTTP 400.
  - `pytest tests/routes/test_grading_route.py` passes.

---

### Task 7 — Update `backend/routes/saved_outputs.py` — structured error responses

- **Files:** `backend/routes/saved_outputs.py`
- **Changes:**
  - Add import:
    ```python
    from utils.error_codes import make_error_response, ErrorCode
    ```
  - In `rename_saved` (lines 77–95), replace:
    - `jsonify({'error': 'name is required'}), 400` →
      ```python
      make_error_response(
          ErrorCode.INPUT_VALIDATION_ERROR,
          f"/care_plan/saved/{doc_id}",
          {"field": "name", "reason": "required"},
      ).to_dict(), 400
      ```
    - `jsonify({'error': 'name too long (max 200 chars)'}), 400` →
      ```python
      make_error_response(
          ErrorCode.INPUT_VALIDATION_ERROR,
          f"/care_plan/saved/{doc_id}",
          {"field": "name", "reason": "max 200 chars"},
      ).to_dict(), 400
      ```
  - In `get_input_pdf_url` (lines 126–159), replace:
    - `jsonify({'error': 'No input PDF stored for this output'}), 404` →
      ```python
      make_error_response(
          ErrorCode.PDF_URL_UNAVAILABLE,
          f"/care_plan/saved/{doc_id}/input-pdf-url",
          {"doc_id": doc_id},
      ).to_dict(), 404
      ```
    - `jsonify({'error': f'Could not generate URL: {e}'}), 500` →
      ```python
      make_error_response(
          ErrorCode.INTERNAL_ERROR,
          f"/care_plan/saved/{doc_id}/input-pdf-url",
      ).to_dict(), 500
      ```
  - Keep `jsonify` in the import — it is still used by `list_saved`, `get_saved`, `rename_saved` (success path), `delete_saved`.
- **Acceptance criteria:**
  - `PATCH /care_plan/saved/<id>` with `{"name": ""}` returns `{"status": "error", "error": {"code": "INPUT_VALIDATION_ERROR", ...}}` and HTTP 400.
  - `GET /care_plan/saved/<id>/input-pdf-url` when no PDF is stored returns `{"status": "error", "error": {"code": "PDF_URL_UNAVAILABLE", ...}}` and HTTP 404.
  - `pytest tests/routes/test_saved_outputs_route.py` passes.

---

### Task 8 — Update `backend/routes/care_plan.py` — structured SSE errors and version check

- **Files:** `backend/routes/care_plan.py`
- **Changes:**
  1. Add imports near the top:
     ```python
     from utils.error_codes import make_error_response, ErrorCode
     ```
  2. Add `_sse_error` helper immediately after the `_sse` function definition (line 85):
     ```python
     def _sse_error(code: ErrorCode, path: str, details_vars: dict | None = None) -> str:
         resp = make_error_response(code, path=path, details_vars=details_vars)
         return _sse({"step": "error", "error_data": resp.error.to_dict()})
     ```
  3. In `create_care_plan` (lines 624–647), replace the version-check error return:
     - Old: `return {"error": f"Unknown version '{version}'"}, 400`
     - New:
       ```python
       return make_error_response(
           ErrorCode.UNKNOWN_VERSION,
           request.path,
           {"version": version, "allowed": ", ".join(Constants.ALLOWED_VERSIONS)},
       ).to_dict(), 400
       ```
  4. In `_care_plan_stream` / `run_care_plan_pipeline`, replace all `yield _sse({"step": "error", "error": ...})` calls with `yield _sse_error(...)` per the PRD §4.4 table. Exact replacements:
     - `"Failed to initialize pipeline: {e}"` (line 347 in `run_care_plan_pipeline`) → `yield _sse_error(ErrorCode.PIPELINE_INIT_ERROR, "/care_plan", {"detail": str(e)})`
     - `"Simplification failed: {exc}"` (line 396) → `yield _sse_error(ErrorCode.SIMPLIFICATION_FAILED, "/care_plan", {"detail": str(exc)})`
     - `"Structuring failed: {exc}"` (line 436) → `yield _sse_error(ErrorCode.STRUCTURING_FAILED, "/care_plan", {"detail": str(exc)})`
     - `"Pipeline error: {exc}"` (outer except in `run_care_plan_pipeline`, line 493) → `yield _sse_error(ErrorCode.PIPELINE_ERROR, "/care_plan", {"detail": str(exc)})`
     - `"Could not read input: {exc}"` (line 536 in `_care_plan_stream`) → `yield _sse_error(ErrorCode.INPUT_VALIDATION_ERROR, "/care_plan", {"field": "input", "reason": str(exc)})`
     - `"Input appears to be empty or unreadable."` (line 541) → `yield _sse_error(ErrorCode.INPUT_EMPTY, "/care_plan")`
     - `"Pipeline error: {exc}"` (outer except in `_care_plan_stream`, line 618) → `yield _sse_error(ErrorCode.PIPELINE_ERROR, "/care_plan", {"detail": str(exc)})`
     - The hardcoded inline error at line 566 (`"Pipeline result SSE is invalid..."`) — replace with `yield _sse_error(ErrorCode.PIPELINE_ERROR, "/care_plan", {"detail": "Pipeline result SSE is invalid; use the route result sentinel."})` and return.
  - **Do not** change `step: "result"` events, batch_progress events, or any success `_sse(...)` calls.
- **Acceptance criteria:**
  - `POST /care_plan` with `version=99.0` (invalid version) returns HTTP 400 JSON with `{"status": "error", "error": {"code": "UNKNOWN_VERSION", ...}}`.
  - An SSE error event produced during the pipeline has shape `{"step": "error", "error_data": {"code": "...", "message": "...", "details": "...", "timestamp": "...", "path": null}}` — the old `"error": "string"` key is gone.
  - `pytest tests/routes/test_care_plan_route.py tests/routes/test_care_plan_auth.py` passes.

---

### Task 9 — Update `backend/routes/batch.py` — structured SSE errors

- **Files:** `backend/routes/batch.py`
- **Changes:**
  1. Add imports:
     ```python
     from utils.error_codes import make_error_response, ErrorCode
     ```
  2. Add `_sse_error` helper immediately after the `_sse` function (line 25):
     ```python
     def _sse_error(code: ErrorCode, path: str, details_vars: dict | None = None) -> str:
         resp = make_error_response(code, path=path, details_vars=details_vars)
         return _sse({"step": "error", "error_data": resp.error.to_dict()})
     ```
  3. In `generate()` (inside `create_care_plan_batch`), replace top-level `yield _sse({"step": "error", ...})` calls per PRD §4.4 table:
     - `"Request body must be a JSON object"` → `yield _sse_error(ErrorCode.INPUT_VALIDATION_ERROR, "/care_plan/batch", {"field": "body", "reason": "must be a JSON object"})`
     - `f"Unknown version '{version}'"` → `yield _sse_error(ErrorCode.UNKNOWN_VERSION, "/care_plan/batch", {"version": version, "allowed": ", ".join(Constants.ALLOWED_VERSIONS)})`
     - `"Request must include selections"` → `yield _sse_error(ErrorCode.INPUT_VALIDATION_ERROR, "/care_plan/batch", {"field": "selections", "reason": "required, must be a non-empty list"})`
     - `f"Batch request exceeds maximum of {MAX_BATCH_RUNS} runs"` → `yield _sse_error(ErrorCode.BATCH_TOO_LARGE, "/care_plan/batch", {"count": total, "max_runs": MAX_BATCH_RUNS})`
  4. In the `except (FileNotFoundError, ValueError) as exc` block (line 279):
     - `yield _sse({"step": "error", "error": str(exc) or "Invalid batch selection"})` → `yield _sse_error(ErrorCode.BATCH_INVALID_SELECTION, "/care_plan/batch", {"detail": str(exc) or "Invalid batch selection"})`
  5. In the outer `except Exception as exc` (line 281):
     - `f"Batch pipeline error: {exc}"` → `yield _sse_error(ErrorCode.PIPELINE_ERROR, "/care_plan/batch", {"detail": str(exc)})`
  - **Do not** change `_batch_progress_error` — it uses `"error": string` inside a `batch_progress` event, which is a different shape (per-item progress, not a top-level SSE error). Leave it as-is.
  - The inner per-item error at line 219 (`payload.get("error") or f"Pipeline failed: ..."`) reads the old SSE error string. After Task 8, the pipeline yields `{"step": "error", "error_data": {...}}`. Update the batch error-forwarding code (lines 218–228):
    ```python
    if payload.get("step") == "error":
        error_msg = (
            (payload.get("error_data") or {}).get("message")
            or payload.get("error")
            or f"Pipeline failed: {group}/{input_id}"
        )
        yield _sse(_batch_progress_error(group, input_id, index, total, error_msg))
        result_data = None
        input_failed = True
        break
    ```
- **Acceptance criteria:**
  - `POST /care_plan/batch` with `{}` body returns SSE event `{"step": "error", "error_data": {"code": "INPUT_VALIDATION_ERROR", ...}}`.
  - `POST /care_plan/batch` with `{"selections": [], "version": "v1-2"}` returns SSE event `{"step": "error", "error_data": {"code": "INPUT_VALIDATION_ERROR", ...}}`.
  - `pytest tests/routes/test_batch_route.py` passes.

---

### Task 10 — Create `frontend/src/types/errors.ts` — TypeScript error types

- **Files:** `frontend/src/types/errors.ts` *(new)*
- **Changes:**
  - Create the file with exactly the content from PRD §4.7:
    - `export type ApiStatus`
    - `export interface ApiErrorDetail`
    - `export interface ApiErrorResponse`
    - `export interface ApiSuccessResponse<T>`
    - `export type ApiResponse<T>`
    - `export class ApiError extends Error` — with `readonly code`, `details`, `requestId`, `path` fields and the constructor shown in PRD §4.7.
  - Add the module comment: `// Mirrors backend models/errors.py — keep in sync with StatusEnum and ErrorDetail.`
- **Acceptance criteria:**
  - `npx tsc --noEmit` from `frontend/` exits 0 (no new type errors).
  - `import { ApiError, ApiErrorDetail, ApiResponse } from '../types/errors'` resolves without error in any file that imports it.
  - `new ApiError({ code: "X", message: "m", details: "d", timestamp: "t", path: null }, null).message` equals `"m"` and `.code` equals `"X"`.

---

### Task 11 — Update `frontend/src/api/apiClient.ts` — add `authenticatedFetchJson<T>`

- **Files:** `frontend/src/api/apiClient.ts`
- **Changes:**
  - Add at the top:
    ```typescript
    import type { ApiErrorResponse } from '../types/errors';
    import { ApiError } from '../types/errors';
    ```
  - Append the `authenticatedFetchJson<T>` function from PRD §4.7 **after** the existing `authenticatedFetch` function. Do not modify `authenticatedFetch`.
  - Export `authenticatedFetchJson`.
- **Acceptance criteria:**
  - `npx tsc --noEmit` from `frontend/` exits 0.
  - `authenticatedFetch` is still exported and unchanged.
  - A failed response with body `{"status":"error","error":{"code":"X","message":"m","details":"","timestamp":"t","path":"/x"},"requestId":null}` causes `authenticatedFetchJson` to throw an `ApiError` with `.code === "X"` and `.message === "m"`.
  - A failed response with a non-JSON body causes `authenticatedFetchJson` to throw a plain `Error` (not `ApiError`) with the status code in the message.

---

### Task 12 — Update `frontend/src/api/savedOutputs.ts` — switch to `authenticatedFetchJson`

- **Files:** `frontend/src/api/savedOutputs.ts`
- **Changes:**
  - Replace `import { authenticatedFetch } from './apiClient';` with:
    ```typescript
    import { authenticatedFetchJson } from './apiClient';
    ```
  - Rewrite each function to use `authenticatedFetchJson` and remove the manual `!res.ok` guard:
    - `listSavedOutputs`:
      ```typescript
      export async function listSavedOutputs(): Promise<SavedOutputMeta[]> {
        const json = await authenticatedFetchJson<{ outputs: SavedOutputMeta[] }>(
          `${API_URL}${SAVED_OUTPUTS_PATH}`,
        );
        return json.outputs;
      }
      ```
    - `getSavedOutput`:
      ```typescript
      export async function getSavedOutput(id: string): Promise<SavedOutput> {
        return authenticatedFetchJson<SavedOutput>(`${API_URL}${savedOutputPath(id)}`);
      }
      ```
    - `renameSavedOutput`:
      ```typescript
      export async function renameSavedOutput(id: string, name: string): Promise<void> {
        await authenticatedFetchJson(`${API_URL}${savedOutputPath(id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
      }
      ```
    - `deleteSavedOutput`:
      ```typescript
      export async function deleteSavedOutput(id: string): Promise<void> {
        await authenticatedFetchJson(`${API_URL}${savedOutputPath(id)}`, { method: 'DELETE' });
      }
      ```
    - `getInputPdfUrl`:
      ```typescript
      export async function getInputPdfUrl(id: string): Promise<string> {
        const json = await authenticatedFetchJson<{ url: string }>(`${API_URL}${inputPdfUrlPath(id)}`);
        return json.url;
      }
      ```
  - `SavedOutputMeta` and `SavedOutput` interface definitions stay unchanged.
- **Acceptance criteria:**
  - `npx tsc --noEmit` from `frontend/` exits 0.
  - No `!res.ok` guards remain in this file.
  - Callers that catch errors from these functions now receive an `ApiError` when the server returns a structured error body.

---

### Task 13 — Update `frontend/src/pages/care-plan/CarePlanPage.tsx` — SSE error parser

- **Files:** `frontend/src/pages/care-plan/CarePlanPage.tsx`
- **Changes:**
  1. Add import near the top (after existing imports from `../../api/apiClient`):
     ```typescript
     import { ApiError } from '../../types/errors';
     import type { ApiErrorDetail } from '../../types/errors';
     ```
  2. In the single-run SSE parser (lines 292–300), the event type definition currently includes `error?: string`. Extend it to also include `error_data?: unknown`. Update the error check at line 300:
     - Old:
       ```typescript
       if (event.error) throw new Error(event.error);
       ```
     - New:
       ```typescript
       if (event.step === 'error' && event.error_data) {
         const detail = event.error_data as ApiErrorDetail;
         throw new ApiError(detail, null);
       } else if (event.step === 'error' && event.error) {
         // fallback for legacy shape during transition window
         throw new Error(event.error as string);
       }
       ```
  3. In the batch SSE parser (lines 200–202), the `step === 'error'` check reads `event.error`. Update it the same way:
     - Old:
       ```typescript
       if (event.step === 'error') {
         throw new Error(event.error || 'Batch processing failed.');
       }
       ```
     - New:
       ```typescript
       if (event.step === 'error') {
         if (event.error_data) {
           const detail = event.error_data as ApiErrorDetail;
           throw new ApiError(detail, null);
         }
         throw new Error((event.error as string | undefined) || 'Batch processing failed.');
       }
       ```
  4. In both `catch` blocks (lines 241–244 and 322–326), update the `setError` call:
     - Old: `setError(err instanceof Error ? err.message : 'An unexpected error occurred.')`
     - New: `setError(err instanceof ApiError || err instanceof Error ? err.message : 'An unexpected error occurred.')`
     - (This is functionally equivalent since `ApiError extends Error`, but makes the intent explicit for SP3.)
  5. Update the event type inline annotation to include `error_data?: unknown` where `error?: string` appears.
  - **Do not** change the `step === 'result'` branch, the `step === 'batch_result'` branch, or any other SSE event handling. The `error` state type stays `string | null`.
- **Acceptance criteria:**
  - `npx tsc --noEmit` from `frontend/` exits 0.
  - When the backend sends `{"step": "error", "error_data": {"code": "SIMPLIFICATION_FAILED", "message": "Simplification step failed", "details": "...", "timestamp": "...", "path": null}}`, the page displays `"Simplification step failed"` in the error box (extracted from `ApiError.message`).
  - When the backend sends the legacy `{"step": "error", "error": "some string"}` (transition-window fallback), the page still displays the string.

---

### Task 14 — Write unit tests: `backend/tests/utils/test_error_codes.py`

- **Files:** `backend/tests/utils/test_error_codes.py` *(new)*
- **Changes:**
  - Create the file with all tests from PRD §7.1 and §7.2, exactly as written in the PRD:
    - `test_all_error_codes_in_registry` — every `ErrorCode` member has a `_REGISTRY` entry.
    - `test_all_registry_entries_have_message_and_template` — every entry is `(non-empty str, non-empty str)`.
    - `test_make_error_response_returns_api_response` — shape, status, code fields.
    - `test_make_error_response_fills_details_template` — `{version}` and `{allowed}` filled.
    - `test_make_error_response_handles_missing_template_vars` — no `KeyError` on partial fill.
    - `test_make_error_response_no_flask_context_does_not_raise` — `requestId` is `None`.
    - `test_make_error_response_uses_g_session_id(app_context)` — uses `g.session_id` within Flask context. Use the `app` fixture from `conftest.py` to create a test request context: `with app.test_request_context(): g.session_id = "sess-abc-123"; resp = make_error_response(...); assert resp.requestId == "sess-abc-123"`. Rename fixture parameter from `app_context` to `app` to match conftest.
    - `test_make_error_response_logs_error(caplog)` — log record at ERROR level contains `"UNAUTHORIZED"` in message or as `error_code` extra attribute.
- **Acceptance criteria:**
  - `pytest tests/utils/test_error_codes.py -v` — all tests pass, none skipped.
  - The `g.session_id` test uses the `app` fixture from `conftest.py` with a `test_request_context()` (not a raw `app_context` fixture that doesn't exist in conftest).

---

### Task 15 — Write unit tests: `backend/tests/models/test_errors.py`

- **Files:** `backend/tests/models/test_errors.py` *(new)*
- **Changes:**
  - Create the file with all tests from PRD §7.3:
    - `test_api_response_error_round_trip` — `to_dict()` produces correct keys; `ApiResponse.from_dict(d)` round-trips.
    - `test_api_response_path_is_optional` — `ErrorDetail` without `path` argument serializes `"path": None`.
    - `test_api_response_extra_field_raises` — `ApiResponse(status="error", unknown_field="x")` raises `pydantic.ValidationError`.
    - `test_status_enum_values` — the set of values equals `{"error","success","not_started","processing","completed"}`.
- **Acceptance criteria:**
  - `pytest tests/models/test_errors.py -v` — all four tests pass.

---

### Task 16 — Extend existing route tests with structured-error assertions (PRD §7.4)

- **Files:**
  - `backend/tests/routes/test_saved_outputs_route.py`
  - `backend/tests/routes/test_grading_route.py`
  - `backend/tests/routes/test_care_plan_auth.py`
- **Changes:**
  - In `test_saved_outputs_route.py`: find existing tests that assert 404 and 403 responses (the `get_owned_doc_or_403` path). Add assertions that the response body now contains `"status": "error"` and an `"error"` object with a `"code"` key. Use the `json()` / `get_json()` method on the test response. Do **not** rewrite the existing test logic — add assertions after existing `assert res.status_code == 404` / `403` lines.
  - In `test_grading_route.py`: find existing tests for 400 responses (missing text). Add assertions that `res.json["status"] == "error"` and `res.json["error"]["code"] == "INPUT_VALIDATION_ERROR"`.
  - In `test_care_plan_auth.py`: find existing tests for 401 responses. Add assertions that `res.json["status"] == "error"` and `res.json["error"]["code"]` is one of `"UNAUTHORIZED"`, `"MISSING_AUTH_HEADER"`, `"MALFORMED_AUTH_HEADER"` depending on the test case.
- **Acceptance criteria:**
  - `pytest tests/routes/test_saved_outputs_route.py tests/routes/test_grading_route.py tests/routes/test_care_plan_auth.py -v` — all pre-existing tests still pass, new assertions all pass.
  - No test files were deleted or renamed.

---

## Summary of what requires you (not a dev agent)

1. **Success response wrapper decision** (PRD §8.1): SP2 intentionally leaves all success responses in their current shape (raw `jsonify({...})`). If you later want all routes to return `{"status":"success","data":{...}}`, that is a separate scope change — say so before any dev agent starts on follow-up work. New endpoints from SP1 will use `ApiResponse` for both success and error from day one.

2. **Confirm the SSE transition shape** (PRD §8.2): Tasks 8 and 9 produce `{"step":"error","error_data":{...}}` on all SSE error events, replacing `{"step":"error","error":"..."}`. Task 13 updates the frontend SSE parser to read `error_data`. Verify the transition shape is acceptable before SP1 lands — SP1 removes SSE entirely, so the window is short.

3. **`authenticatedFetchJson` rollout scope** (PRD §8.3): Tasks 11–12 scope `authenticatedFetchJson` to `savedOutputs.ts` only. If you want `datasets.ts` or other API modules migrated now, scope those explicitly before implementation — they are not in SP2.

4. **SP1 interface contract reminder** (PRD §4.5): After SP2 lands, SP1 workers must use `make_error_response(code, path=None, requestId=None).error.to_dict()` as the `error_data` field value in Firestore job docs. The worker must **not** pass a full `ApiResponse` dict — only the inner `ErrorDetail.to_dict()` goes to Firestore. Confirm this with the SP1 implementer before SP1 begins.
