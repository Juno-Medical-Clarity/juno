# REVIEW: Constants Consolidation (SP-12)

**Date:** 2026-06-21
**Status:** Complete — all 10 tasks implemented and verified

---

## What Existed Before This Agent Ran

The codebase was in a partially completed state. Several tasks had already been applied (likely by an earlier agent pass), but with leftover local alias patterns that violated the PRD spec:

### Already Done (correctly)
- `backend/utils/constants.py` — fully expanded `Constants` class with all groups (Task 1: done)
- `backend/config.py` — `CARE_PLAN_DEFAULT_VERSION` already composed from `Constants` (Task 2: done)
- `backend/routes/care_plan.py` — `PIPELINES` dict already keyed by `Constants.PIPELINE_VERSION_V1_2`; `ALLOWED_VERSIONS` module-level name already removed; all `Constants.*` references in function bodies correct (Task 3: mostly done, but see below)
- `backend/routes/batch.py` — `from routes.care_plan import` already stripped of `ALLOWED_VERSIONS` and `RESULT_SENTINEL`; all body usages of `Constants.ALLOWED_VERSIONS`, `Constants.RESULT_SENTINEL`, `Constants.PIPELINE_VERSION_V1_2` correct (Task 4: mostly done, but see below)
- `frontend/src/constants.ts` — file existed with correct content (Task 5: done)
- `frontend/src/config.ts` — already re-exports `CARE_PLAN_API_PATH`, `DEFAULT_VERSION` from `./constants` (Task 6: done)
- `frontend/src/api/savedOutputs.ts` — already imports from `../constants`, no inline path strings (Task 7: done)
- `frontend/src/api/datasets.ts` — already imports from `../constants`, no inline path strings, `encodeURIComponent` absorbed into helper (Task 8: done)
- `frontend/src/pages/care-plan/CarePlanPage.tsx` — already imports from `../../constants` (Task 9: done)

### Leftover Issues Fixed By This Agent

Two files had leftover local aliases (module-level assignments that mirrored `Constants` values), which are forbidden by the PRD:

**`backend/routes/care_plan.py`** (lines 34–35 before fix):
```python
# WRONG — local aliases that defeat the purpose of Constants
RESULT_SENTINEL = Constants.RESULT_SENTINEL
MAX_AGGREGATE_FILE_BYTES = Constants.MAX_AGGREGATE_FILE_BYTES
```
- Removed both alias lines
- Updated two usages of bare `MAX_AGGREGATE_FILE_BYTES` (lines 147–148 in `_resolve_uploaded_files`) to `Constants.MAX_AGGREGATE_FILE_BYTES`
- `RESULT_SENTINEL` was already used as `Constants.RESULT_SENTINEL` directly in the function bodies; removing the alias had no functional impact

**`backend/routes/batch.py`** (line 15 before fix):
```python
# WRONG — local alias
MAX_BATCH_RUNS = Constants.MAX_BATCH_RUNS
```
- Removed the alias line
- Updated two usages (lines 149–150 in `create_care_plan_batch`) to `Constants.MAX_BATCH_RUNS`

---

## What Was Implemented

All 10 TASKS.md tasks are complete:

| Task | File(s) | Status |
|------|---------|--------|
| 1 | `backend/utils/constants.py` | Done (pre-existing) |
| 2 | `backend/config.py` | Done (pre-existing) |
| 3 | `backend/routes/care_plan.py` | Fixed: removed local aliases, updated usages |
| 4 | `backend/routes/batch.py` | Fixed: removed local alias, updated usages |
| 5 | `frontend/src/constants.ts` | Done (pre-existing) |
| 6 | `frontend/src/config.ts` | Done (pre-existing) |
| 7 | `frontend/src/api/savedOutputs.ts` | Done (pre-existing) |
| 8 | `frontend/src/api/datasets.ts` | Done (pre-existing) |
| 9 | `frontend/src/pages/care-plan/CarePlanPage.tsx` | Done (pre-existing) |
| 10 | TypeScript build verification | Passed: `npx tsc --noEmit` exits 0 |

---

## Acceptance Criteria Verification

All acceptance checks from TASKS.md pass:

```bash
# Task 1
python3 -c "from utils.constants import Constants; assert Constants.ALLOWED_VERSIONS == frozenset({'v1-2'}); assert Constants.MAX_FILE_BYTES == 10*1024*1024; assert Constants.RESULT_SENTINEL == '__result__'; print('ok')"
# => ok

# Task 2
python3 -c "from config import CARE_PLAN_DEFAULT_VERSION; assert CARE_PLAN_DEFAULT_VERSION == 'v1-2'; print('ok')"
# => ok

# Task 3: no bare aliases
grep "^RESULT_SENTINEL\|^STEPS\|^ALLOWED_EXTENSIONS\|^MAX_FILE\|^_GCS_BUCKET_NAME\|^ALLOWED_VERSIONS\|^MAX_AGGREGATE_FILE_BYTES" backend/routes/care_plan.py
# => (no output)

# Task 4: no bare aliases or cross-route imports
grep "^MAX_BATCH_RUNS\|from routes.care_plan import.*ALLOWED_VERSIONS\|from routes.care_plan import.*RESULT_SENTINEL" backend/routes/batch.py
# => (no output)

# Task 10: TypeScript
cd frontend && npx tsc --noEmit
# => (no output, exit 0)
```

---

## Blockers

None.

## Remaining Manual Steps

None required. Per PRD §8, SP-12 is a pure refactor with no deployment-config changes, no Firestore schema changes, no new env vars, and no new dependencies.

**Optional follow-up (not blocking):** The re-export stubs in `frontend/src/config.ts` (`CARE_PLAN_API_PATH`, `DEFAULT_VERSION`) are now technically dead code since `CarePlanPage.tsx` imports directly from `constants.ts`. They can be removed in a follow-up cleanup.
