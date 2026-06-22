# PRD: Constants Consolidation (SP-12)

Sub-project 12 of the Juno Phase 4 initiative. **No dependencies on other Phase 4 sub-projects**
(SP-07 through SP-13); this is a pure refactor that can land in any order. SP-07 (care plan folder
restructure) renames `simplify/ → care_plan/`; the `PIPELINES` dict in `routes/care_plan.py` will
reference the new import path after SP-07 lands, but SP-12 only touches the key strings inside
that dict — the import of the callable itself is SP-07's concern.

## 1. Problem

Magic values are scattered across seven backend files and four frontend files with no central
registry:

**Backend**
- `routes/care_plan.py` (lines 51–65, 599–600): `RESULT_SENTINEL`, `STEPS` dict, `ALLOWED_EXTENSIONS`,
  `MAX_FILE_BYTES`, `MAX_FILE_COUNT`, `MAX_AGGREGATE_FILE_BYTES`, `_GCS_BUCKET_NAME` (duplicate
  env-var read already done in `config.py`), `PIPELINES` dict, `ALLOWED_VERSIONS`.
- `routes/batch.py` (line 19): `MAX_BATCH_RUNS = 50`. Also imports `ALLOWED_VERSIONS` from
  `routes.care_plan` — a cross-route coupling that forces batch to depend on care_plan internals.
- `config.py` (line 13): `CARE_PLAN_DEFAULT_VERSION = os.getenv('CARE_PLAN_DEFAULT_VERSION', 'v1-2')`.
- `models/care_plan.py` (line 11): `CARE_PLAN_VERSION = "1.2"`.
- `models/grading.py` (line 9): `GRADING_VERSION = "1.0"`.
- `models/input.py` (line 15): `INPUT_VERSION = "1.0"`.
- `utils/constants.py`: Only `SUMMARY_SCHEMA_VERSION_1_2 / _1_3 / _1_4` today; not used as the
  canonical home for any of the above.

**Frontend**
- `api/savedOutputs.ts`: Five inline template strings with `/care_plan/saved`, `/care_plan/saved/${id}`,
  `/care_plan/saved/${id}/input-pdf-url`.
- `api/datasets.ts`: Inline `/care_plan/datasets`, `/care_plan/datasets/${…}`, `/care_plan/batch`.
- `pages/care-plan/CarePlanPage.tsx`: `\`${API_URL}${CARE_PLAN_API_PATH}\`` assembled from two
  separate imports.
- `config.ts`: `CARE_PLAN_API_PATH = '/care_plan'`, `DEFAULT_VERSION = 'v1-2'`, `VERSIONS` array.
  No `src/constants.ts` exists today.

The consequences: a version string or file-size limit changed in one place can silently diverge
from the others; the batch route is tightly coupled to care_plan route internals
(`from routes.care_plan import ALLOWED_VERSIONS`); and frontend path strings can drift between
API modules.

## 2. Goals

1. **Backend**: Expand `utils/constants.py` (`Constants` class) to be the single authoritative home
   for all non-model-version magic values used across more than one file, plus upload-related limits
   defined in routes.
2. **Backend**: Keep model-version constants (`CARE_PLAN_VERSION`, `GRADING_VERSION`,
   `INPUT_VERSION`) where they are — in their respective model files — because SP-01 resolved them
   there and SP-04 imports them directly from model modules. This PRD does **not** move them.
3. **Backend**: Move `CARE_PLAN_DEFAULT_VERSION` from `config.py` into `Constants` so the default
   pipeline version is co-located with `ALLOWED_VERSIONS`/`PIPELINES`.
4. **Backend**: Break the `routes/batch.py → routes/care_plan.py` coupling: `ALLOWED_VERSIONS`
   (derived from `PIPELINES`) moves to `Constants`, so `batch.py` imports from `utils.constants`,
   not from a sibling route.
