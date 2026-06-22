# Tasks: Constants Consolidation (SP-12)

Pure internal refactor — no logic changes, no API surface changes. All decisions are
RESOLVED in PRD §9. No [OPEN] items exist.

SP-12 has no dependencies on other SPs and can land in any order.

---

### Task 1 — Expand `utils/constants.py` with all consolidated constants

**Files:** `backend/utils/constants.py`

Add two new logical groups to the existing `Constants` class — file upload limits and
pipeline registry config — plus `RESULT_SENTINEL`, `STEPS`, and batch config. The three
pre-existing `SUMMARY_SCHEMA_VERSION_*` attributes are left in place, unchanged.

Replace the entire file with:

```python
class Constants:
    # ── Summary schema versions (pre-existing) ───────────────────────────
    SUMMARY_SCHEMA_VERSION_1_2 = "1.2"
    SUMMARY_SCHEMA_VERSION_1_3 = "1.3"
    SUMMARY_SCHEMA_VERSION_1_4 = "1.4"

    # ── File upload limits ────────────────────────────────────────────────
    ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx"})
    MAX_FILE_BYTES: int = 10 * 1024 * 1024       # 10 MB per file
    MAX_FILE_COUNT: int = 10
    MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024  # 25 MB combined

    # ── GCS / Cloud config ────────────────────────────────────────────────
    GCS_BUCKET_ENV_VAR: str = "GCP_BUCKET_NAME"  # name of the env var, not the value

    # ── Pipeline registry ─────────────────────────────────────────────────
    PIPELINE_VERSION_V1_2: str = "v1-2"
    ALLOWED_VERSIONS: frozenset[str] = frozenset({"v1-2"})

    # ── Batch ─────────────────────────────────────────────────────────────
    MAX_BATCH_RUNS: int = 50

    # ── Default pipeline version (moved from config.py) ───────────────────
    # config.py re-exports this for backward-compat; the source of truth is here.
    CARE_PLAN_DEFAULT_VERSION_ENV_VAR: str = "CARE_PLAN_DEFAULT_VERSION"
    CARE_PLAN_DEFAULT_VERSION_FALLBACK: str = "v1-2"

    # ── SSE sentinel ──────────────────────────────────────────────────────
    RESULT_SENTINEL: str = "__result__"

    # ── Pipeline step labels ──────────────────────────────────────────────
    STEPS: dict[int, str] = {
        1: "Reading your note",
        2: "Finding difficult and medical terms",
        3: "Simplifying language",
        4: "Clarifying actions and numbers",
        5: "Organizing your care plan",
    }
```

Key design points (PRD §4.1):
- `ALLOWED_EXTENSIONS` and `ALLOWED_VERSIONS` are `frozenset`, not `set` — immutable at class level.
- `GCS_BUCKET_ENV_VAR` stores the env-var *name* only; the resolved value stays in the route.
- `PIPELINES` dict is NOT moved here (PRD §9.3 RESOLVED — its values are callable route functions).
- Model version constants (`CARE_PLAN_VERSION`, `GRADING_VERSION`, `INPUT_VERSION`) are NOT moved
  (PRD §9.2 RESOLVED — they stay in `models/`).

**Acceptance:** `python -c "from utils.constants import Constants; assert Constants.ALLOWED_VERSIONS == frozenset({'v1-2'}); assert Constants.MAX_FILE_BYTES == 10 * 1024 * 1024; assert Constants.RESULT_SENTINEL == '__result__'; print('ok')"` prints `ok` when run from `backend/`.

---

### Task 2 — Update `config.py` to compose `CARE_PLAN_DEFAULT_VERSION` from `Constants`

**Files:** `backend/config.py`

Change the `CARE_PLAN_DEFAULT_VERSION` line to use the env-var name and fallback from
`Constants`. Add the import of `Constants`. All other GCP env-var reads are unchanged.

Current line 13:
```python
CARE_PLAN_DEFAULT_VERSION = os.getenv('CARE_PLAN_DEFAULT_VERSION', 'v1-2')
```

