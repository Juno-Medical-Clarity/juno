# Review — SP-07: Care Plan Model & Folder Restructure
Date: 2026-06-21

## Status: COMPLETE (after fixes applied in this review)

---

## What the Implementation Got Right

All 10 tasks from TASKS.md were substantially implemented. The major structural work was done correctly:

- `backend/care_plan/` package created with `interface.py`, `v1_2/__init__.py` (registration import), `v1_2/models.py` (all v1.2 types), and `v1_2/pipeline.py` (CarePlanV1_2Pipeline).
- `backend/simplify/` directory fully deleted.
- `models/care_plan.py` slimmed to base-only (`CarePlan` + `CARE_PLAN_VERSION`).
- `models/__init__.py` updated per PRD §4.11 (no `CarePlanV1_2`, no `CarePlanV1_2StructuredLLM`, no `is_legacy_shape`; added `GradingMethodReason`).
- `models/grading.py` now has `GradingMethodReason(str, enum.Enum)` with 6 members; `build_grading` uses `GradingMethodReason[method_name].value`.
- `models/envelope.py` has `CarePlanInternal` without `before_score`/`after_score`; `is_legacy_shape` deleted.
- `routes/care_plan.py` imports `CarePlanV1_2Pipeline`; sentinel tuple is 5-element (no scores); unpacking correct.
- `routes/batch.py` has no `before_score`/`after_score` references.
- `_llm_schema()` helper added to `care_plan/v1_2/pipeline.py`; `_STRUCTURING_SCHEMA` generated from it.
- `structure_appointment_note` validates via `CarePlanV1_2.model_validate` and dumps with `exclude={"terms", "raw"}`.
- Test folder renamed `tests/simplify/` → `tests/care_plan/` (most files moved).
- Test files updated: `test_pipeline_interface.py`, `test_pipeline_schema.py`, `test_care_plan.py`, `test_exports.py`, `test_envelope.py`, `test_grading_model.py`, `test_pipeline_executors.py`, `test_care_plan_route.py`, `test_care_plan_persistence.py`.

---

## Issues Found and Fixed

### Issue 1 (CRITICAL): `RESULT_SENTINEL` module-level alias missing from `routes/care_plan.py`

**Problem:** Two test files (`tests/care_plan/test_pipeline_errors.py` and `tests/care_plan/test_pipeline_happy_path.py`) import `RESULT_SENTINEL` directly from `routes.care_plan`:
```python
from routes.care_plan import RESULT_SENTINEL
```
The implementation removed the module-level alias `RESULT_SENTINEL = Constants.RESULT_SENTINEL` from `routes/care_plan.py` while only using `Constants.RESULT_SENTINEL` internally. This caused collection-time `ImportError` that prevented those test files from being collected at all — which masked further test failures.

**Fix applied:** Added back the module-level aliases after the `Constants` import in `routes/care_plan.py`:
```python
RESULT_SENTINEL = Constants.RESULT_SENTINEL
MAX_AGGREGATE_FILE_BYTES = Constants.MAX_AGGREGATE_FILE_BYTES
```

### Issue 2 (MINOR): `tests/simplify/test_pipeline_prompts.py` not moved

**Problem:** When `tests/simplify/` was renamed to `tests/care_plan/`, `test_pipeline_prompts.py` was left behind in `tests/simplify/`. The folder still existed as `tests/simplify/` with one file. This would cause the `test_old_simplify_folder_is_gone` assertion in `test_pipeline_interface.py` to fail (that test checks `backend/simplify/` not `tests/simplify/`, but the orphaned file was still being collected by pytest and would have been a problem for any future cleanup assertion on the tests folder).

**Fix applied:** Moved `tests/simplify/test_pipeline_prompts.py` → `tests/care_plan/test_pipeline_prompts.py`, then deleted the `tests/simplify/` directory.

### Issue 3 (COSMETIC): Stale comment in `tests/fixtures/care_plan.py`

**Problem:** Line 16 comment still read: `# Keys: metrics, input, grading, care_plan (plus optional before_score/after_score).`

**Fix applied:** Updated comment to: `# Keys: metrics, input, grading, care_plan.`

---

## Test Results After Fixes

```
346 passed, 2 failed (pre-existing), 1 warning in ~254s
```

The 2 failures are pre-existing, unrelated to SP-07:
- `test_care_plan_persistence.py::test_multi_file_upload_rejects_aggregate_size_over_limit` — GCP Firestore HTTP 404 (no GCP project configured in test env).
- `test_batch_route.py::test_batch_rejects_too_many_runs_before_pipeline_work` — Pre-existing batch-route ordering issue.

Both were documented as pre-existing in the implementation record.

---

## Conformance to PRD/TASKS

| Item | Status |
|---|---|
| Task 1: `care_plan/` package skeleton | Correct |
| Task 2: `care_plan/v1_2/models.py` (move v1.2 types) | Correct |
| Task 3: `care_plan/v1_2/pipeline.py` (move + update) | Correct |
| Task 4: Delete `backend/simplify/` | Correct |
| Task 5: Slim `models/care_plan.py` to base-only | Correct |
| Task 6: Update `models/__init__.py` exports | Correct |
| Task 7: `GradingMethodReason` enum in `grading.py` | Correct |
| Task 8: Remove `before_score`/`after_score` + `is_legacy_shape` | Correct |
| Task 9: Update `routes/care_plan.py` and `routes/batch.py` | Correct (after fix 1) |
| Task 10a: Rename `tests/simplify/` → `tests/care_plan/` | Fixed (after fix 2) |
| Task 10b-i: All test file updates | Correct |
| PRD §4.9: `Grading` stays as `JsonModel` (no version field) | Correct |
| PRD §4.11: `models/__init__.py` `__all__` matches exactly | Correct |

---

## No Outstanding Issues
All PRD requirements are satisfied. No dead code remains. The restructure is complete.