5. **Frontend**: Create `frontend/src/constants.ts` as the single file for all API path strings.
   Update every consumer to import from there. `config.ts` keeps `VERSIONS` (it is UI config, not
   an API path) but `CARE_PLAN_API_PATH` and `DEFAULT_VERSION` move to `constants.ts`.

## 3. Non-Goals

- **Not** moving `CARE_PLAN_VERSION`, `GRADING_VERSION`, or `INPUT_VERSION` out of their model
  files. SP-01 placed them there; SP-04 imports them from there. They are model-version facts, not
  route-level config.
- **Not** moving `SUMMARY_SCHEMA_VERSION_1_2 / _1_3 / _1_4` — they are already in `Constants` and
  can stay as-is.
- **Not** changing the `PIPELINES` dict value (a callable reference) — only the key string `"v1-2"`
  moves to `Constants`. The dict itself and the import of the pipeline callable remain in
  `routes/care_plan.py`.
- **Not** moving `API_URL` in the frontend — it comes from an env var via `firebase.ts` and is not
  a path string.
- **Not** moving `VERSIONS` array out of `config.ts` — it is UI display config (labels, descriptions,
  steps), not an API endpoint path.
- **Not** touching GCP config (`GCP_PROJECT_ID`, `GCP_BUCKET_NAME`, `GCP_LOCATION`, etc.) in
  `config.py` — those stay as env-var reads there.
- **Not** altering any business logic, pipeline behavior, or API surface.
- **Not** writing a TASKS.md.

## 4. Architecture Decisions

### 4.1 `backend/utils/constants.py` — expanded `Constants` class

The existing `Constants` class gains two logical groups: **upload/file limits** and **pipeline
registry config**. All values are class attributes (no instances needed).

```python
# backend/utils/constants.py

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

**Design notes:**

- `ALLOWED_EXTENSIONS` and `ALLOWED_VERSIONS` change from `set` to `frozenset` — immutable at
  class level, safer for a shared constant.
- `GCS_BUCKET_ENV_VAR = "GCP_BUCKET_NAME"` stores the *name* of the env var, not the resolved
  value. Actual lookup (`os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")`) stays in the route
  where GCS clients are instantiated. This avoids importing `os` into `constants.py` and keeps
  the constant purely declarative.
- `CARE_PLAN_DEFAULT_VERSION` stays as an `os.getenv(...)` call — it is an env-resolved runtime
  value. The constant captures only the env-var name and fallback. See §4.3 for how `config.py`
  composes these.
- `RESULT_SENTINEL` and `STEPS` move here so `routes/batch.py` can import the sentinel from
  `utils.constants` instead of `routes.care_plan` (breaking the current cross-route import of
  `RESULT_SENTINEL` from `routes.care_plan`).
- `PIPELINE_VERSION_V1_2` is the canonical key string `"v1-2"`. The `PIPELINES` dict in
  `routes/care_plan.py` uses it as a key (see §4.2).

### 4.2 `backend/routes/care_plan.py` — replace inline values

Old → new, by variable:

| Old (inline in route) | New reference |
|---|---|
| `RESULT_SENTINEL = "__result__"` | `Constants.RESULT_SENTINEL` |
| `STEPS = {1: "Reading…", …}` | `Constants.STEPS` |
| `ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}` | `Constants.ALLOWED_EXTENSIONS` |
| `MAX_FILE_BYTES = 10 * 1024 * 1024` | `Constants.MAX_FILE_BYTES` |
| `MAX_FILE_COUNT = 10` | `Constants.MAX_FILE_COUNT` |
| `MAX_AGGREGATE_FILE_BYTES = 25 * 1024 * 1024` | `Constants.MAX_AGGREGATE_FILE_BYTES` |
| `_GCS_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "")` | `os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")` (inline at point of use) |
| `PIPELINES = {"v1-2": run_care_plan_pipeline}` | `PIPELINES = {Constants.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}` |
| `ALLOWED_VERSIONS = set(PIPELINES)` | removed — `Constants.ALLOWED_VERSIONS` is used directly |