Replace with:
```python
from utils.constants import Constants

# …existing GCP reads unchanged…

CARE_PLAN_DEFAULT_VERSION = os.getenv(
    Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR,
    Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK,
)
```

The `from utils.constants import Constants` import should be added after the existing
`from dotenv import load_dotenv` import. Everything else in `config.py` stays unchanged.
Both routes (`care_plan.py`, `batch.py`) continue importing `CARE_PLAN_DEFAULT_VERSION`
from `config` — no change to those import sites (PRD §9.8 RESOLVED).

**Acceptance:** `python -c "from config import CARE_PLAN_DEFAULT_VERSION; assert CARE_PLAN_DEFAULT_VERSION == 'v1-2'; print('ok')"` prints `ok` when run from `backend/` (with no `CARE_PLAN_DEFAULT_VERSION` env var set).

---

### Task 3 — Refactor `routes/care_plan.py` to use `Constants`

**Files:** `backend/routes/care_plan.py`

**Step 1 — Add import.** After the existing `from config import CARE_PLAN_DEFAULT_VERSION`
line (line 31), add:
```python
from utils.constants import Constants
```

**Step 2 — Remove module-level constant definitions** (lines 51–65 in current file):
Delete these seven lines:
```python
RESULT_SENTINEL = "__result__"

STEPS = {
    1: "Reading your note",
    2: "Finding difficult and medical terms",
    3: "Simplifying language",
    4: "Clarifying actions and numbers",
    5: "Organizing your care plan",
}

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_FILE_COUNT = 10
MAX_AGGREGATE_FILE_BYTES = 25 * 1024 * 1024  # 25 MB
_GCS_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "")
```

**Step 3 — Replace all usages** inside the file (do a careful search-and-replace for each):

| Old name | New reference |
|---|---|
| `RESULT_SENTINEL` | `Constants.RESULT_SENTINEL` |
| `STEPS[N]` | `Constants.STEPS[N]` |
| `ALLOWED_EXTENSIONS` | `Constants.ALLOWED_EXTENSIONS` |
| `MAX_FILE_BYTES` | `Constants.MAX_FILE_BYTES` |
| `MAX_FILE_COUNT` | `Constants.MAX_FILE_COUNT` |
| `MAX_AGGREGATE_FILE_BYTES` | `Constants.MAX_AGGREGATE_FILE_BYTES` |
| `_GCS_BUCKET_NAME` (line 192, 197) | `os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")` inline at each use |

Also note the `upload_combined_pdf` function at line 71 has a separate `os.environ.get("GCP_BUCKET_NAME", "")` call — update that too: `os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")`.

**Step 4 — Update `PIPELINES` dict and remove `ALLOWED_VERSIONS`** (lines 599–600):
```python
# Before:
PIPELINES = {"v1-2": run_care_plan_pipeline}
ALLOWED_VERSIONS = set(PIPELINES)

# After:
PIPELINES = {Constants.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}
# ALLOWED_VERSIONS removed — use Constants.ALLOWED_VERSIONS directly
```

**Step 5 — Update the version check** (line 615):
```python
# Before:
if not isinstance(version, str) or version not in ALLOWED_VERSIONS:

# After:
if not isinstance(version, str) or version not in Constants.ALLOWED_VERSIONS:
```

**Step 6 — Update the pipeline lookup** (line 530):
```python
# Before:
pipeline = PIPELINES[version]

# After:
pipeline = PIPELINES[version]   # unchanged — PIPELINES is still a local dict
```
(No change needed for line 530 — `PIPELINES` stays as a module-level dict in this file.)

Note: `_UPLOAD_PREFIX = "care_plan-uploads"` (line 66) is used only locally and does NOT move to `Constants` (PRD §4.2).

