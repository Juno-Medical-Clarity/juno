# Implementation Summary: SP-12 Constants Consolidation

**Date:** 2026-06-21
**Agent session result:** Complete

---

## What Was Implemented

SP-12 is a pure internal refactor. No API surface, business logic, or pipeline behavior changed.

### Backend changes

**`backend/utils/constants.py`** (pre-existing, no changes needed)
Expanded `Constants` class already contained all consolidated constants: file upload limits (`ALLOWED_EXTENSIONS`, `MAX_FILE_BYTES`, `MAX_FILE_COUNT`, `MAX_AGGREGATE_FILE_BYTES`), pipeline registry (`PIPELINE_VERSION_V1_2`, `ALLOWED_VERSIONS`), batch config (`MAX_BATCH_RUNS`), default version env-var metadata (`CARE_PLAN_DEFAULT_VERSION_ENV_VAR`, `CARE_PLAN_DEFAULT_VERSION_FALLBACK`), SSE sentinel (`RESULT_SENTINEL`), and step labels (`STEPS`).

**`backend/config.py`** (pre-existing, no changes needed)
Already imports `Constants` and composes `CARE_PLAN_DEFAULT_VERSION = os.getenv(Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR, Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK)`.

**`backend/routes/care_plan.py`** (2 lines removed, 2 usages updated)
- Removed leftover local alias lines: `RESULT_SENTINEL = Constants.RESULT_SENTINEL` and `MAX_AGGREGATE_FILE_BYTES = Constants.MAX_AGGREGATE_FILE_BYTES`
- Updated 2 usages of bare `MAX_AGGREGATE_FILE_BYTES` in `_resolve_uploaded_files` to `Constants.MAX_AGGREGATE_FILE_BYTES`
- All other references already used `Constants.*` directly (23 total)

**`backend/routes/batch.py`** (1 line removed, 2 usages updated)
- Removed leftover local alias line: `MAX_BATCH_RUNS = Constants.MAX_BATCH_RUNS`
- Updated 2 usages of bare `MAX_BATCH_RUNS` in `create_care_plan_batch` to `Constants.MAX_BATCH_RUNS`
- Cross-route import of `ALLOWED_VERSIONS` and `RESULT_SENTINEL` from `routes.care_plan` was already removed
- All 5 `Constants.*` references confirmed in place

### Frontend changes (all pre-existing, no changes needed)

**`frontend/src/constants.ts`** — new file with all API path constants and template helpers (`savedOutputPath`, `inputPdfUrlPath`, `datasetFilePath`), plus `DEFAULT_VERSION` and `CARE_PLAN_API_PATH` alias.

**`frontend/src/config.ts`** — removed inline `CARE_PLAN_API_PATH` and `DEFAULT_VERSION` definitions; re-exports them from `./constants`. `VERSIONS` array unchanged.

**`frontend/src/api/savedOutputs.ts`** — imports `SAVED_OUTPUTS_PATH`, `savedOutputPath`, `inputPdfUrlPath` from `../constants`; no inline path strings.

**`frontend/src/api/datasets.ts`** — imports `DATASETS_PATH`, `BATCH_PATH`, `datasetFilePath` from `../constants`; `encodeURIComponent` calls absorbed into `datasetFilePath` helper.

**`frontend/src/pages/care-plan/CarePlanPage.tsx`** — imports `CARE_PLAN_API_PATH` and `DEFAULT_VERSION` from `../../constants` (not `../../config`).

---

## Verification

- Backend: All Python acceptance assertions pass
- Frontend: `npx tsc --noEmit` exits 0 with no errors
- No inline path strings remain in `savedOutputs.ts` or `datasets.ts`
- No bare module-level constant aliases remain in `care_plan.py` or `batch.py`
- Cross-route coupling (`batch.py → care_plan.py` for `ALLOWED_VERSIONS`) is fully broken

---

## Files Changed

- `/root/projects/juno/backend/routes/care_plan.py` — removed 2 alias lines, updated 2 usages
- `/root/projects/juno/backend/routes/batch.py` — removed 1 alias line, updated 2 usages

All other files were already correctly implemented prior to this agent session.