**Import change:**
```python
# add
from utils.constants import Constants
# remove module-level assignments for RESULT_SENTINEL, STEPS, ALLOWED_EXTENSIONS,
# MAX_FILE_BYTES, MAX_FILE_COUNT, MAX_AGGREGATE_FILE_BYTES, _GCS_BUCKET_NAME, ALLOWED_VERSIONS
```

`PIPELINES` stays as a module-level dict in the route (its values are callable references), but
keyed by `Constants.PIPELINE_VERSION_V1_2`.

`ALLOWED_VERSIONS` as a module-level name is **removed** from `routes/care_plan.py`. Any place in
the route that checked `version not in ALLOWED_VERSIONS` switches to
`version not in Constants.ALLOWED_VERSIONS`. The import in `routes/batch.py` of `ALLOWED_VERSIONS`
from `routes.care_plan` is likewise removed (see §4.4).

`_UPLOAD_PREFIX = "care_plan-uploads"` (line 66) is used only once, locally. It stays in the route
as a local string — single-file-only constants need not move.

**SP-07 note:** After SP-07 renames `simplify/ → care_plan/`, the import
`from simplify.v1_2.pipeline import V1_2Pipeline` (line 32) becomes
`from care_plan.v1_2.pipeline import V1_2Pipeline`. SP-12 does not touch this import; SP-07 owns
it. The `PIPELINES` dict value `run_care_plan_pipeline` is a function defined in this same file,
so it is unaffected by the module rename.

### 4.3 `backend/config.py` — `CARE_PLAN_DEFAULT_VERSION` composition

`CARE_PLAN_DEFAULT_VERSION` is an env-resolved runtime value. After SP-12:

```python
# backend/config.py
import os
from dotenv import load_dotenv
from utils.constants import Constants

load_dotenv()

# … GCP config unchanged …

CARE_PLAN_DEFAULT_VERSION = os.getenv(
    Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR,
    Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK,
)
```

`config.py` continues to export `CARE_PLAN_DEFAULT_VERSION` as a resolved string; both routes
still import it from `config` exactly as today. This keeps the pattern consistent with the other
GCP env reads in `config.py` and avoids a two-phase change to both routes.

### 4.4 `backend/routes/batch.py` — break the cross-route coupling

Current imports from a sibling route:
```python
from routes.care_plan import ALLOWED_VERSIONS, RESULT_SENTINEL, _extract_text_from_bytes, run_care_plan_pipeline
```

After SP-12 the first two move to `utils.constants`:

```python
# batch.py — import change
from utils.constants import Constants
from routes.care_plan import _extract_text_from_bytes, run_care_plan_pipeline

# usage change
if version not in Constants.ALLOWED_VERSIONS:   # was: version not in ALLOWED_VERSIONS
    …
if isinstance(chunk, tuple) and chunk and chunk[0] == Constants.RESULT_SENTINEL:   # was: == RESULT_SENTINEL
    …
if total > Constants.MAX_BATCH_RUNS:             # was: > MAX_BATCH_RUNS
    …
```

`_extract_text_from_bytes` and `run_care_plan_pipeline` still import from `routes.care_plan`
(they are route-local helpers, not constants).

The `_pipeline_for_version` helper in `batch.py` (line 43) hardcodes `"v1-2"`:

```python
def _pipeline_for_version(version: str) -> …:
    if version == "v1-2":         # current
```

This switches to:

```python
    if version == Constants.PIPELINE_VERSION_V1_2:
```

### 4.5 `backend/models/*.py` — no change

`CARE_PLAN_VERSION`, `GRADING_VERSION`, and `INPUT_VERSION` stay in their model files as resolved
in SP-01 (§9.8 of that PRD). They are the single source of truth for SP-04's log dimensions and
for `version_value` / `Literal` pins on the concrete model. Moving them to `utils/constants.py`
would create a circular dependency risk (models import from utils; utils would then define model
version strings independently from the models that use them) and would conflict with SP-01's
resolved design. SP-12 does not touch `models/`.