**Acceptance:**
- `grep -n "^RESULT_SENTINEL\|^STEPS\|^ALLOWED_EXTENSIONS\|^MAX_FILE\|^_GCS_BUCKET_NAME\|^ALLOWED_VERSIONS" backend/routes/care_plan.py` returns nothing.
- `grep -n "Constants\." backend/routes/care_plan.py` shows references replacing the old names.
- The route's file-limit validation logic is unchanged (same numeric thresholds, now via `Constants`).

---

### Task 4 — Refactor `routes/batch.py` to break cross-route coupling

**Files:** `backend/routes/batch.py`

**Step 1 — Change the import from `routes.care_plan`** (line 13).

Current:
```python
from routes.care_plan import ALLOWED_VERSIONS, RESULT_SENTINEL, _extract_text_from_bytes, run_care_plan_pipeline
```

Replace with:
```python
from utils.constants import Constants
from routes.care_plan import _extract_text_from_bytes, run_care_plan_pipeline
```

**Step 2 — Remove the module-level `MAX_BATCH_RUNS = 50`** (line 19).
Delete this line — `Constants.MAX_BATCH_RUNS` replaces it.

**Step 3 — Update all usages** in the file:

| Old | New |
|---|---|
| `ALLOWED_VERSIONS` (line 134) | `Constants.ALLOWED_VERSIONS` |
| `RESULT_SENTINEL` (line 200) | `Constants.RESULT_SENTINEL` |
| `MAX_BATCH_RUNS` (lines 147–148) | `Constants.MAX_BATCH_RUNS` |
| `version == "v1-2"` in `_pipeline_for_version` (line 43) | `version == Constants.PIPELINE_VERSION_V1_2` |

The specific lines to update:
- Line 43: `if version == "v1-2":` → `if version == Constants.PIPELINE_VERSION_V1_2:`
- Line 134: `version not in ALLOWED_VERSIONS` → `version not in Constants.ALLOWED_VERSIONS`
- Line 147: `if total > MAX_BATCH_RUNS:` → `if total > Constants.MAX_BATCH_RUNS:`
- Line 148: `f"Batch request exceeds maximum of {MAX_BATCH_RUNS} runs"` → `f"Batch request exceeds maximum of {Constants.MAX_BATCH_RUNS} runs"`
- Line 200: `chunk[0] == RESULT_SENTINEL` → `chunk[0] == Constants.RESULT_SENTINEL`

**Acceptance:**
- `grep -n "^MAX_BATCH_RUNS\|from routes.care_plan import ALLOWED_VERSIONS\|from routes.care_plan import.*RESULT_SENTINEL" backend/routes/batch.py` returns nothing.
- `grep -n "Constants\." backend/routes/batch.py` shows all five replacements.
- `python -c "from routes.batch import batch_bp; print('ok')"` runs without import errors from `backend/`.

---

### Task 5 — Create `frontend/src/constants.ts`

**Files:** `frontend/src/constants.ts` (NEW FILE)

Create this file with all API path strings, template helpers, and the moved
`DEFAULT_VERSION`/`CARE_PLAN_API_PATH` values (PRD §4.6):

```typescript
// frontend/src/constants.ts
// All API path strings. API_URL (the base URL from env) stays in api/firebase.ts.
// VERSIONS array (UI display config) stays in config.ts.

export const CARE_PLAN_PATH = '/care_plan';
export const SAVED_OUTPUTS_PATH = '/care_plan/saved';
export const BATCH_PATH = '/care_plan/batch';
export const DATASETS_PATH = '/care_plan/datasets';

// Per-ID path helpers — eliminate inline template literals at call sites.
export const savedOutputPath = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}`;
export const inputPdfUrlPath  = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}/input-pdf-url`;
export const datasetFilePath  = (group: string, input: string, file: string) =>
  `${DATASETS_PATH}/${encodeURIComponent(group)}/${encodeURIComponent(input)}/${encodeURIComponent(file)}`;

// Moved from config.ts (pipeline-selection strings, same semantic kind as CARE_PLAN_PATH).
export const DEFAULT_VERSION = 'v1-2';
export { CARE_PLAN_PATH as CARE_PLAN_API_PATH };  // alias — config.ts re-exports it
```

