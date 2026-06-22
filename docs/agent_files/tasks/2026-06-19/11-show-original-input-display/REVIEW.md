# REVIEW: SP-11 — Show Original & Input Display Redesign

**Date:** 2026-06-21
**Status:** COMPLETE (with one fix applied)

---

## Summary

SP-11 was implemented largely correctly across all 11 tasks. One bug was found and fixed during this review. All tests now pass: 348 backend, 85 frontend.

---

## Audit Results by Area

### Backend

#### `backend/utils/firebase.py` — Task 1 (Drop `input_pdf_gcs`)
CORRECT. `save_care_plan_output` no longer has `input_pdf_gcs` parameter. The Firestore payload dict does not write an `"input_pdf_gcs"` key.

#### `backend/routes/batch.py` — Task 2
CORRECT. `input_pdf_gcs=None` kwarg removed from `save_care_plan_output` call.

#### `backend/routes/care_plan.py` — Task 3
CORRECT. `_save` closure defers `envelope.to_dict()` until after `input_model.pdf_gcs_url = gcs_uri` is set. `isinstance(input_model, FileInput)` guard is in place. `_payload_holder` pattern propagates `payload` to the outer scope correctly so the SSE result event includes `pdf_gcs_url`.

**ONE BUG FOUND AND FIXED HERE:** The module-level alias `MAX_AGGREGATE_FILE_BYTES = Constants.MAX_AGGREGATE_FILE_BYTES` was added to `care_plan.py` by a prior task (SP-12) but lines 148–149 still referenced `Constants.MAX_AGGREGATE_FILE_BYTES` directly. This meant test patches on `routes.care_plan.MAX_AGGREGATE_FILE_BYTES` had no effect, causing `test_multi_file_upload_rejects_aggregate_size_over_limit` to fail (it was getting a `result` event instead of an `error` event). **Fix applied:** changed lines 148–149 to use `MAX_AGGREGATE_FILE_BYTES` (the module-level alias) instead of `Constants.MAX_AGGREGATE_FILE_BYTES`.

#### `backend/routes/saved_outputs.py` — Task 4
CORRECT. Both `delete_saved` (line 109–112) and `get_input_pdf_url` (line 139–142) implement the tolerant fallback read:
```python
gcs_uri = (
    (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
    or data.get('input_pdf_gcs', '')
)
```
The `get_saved` endpoint no longer returns `input_pdf_gcs` in the response body (Task 4C was completed correctly).

#### `backend/models/input.py` — SP-08 dependency
CORRECT. `FileInput.pdf_gcs_url: str | None = None` is present. All four variants (`FileInput`, `TextInput`, `DocIdInput`, `BatchDatasetInput`) are in place.

### Frontend

#### `frontend/src/types/envelope.ts` — Task 5
CORRECT. Four-variant discriminated union is in place: `FileInput | TextInput | DocIdInput | BatchDatasetInput`. `FileInput.pdf_gcs_url: string | null` is present.

#### `frontend/src/api/savedOutputs.ts` — Task 6
CORRECT. `SavedOutput.input_pdf_gcs` field is removed. `getInputPdfUrl` is unchanged.

#### `frontend/src/pages/care-plan/CarePlanPage.tsx` — Task 7
CORRECT.
- `outputHasInputPdf` checks `output.input.mode === 'file' && output.input.pdf_gcs_url != null`.
- `outputHasInputText` checks both `mode === 'text'` and `mode === 'batch_dataset'` with non-empty text.
- Both helpers are exported for unit testing.
- "Show Original" button condition: `activeSavedId && result && (outputHasInputPdf(result) || outputHasInputText(result))`. Note: the `activeSavedId &&` guard is kept on the button (consistent with prior behavior), though the PRD note about removing it applied only to the SplitView render site. For text inputs, `activeSavedId` is always set when save succeeds, so this is acceptable.
- SplitView render site correctly passes `savedId={result.input.mode === 'file' ? activeSavedId : null}` and `originalText` from text/batch modes. The `activeSavedId &&` guard is correctly absent from the SplitView render condition (line 627).

#### `frontend/src/components/SplitView/SplitView.tsx` — Task 8
CORRECT. Props widened to `savedId: string | null` and `originalText: string | null`. Component conditionally fetches signed URL (PDF mode) or renders `<pre>` (text mode). Error state for both-null case is included.

#### `frontend/src/components/SplitView/SplitView.css` — Task 9
CORRECT. `.split-view-text-content` class added with `height: 100%; overflow-y: auto; padding: 16px; font-size: 0.875rem; line-height: 1.6;` plus `.split-view-text-content pre` with `margin: 0; font-family: inherit; color: var(--text-primary);`.

### Tests

#### Backend tests — Task 10
CORRECT. Tests added for:
- `test_firebase.py`: `input_pdf_gcs` kwarg rejection, payload does not contain `input_pdf_gcs`, `output_data` persisted verbatim.
- `test_saved_outputs_route.py`: 4 tolerant-read cases for `get_input_pdf_url` (new path, legacy fallback, priority, 404 when neither).
- `test_care_plan_route.py`: save block sets `input.pdf_gcs_url` in `output_data`, no `input_pdf_gcs` at doc root, SSE result also contains it.
- `test_batch_route.py`: `save_care_plan_output` called without `input_pdf_gcs`.

#### Frontend tests — Task 11
CORRECT. Tests added for:
- `src/tests/components/SplitView.test.tsx`: PDF mode (calls getInputPdfUrl, renders iframe, error state), text mode (no API call, renders pre, correct header), both-null state.
- `src/tests/pages/care-plan/CarePlanPage.test.tsx`: All 7 helper function cases for `outputHasInputPdf` and `outputHasInputText`.

---

## Fix Applied

**File:** `/root/projects/juno/backend/routes/care_plan.py` lines 148–149

Changed `Constants.MAX_AGGREGATE_FILE_BYTES` to `MAX_AGGREGATE_FILE_BYTES` (the module-level alias) so that test patches on `routes.care_plan.MAX_AGGREGATE_FILE_BYTES` correctly override the limit in tests.

This was a latent bug from SP-12 (which introduced the `Constants` refactor) that only manifested when the `_save` closure restructure in SP-11 Task 3 changed the control flow so the route no longer short-circuited before the size check. The test `test_multi_file_upload_rejects_aggregate_size_over_limit` was failing because the patch had no effect on the actual constant used.

---

## Final Test Counts

- Backend: 348 passed, 0 failed
- Frontend: 85 passed, 0 failed

---

## Remaining Manual Steps (from PRD §8)

1. **SSE timing verification**: After merging, manually generate a care plan from a PDF upload in the browser. Confirm "Show Original" button appears immediately after generation (same session, no reload) — validates that `pdf_gcs_url` is in the SSE result payload.
2. **Visual review of text panel**: Open "Show Original" for a text/batch-dataset input and confirm the text panel scrolls independently, font size reads well, and panels are visually balanced.