### 4.6 `frontend/src/constants.ts` — new file (API path strings)

Create `frontend/src/constants.ts`:

```typescript
// frontend/src/constants.ts
// All API path strings. API_URL (the base URL from env) stays in api/firebase.ts.
// VERSIONS array (UI display config) stays in config.ts.

export const CARE_PLAN_PATH = '/care_plan';
export const SAVED_OUTPUTS_PATH = '/care_plan/saved';
export const BATCH_PATH = '/care_plan/batch';
export const DATASETS_PATH = '/care_plan/datasets';

// Per-ID paths are template helpers rather than bare strings.
// Callers: savedOutputPath(id) === '/care_plan/saved/<id>'
export const savedOutputPath = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}`;
export const inputPdfUrlPath  = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}/input-pdf-url`;
export const datasetFilePath  = (group: string, input: string, file: string) =>
  `${DATASETS_PATH}/${encodeURIComponent(group)}/${encodeURIComponent(input)}/${encodeURIComponent(file)}`;

// Moved from config.ts (these are pipeline-selection strings, not UI display config).
export const DEFAULT_VERSION = 'v1-2';
export { CARE_PLAN_PATH as CARE_PLAN_API_PATH };  // alias — config.ts re-exports it
```

**Why template helpers instead of bare path strings for per-ID paths:**  
Per-ID paths (`/care_plan/saved/${id}`) require interpolation at the call site. Exporting a bare
`'/care_plan/saved/'` prefix still leaves callers writing inline strings. Template helpers
eliminate that residual inline string while keeping callers readable. Each helper is a one-liner,
not a class.

**`CARE_PLAN_API_PATH` alias:** `config.ts` currently exports `CARE_PLAN_API_PATH` and
`CarePlanPage.tsx` imports it from there. During transition `config.ts` re-exports the alias
from `constants.ts` so `CarePlanPage.tsx` can keep its `from '../../config'` import while the
canonical name moves. (See §4.8 for the `config.ts` change.)

**`DEFAULT_VERSION` co-location:** `DEFAULT_VERSION` moves to `constants.ts` because it selects a
pipeline version — it is the same semantic kind as `CARE_PLAN_PATH`. `CarePlanPage.tsx` uses it
to pre-select the SSE pipeline version sent to the backend. Keeping it next to `CARE_PLAN_PATH`
means both the path and the default version are in one file.

### 4.7 `frontend/src/api/savedOutputs.ts` — import path constants

Old (inline):
```typescript
`${API_URL}/care_plan/saved`
`${API_URL}/care_plan/saved/${id}`
`${API_URL}/care_plan/saved/${id}/input-pdf-url`
```

New:
```typescript
import { SAVED_OUTPUTS_PATH, savedOutputPath, inputPdfUrlPath } from '../constants';

`${API_URL}${SAVED_OUTPUTS_PATH}`           // listSavedOutputs
`${API_URL}${savedOutputPath(id)}`          // getSavedOutput, renameSavedOutput, deleteSavedOutput
`${API_URL}${inputPdfUrlPath(id)}`          // getInputPdfUrl
```

### 4.8 `frontend/src/api/datasets.ts` — import path constants

Old (inline):
```typescript
`${API_URL}/care_plan/datasets`
`${API_URL}/care_plan/datasets/${encodedGroup}/${encodedInput}/${encodedFilename}`
`${API_URL}/care_plan/batch`
```

New:
```typescript
import { DATASETS_PATH, BATCH_PATH, datasetFilePath } from '../constants';

`${API_URL}${DATASETS_PATH}`                               // listDatasets
`${API_URL}${datasetFilePath(group, input, filename)}`     // getDatasetFileContent (encode inside helper)
`${API_URL}${BATCH_PATH}`                                  // runBatch
```

`datasetFilePath` absorbs the three `encodeURIComponent` calls currently inline in `datasets.ts`.