`API_URL` is NOT added here (it is a runtime env-var value resolved in `api/firebase.ts`).
`VERSIONS` is NOT added here (it is UI display config; stays in `config.ts`).

**Acceptance:**
- File exists at `frontend/src/constants.ts`.
- `npx tsc --noEmit` in `frontend/` passes (or run after Tasks 6–9 are also complete).
- `savedOutputPath('abc')` equals `'/care_plan/saved/abc'`.
- `datasetFilePath('grp', 'inp', 'f.pdf')` equals `'/care_plan/datasets/grp/inp/f.pdf'`.

---

### Task 6 — Update `frontend/src/config.ts` to re-export from `constants.ts`

**Files:** `frontend/src/config.ts`

Remove the `CARE_PLAN_API_PATH` and `DEFAULT_VERSION` constant definitions and replace
them with re-exports from `./constants`. Keep `VERSIONS` exactly as-is.

Current `config.ts`:
```typescript
export const CARE_PLAN_API_PATH = '/care_plan';

export const DEFAULT_VERSION = 'v1-2';

// Static list rendered by VersionsPage. ...
export const VERSIONS = [ … ] as const;
```

Updated `config.ts`:
```typescript
// CARE_PLAN_API_PATH and DEFAULT_VERSION moved to constants.ts.
// Re-exported here as a safety net during transition.
export { CARE_PLAN_API_PATH, DEFAULT_VERSION } from './constants';

// Static list rendered by VersionsPage. Append a second entry (e.g. v1-3) to add a version later.
export const VERSIONS = [
  {
    id: 'v1-2',
    label: 'Version 1.2',
    description: 'Create a V1.2 care plan with clearer appointment sections, warning signs, follow-up questions, and patient-friendly care details.',
    steps: ['Read input', 'Find medical terms', 'Plain language rewrite', 'Clarify care details', 'Structure V1.2 note'],
    isDefault: true,
  },
] as const;
```

The re-export lines act as a safety net for the transition. They can be removed in a
follow-up once Task 7 (CarePlanPage) is merged and confirmed (PRD §4.10).

**Acceptance:**
- `grep "CARE_PLAN_API_PATH\|DEFAULT_VERSION" frontend/src/config.ts` shows only `export {` re-export lines (no `= '/care_plan'` or `= 'v1-2'` inline definitions).
- `VERSIONS` export is unchanged.

---

### Task 7 — Update `frontend/src/api/savedOutputs.ts` to use path constants

**Files:** `frontend/src/api/savedOutputs.ts`

Add an import from `../constants` and replace the four inline path strings.

**Add import** (after the existing imports at the top of the file):
```typescript
import { SAVED_OUTPUTS_PATH, savedOutputPath, inputPdfUrlPath } from '../constants';
```

**Replace inline strings:**

| Old inline string | New expression |
|---|---|
| `` `${API_URL}/care_plan/saved` `` (line 19) | `` `${API_URL}${SAVED_OUTPUTS_PATH}` `` |
| `` `${API_URL}/care_plan/saved/${id}` `` (lines 26, 32, 41) | `` `${API_URL}${savedOutputPath(id)}` `` |
| `` `${API_URL}/care_plan/saved/${id}/input-pdf-url` `` (line 48) | `` `${API_URL}${inputPdfUrlPath(id)}` `` |

All three uses of `` `/care_plan/saved/${id}` `` (lines 26, 32, 41) map to
`savedOutputPath(id)`.

**Acceptance:**
- `grep "'/care_plan" frontend/src/api/savedOutputs.ts` returns nothing (no inline path strings remain).
- `grep "SAVED_OUTPUTS_PATH\|savedOutputPath\|inputPdfUrlPath" frontend/src/api/savedOutputs.ts` shows the imports and usages.

---

### Task 8 — Update `frontend/src/api/datasets.ts` to use path constants

