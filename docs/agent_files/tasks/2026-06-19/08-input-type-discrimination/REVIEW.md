# REVIEW: SP-08 Input Type Discrimination

**Reviewed:** 2026-06-21
**Status:** COMPLETE (after one fix applied)

---

## What Was Correct

All 9 tasks from the PRD were implemented correctly by the implementation agent:

**Task 1 — `models/input.py` rewritten:**
- Four concrete `JsonModel` subclasses: `FileInput`, `TextInput`, `DocIdInput`, `BatchDatasetInput`
- Each with a `Literal` discriminator on `mode`
- `Input` defined as `Annotated[Union[...], Field(discriminator="mode")]` runtime alias
- `FileInput.from_file_uploads` classmethod preserved; old `Input.from_*` classmethods removed
- `pdf_gcs_url: str | None = None` stub on `FileInput` for SP-11
- `BatchDatasetInput.mode = "batch_dataset"` (breaking change from old `"text"`) — implemented as approved

**Task 2 — `models/__init__.py` updated:** All four concrete types exported; `__all__` updated.

**Task 3 — `models/envelope.py`:** No change needed; Pydantic v2 discriminated union dispatches automatically via `input: Input` annotation.

**Task 4 — `routes/care_plan.py`:** `_input_model_from_resolved` rewired to use `TextInput`, `DocIdInput`, `FileInput.from_file_uploads` directly.

**Task 5 — `routes/batch.py`:** `BatchDatasetInput(...)` construction replacing old `Input.from_batch_dataset(...)`.

**Task 6 — `tests/models/test_input_metrics.py`:** Fully rewritten with 22 tests covering each variant's exact shape, `extra="forbid"` rejection, TypeAdapter dispatch, and `CarePlanInternal` round-trips.

**Task 7 — `tests/models/test_exports.py`:** `__all__` assertion and import smoke-tests updated.

**Task 8 — `frontend/src/types/envelope.ts`:** Flat `Input` interface replaced with four concrete interfaces and a `type Input = FileInput | TextInput | DocIdInput | BatchDatasetInput` union.

**Task 9 — Frontend TS sweep:** Only one access site (`outputHasInputPdf` in `CarePlanPage.tsx`) found; already mode-guarded; no changes needed.

---

## Issue Found and Fixed

**Bug: `routes/batch.py` — `MAX_BATCH_RUNS` module-level name removed**

The implementation changed batch.py to access `Constants.MAX_BATCH_RUNS` inline rather than binding it at module level as `MAX_BATCH_RUNS = Constants.MAX_BATCH_RUNS`. The test `test_batch_rejects_too_many_runs_before_pipeline_work` patches `routes.batch.MAX_BATCH_RUNS` and failed with `AttributeError: <module 'routes.batch'> does not have the attribute 'MAX_BATCH_RUNS'`.

**Fix applied:** Added `MAX_BATCH_RUNS = Constants.MAX_BATCH_RUNS` at module level in `/root/projects/juno/backend/routes/batch.py` (after the `Constants` import) and updated the two inline `Constants.MAX_BATCH_RUNS` references to use the module-level name.

File: `/root/projects/juno/backend/routes/batch.py`

---

## Breaking Change Note

`BatchDatasetInput.mode = "batch_dataset"` — confirmed intentional per locked initiative decision. Old Firestore documents with `mode: "text"` for batch runs will fail deserialization through `CarePlanInternal.model_validate`. GET `/care_plan/saved/:id` passes `output_data` as a raw dict without re-validation, so no runtime regression on reads. This is approved per the no-legacy-data decision.

---

## Test Results

After fix: **115 passed, 0 failed** (`tests/models/` + `tests/routes/`)

Pre-fix: 114 passed, 1 failed (`test_batch_rejects_too_many_runs_before_pipeline_work`)