### 4.9 `frontend/src/pages/care-plan/CarePlanPage.tsx` — import from constants

Old:
```typescript
import { CARE_PLAN_API_PATH, DEFAULT_VERSION } from '../../config';
// …
`${API_URL}${CARE_PLAN_API_PATH}`    // line 255
const selectedVersion = DEFAULT_VERSION;  // line 62
```

New:
```typescript
import { CARE_PLAN_API_PATH, DEFAULT_VERSION } from '../../constants';
// everything else unchanged
```

The component import path changes from `'../../config'` to `'../../constants'`; the two names are
identical so no further edits are needed inside the component body.

### 4.10 `frontend/src/config.ts` — re-export alias, drop moved items

```typescript
// frontend/src/config.ts

// CARE_PLAN_API_PATH and DEFAULT_VERSION moved to constants.ts.
// Re-export for any file that still imports from config (only CarePlanPage; updated in §4.9).
export { CARE_PLAN_API_PATH, DEFAULT_VERSION } from './constants';

// VERSIONS stays here — it is UI display config, not an API endpoint path.
export const VERSIONS = [ … ] as const;
```

Once `CarePlanPage.tsx` is updated (§4.9), the re-exports in `config.ts` are technically dead. A
follow-up cleanup can remove them. For SP-12 they remain as a safety net in case any import was
missed.

## 5. API Change Summary

N/A — this is a pure internal refactor. No routes, request shapes, response shapes, or SSE events
change.

## 6. Frontend Change Summary

No visible behavior changes. Changes are import-only:

| File | Change |
|---|---|
| `src/constants.ts` | **New file.** Exports all API path strings and template helpers. |
| `src/config.ts` | Remove `CARE_PLAN_API_PATH` and `DEFAULT_VERSION`; re-export them from `constants.ts`. Keep `VERSIONS`. |
| `src/api/savedOutputs.ts` | Replace 4 inline path strings with imports from `constants.ts`. |
| `src/api/datasets.ts` | Replace 3 inline path strings + 3 `encodeURIComponent` calls with imports from `constants.ts`. |
| `src/pages/care-plan/CarePlanPage.tsx` | Change import source for `CARE_PLAN_API_PATH` / `DEFAULT_VERSION` from `config` to `constants`. |

`API_URL` (env-var base URL) stays in `api/firebase.ts` — it is a runtime value resolved from an
env var, not a path constant.

## 7. Testing

SP-12 is a refactor with no logic changes; existing tests are the primary safety net. No new test
files are required, but the following checks should pass without modification after SP-12 lands:

- **Backend unit tests** covering route request handling (`test_routes_care_plan.py`,
  `test_routes_batch.py`): all file-limit and version-validation paths must pass unchanged —
  they exercise the same limits, just now pulled from `Constants`.
- **`test_utils_constants.py`** (if it exists) or a quick sanity assertion:
  `Constants.ALLOWED_VERSIONS == frozenset({"v1-2"})` and
  `Constants.MAX_FILE_BYTES == 10 * 1024 * 1024`.
- **Frontend TypeScript build** (`tsc --noEmit`) must pass after the new `constants.ts` is created
  and all consumers are updated — this catches any broken import path or missing export.
- **Frontend unit/integration tests**: any test that mocked `config.CARE_PLAN_API_PATH` or
  `config.DEFAULT_VERSION` must update its import path to `constants`.

One deliberate behavioral note: `ALLOWED_EXTENSIONS` changes from `set` to `frozenset`. Any
backend test that does `assert type(ALLOWED_EXTENSIONS) == set` will fail; the correct assertion is
`isinstance(Constants.ALLOWED_EXTENSIONS, frozenset)` or simply `"pdf" in Constants.ALLOWED_EXTENSIONS`.

## 8. Manual Intervention Required From You

None required for this sub-project. SP-12 is a pure refactor with no deployment-config changes, no
Firestore schema changes, no new env vars, and no dependency additions.