**Files:** `frontend/src/api/datasets.ts`

Add an import from `../constants` and replace the three inline path strings (including
absorbing the three `encodeURIComponent` calls into the `datasetFilePath` helper).

**Add import** (after the existing imports):
```typescript
import { DATASETS_PATH, BATCH_PATH, datasetFilePath } from '../constants';
```

**Replace inline strings:**

| Old | New |
|---|---|
| `` `${API_URL}/care_plan/datasets` `` (line 11) | `` `${API_URL}${DATASETS_PATH}` `` |
| The block on lines 22–26 (three `encodeURIComponent` + template literal) | `` `${API_URL}${datasetFilePath(group, input, filename)}` `` |
| `` `${API_URL}/care_plan/batch` `` (line 38) | `` `${API_URL}${BATCH_PATH}` `` |

The `encodeURIComponent` block to remove (lines 22–26):
```typescript
const encodedGroup = encodeURIComponent(group);
const encodedInput = encodeURIComponent(input);
const encodedFilename = encodeURIComponent(filename);

`${API_URL}/care_plan/datasets/${encodedGroup}/${encodedInput}/${encodedFilename}`,
```
Replace the entire block with:
```typescript
`${API_URL}${datasetFilePath(group, input, filename)}`,
```
The `encodedGroup`, `encodedInput`, `encodedFilename` intermediate variable declarations
are no longer needed; delete them (PRD §9.7 RESOLVED — encoding is an implementation
detail of `datasetFilePath`).

**Acceptance:**
- `grep "'/care_plan\|encodeURIComponent" frontend/src/api/datasets.ts` returns nothing.
- `grep "DATASETS_PATH\|BATCH_PATH\|datasetFilePath" frontend/src/api/datasets.ts` shows all three.

---

### Task 9 — Update `CarePlanPage.tsx` import source

**Files:** `frontend/src/pages/care-plan/CarePlanPage.tsx`

Change a single import statement (line 20). No changes anywhere in the component body —
the two exported names (`CARE_PLAN_API_PATH`, `DEFAULT_VERSION`) are identical.

```typescript
// Before (line 20):
import { CARE_PLAN_API_PATH, DEFAULT_VERSION } from '../../config';

// After:
import { CARE_PLAN_API_PATH, DEFAULT_VERSION } from '../../constants';
```

**Acceptance:**
- `grep "from '../../config'" frontend/src/pages/care-plan/CarePlanPage.tsx` returns nothing
  (or only unrelated imports from `config` if any exist besides `CARE_PLAN_API_PATH`/`DEFAULT_VERSION`).
- `grep "from '../../constants'" frontend/src/pages/care-plan/CarePlanPage.tsx` shows the line.
- The component renders identically — no logic or JSX changed.

---

### Task 10 — TypeScript build verification

**Files:** (none modified — verification task only)

After Tasks 5–9 are complete, run the TypeScript compiler in no-emit mode to confirm no
broken imports or missing exports:

```bash
cd frontend && npx tsc --noEmit
```

If the build fails, fix the specific error (broken import path, missing export name).
Common failure modes:
- `constants.ts` not found → check filename and path.
- `CARE_PLAN_API_PATH` not re-exported from `config.ts` → verify Task 6 re-export line.
- Import path uses wrong relative depth (e.g. `'../constants'` vs `'../../constants'`) — match the directory depth of each consumer.

**Acceptance:** `npx tsc --noEmit` exits 0 with no errors.

---

## Summary of what requires you (not a dev agent)

**None required.** SP-12 is a pure refactor with no deployment-config changes, no Firestore
schema changes, no new env vars, and no new dependencies (PRD §8).

**Optional post-ship cleanup (not blocking):**
Once all consumers import `CARE_PLAN_API_PATH` and `DEFAULT_VERSION` from `constants.ts`
directly (Task 9 completes this), the re-export stubs in `config.ts` (Task 6) are dead
code. They can be removed in a follow-up PR.