Optional post-ship cleanup (not blocking):
- Once all consumers import from `constants.ts` directly, the re-export stubs in `config.ts`
  (`CARE_PLAN_API_PATH`, `DEFAULT_VERSION`) can be removed in a follow-up.

## 9. Open Questions & Decisions

1. **Should `RESULT_SENTINEL` move to `Constants`?**
   `[RESOLVED: Yes. It is currently imported by both `routes/care_plan.py` (where it is defined)
   and `routes/batch.py` (which imports it cross-route). Moving it to `Constants` removes that
   cross-route import, which is the same motivation as moving `ALLOWED_VERSIONS`.]`

2. **Should model version constants (`CARE_PLAN_VERSION`, `GRADING_VERSION`, `INPUT_VERSION`) move
   to `utils/constants.py`?**
   `[RESOLVED: No. SP-01 §9.8 explicitly placed them in their respective model files as the single
   source of truth for both the model's `version_value`/`Literal` pin and SP-04's log dimensions.
   Moving them would conflict with SP-01's resolved design and risk circular imports. They stay in
   `models/`.]`

3. **Should `PIPELINES` dict move to `Constants`?**
   `[RESOLVED: No. The dict values are callable references (the `run_care_plan_pipeline` function
   defined in `routes/care_plan.py`). Moving the dict to `constants.py` would require importing a
   route-level function into a utils module, inverting the dependency direction. Only the key string
   `"v1-2"` (now `PIPELINE_VERSION_V1_2`) moves to `Constants`; the dict stays in the route.]`

4. **`frozenset` vs `set` for `ALLOWED_EXTENSIONS` and `ALLOWED_VERSIONS`?**
   `[RESOLVED: `frozenset`. Class-level constants should be immutable; `frozenset` enforces that at
   the language level at zero runtime cost. Membership tests (`"pdf" in Constants.ALLOWED_EXTENSIONS`)
   are identical in syntax. Any test asserting `type(...) == set` will need updating (see §7).]`

5. **Should `DEFAULT_VERSION` and `CARE_PLAN_API_PATH` move from `config.ts` or stay?**
   `[RESOLVED: Both move to `constants.ts`. `CARE_PLAN_API_PATH` is an API path string — the
   defining criterion for `constants.ts`. `DEFAULT_VERSION` selects a pipeline version key, which
   is the same semantic kind as `CARE_PLAN_PATH`; co-locating them makes it obvious that the
   default version `"v1-2"` corresponds to the endpoint `/care_plan`. `config.ts` re-exports both
   names as an alias for the transition period.]`

6. **Should `VERSIONS` array move from `config.ts` to `constants.ts`?**
   `[RESOLVED: No. `VERSIONS` is UI display config — labels, descriptions, steps text rendered in
   `VersionsPage`. It is not an API path string. It stays in `config.ts`.]`

7. **`datasetFilePath` template helper absorbs `encodeURIComponent` calls — is that the right
   boundary?**
   `[RESOLVED: Yes. The three `encodeURIComponent` calls in `datasets.ts:getDatasetFileContent`
   are tightly coupled to the path structure of `/care_plan/datasets/${group}/${input}/${file}`.
   Moving them into `datasetFilePath` removes a 4-line inline construction and makes the helper
   self-contained. `datasets.ts` passes raw strings; encoding is an implementation detail of the
   path helper.]`

8. **Should `config.py`'s `CARE_PLAN_DEFAULT_VERSION` be replaced everywhere by
   `Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK`?**
   `[RESOLVED: No. `CARE_PLAN_DEFAULT_VERSION` in `config.py` is an env-resolved runtime value
   (`os.getenv(...)`). Both `routes/care_plan.py` and `routes/batch.py` import it from `config`.
   SP-12 keeps that resolved name in `config.py` (now composed from `Constants` env-var name +
   fallback) and both routes continue to import from `config`. This is consistent with the other
   GCP env reads in `config.py` and avoids touching both routes just to change an import source.]`
