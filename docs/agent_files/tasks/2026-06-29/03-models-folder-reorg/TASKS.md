# SP03 Models Folder Reorganization — TASKS

## Prerequisites

Reorganize `backend/models/` into structured sub-packages (`care_plan/`, `external_api/`), delete dead code, and move `ResolvedInput` from route code into `models/input.py` as a `JsonModel`. Assumes SP01 (error hierarchy) and SP02 are fully complete and deployed; this SP does NOT depend on SP04+.

---

## Tasks

### Task 03.1: Delete dead code — `athena_manifest.py` and its test

**Goal:** Remove the five dead manifest models and their test file; they are never imported by production code and exist only to satisfy a test that reads from preset-data JSON.

**Files:**
- `backend/models/athena_manifest.py` — DELETE
- `backend/tests/models/test_athena_manifest.py` — DELETE

**Steps:**
1. Delete `backend/models/athena_manifest.py`.
2. Delete `backend/tests/models/test_athena_manifest.py`.
3. Verify no other file imports from `models.athena_manifest` or `athena_manifest`:
   ```
   grep -r "athena_manifest" backend/ --include="*.py"
   ```
   Expected: zero results after deletion.

**Acceptance:**
- Both files are gone from the repository.
- `grep -r "athena_manifest" backend/ --include="*.py"` returns zero lines.
- `pytest tests/models/ -v` passes (the deleted test is simply absent).

**Commit:** `chore: delete dead models/athena_manifest.py and its test`

---

### Task 03.2: Extract `AthenaAPIError` into `models/external_api/athena_errors.py`

**Goal:** Move the `AthenaAPIError` class out of `utils/athena_client.py` into a new `models/external_api/` package so it lives with domain models rather than utility code.

**Files (create):**
- `backend/models/external_api/__init__.py`
- `backend/models/external_api/athena_errors.py`

**Files (edit):**
- `backend/utils/athena_client.py` — remove class definition, add import

**Steps:**
1. Create directory `backend/models/external_api/` (mkdir is implicit when creating files).
2. Create `backend/models/external_api/athena_errors.py` with this exact content:
   ```python
   """Athena Health API error types."""


   class AthenaAPIError(Exception):
       """Raised when an Athena API call returns a non-200 status."""

       def __init__(self, status_code: int, body: str) -> None:
           self.status_code = status_code
           self.body = body
           super().__init__(f"Athena API error {status_code}: {body[:200]}")
   ```
   Note: SP01 defines `JunoError` as the project-wide base exception. When SP01 lands, update `AthenaAPIError` to inherit from `JunoError` instead of `Exception`. For now keep `Exception` to avoid a cross-SP dependency.

3. Create `backend/models/external_api/__init__.py` — leave it empty for now (populated fully in Task 03.3 after `athena_models.py` exists).

4. In `backend/utils/athena_client.py`:
   - Remove lines 24–30 (the `AthenaAPIError` class definition and its docstring).
   - Add the following import near the top of the file (after `from utils.constants import Constants`):
     ```python
     from models.external_api.athena_errors import AthenaAPIError
     ```
   - The three raise-sites at the original lines 64, 82, and 90 are unchanged — they already reference `AthenaAPIError` by name.

5. Run the import smoke test:
   ```bash
   cd /root/projects/juno/backend
   python -c "from models.external_api.athena_errors import AthenaAPIError; print('OK')"
   python -c "from utils.athena_client import AthenaAPIError; print('re-export OK')"
   ```

**Acceptance:**
- `models/external_api/athena_errors.py` exists and defines `AthenaAPIError`.
- `utils/athena_client.py` no longer defines `AthenaAPIError`; it imports it from the new location.
- `pytest tests/utils/test_athena_client.py -v` passes.

**Commit:** `refactor: extract AthenaAPIError to models/external_api/athena_errors.py`

---

### Task 03.3: Move Athena models to `models/external_api/athena_models.py`

**Goal:** Move the 11 Athena request/response models from `models/athena.py` into `models/external_api/athena_models.py` and expose them through the package `__init__.py`. Delete the old `models/athena.py`.

**Files (create):**
- `backend/models/external_api/athena_models.py`

**Files (edit):**
- `backend/models/external_api/__init__.py` — add full re-exports
- `backend/models/athena.py` — DELETE after move

**Steps:**
1. Create `backend/models/external_api/athena_models.py` with the full content of `backend/models/athena.py` (copy verbatim — no import changes needed; the file uses only `pydantic` imports). Keep `extra="allow"` on every model unchanged; tightening to `extra="forbid"` is deferred to SP04.

2. Overwrite `backend/models/external_api/__init__.py` with:
   ```python
   """External API model re-exports."""

   from .athena_errors import AthenaAPIError
   from .athena_models import (
       AthenaTokenRequest,
       AthenaTokenResponse,
       AthenaEncounterSummaryRequest,
       AthenaEncounterSummaryResponse,
       AthenaClinicalDocumentMeta,
       AthenaClinicalDocumentListRequest,
       AthenaClinicalDocumentListResponse,
       AthenaClinicalDocumentContentRequest,
       AthenaClinicalDocumentContentResponse,
       AthenaPushDocumentRequest,
       AthenaPushDocumentResponse,
   )

   __all__ = [
       "AthenaAPIError",
       "AthenaTokenRequest",
       "AthenaTokenResponse",
       "AthenaEncounterSummaryRequest",
       "AthenaEncounterSummaryResponse",
       "AthenaClinicalDocumentMeta",
       "AthenaClinicalDocumentListRequest",
       "AthenaClinicalDocumentListResponse",
       "AthenaClinicalDocumentContentRequest",
       "AthenaClinicalDocumentContentResponse",
       "AthenaPushDocumentRequest",
       "AthenaPushDocumentResponse",
   ]
   ```

3. Delete `backend/models/athena.py`.

4. Confirm no file still imports from `models.athena` (the old path):
   ```
   grep -r "from models.athena import\|from models import.*Athena\|models\.athena" backend/ --include="*.py"
   ```
   Expected: zero results (Athena models are currently unused in production code).

5. Run:
   ```bash
   cd /root/projects/juno/backend
   python -c "from models.external_api import AthenaTokenRequest, AthenaAPIError; print('OK')"
   ```

**Acceptance:**
- `models/external_api/athena_models.py` exists with all 11 Athena model classes.
- `models/external_api/__init__.py` re-exports all 11 models plus `AthenaAPIError`.
- `models/athena.py` is deleted.
- Import smoke test passes.

**Commit:** `refactor: move Athena models to models/external_api/athena_models.py`

---

### Task 03.4: Reorganize care-plan models into `models/care_plan/`

**Goal:** Move `models/care_plan.py`, `models/envelope.py`, and `models/care_plan_versions/v1_2.py` into a new `models/care_plan/` sub-package with a `versions/` sub-directory. Fix the stale docstring. Delete `models/care_plan_versions/`.

**Files (create):**
- `backend/models/care_plan/__init__.py`
- `backend/models/care_plan/care_plan.py`
- `backend/models/care_plan/envelope.py`
- `backend/models/care_plan/versions/__init__.py`
- `backend/models/care_plan/versions/v1_2.py`

**Files (delete):**
- `backend/models/care_plan.py`
- `backend/models/envelope.py`
- `backend/models/care_plan_versions/v1_2.py`
- `backend/models/care_plan_versions/` (directory, once empty)

**Steps:**

1. Create `backend/models/care_plan/care_plan.py`:
   - Copy content from `backend/models/care_plan.py`.
   - Fix the stale docstring on line 8 from:
     ```python
     """Version-agnostic care-plan family base. Concrete versions live in care_plan/v*/models.py."""
     ```
     to:
     ```python
     """Version-agnostic care-plan family base. Concrete versions live in models/care_plan/versions/."""
     ```
   - Update the relative import of `VersionedModel`:
     ```python
     # Old
     from .base import VersionedModel
     # New (one level up from models/care_plan/ to models/)
     from ..base import VersionedModel
     ```

2. Create `backend/models/care_plan/envelope.py`:
   - Copy content from `backend/models/envelope.py`.
   - Update all relative imports:
     ```python
     # Old → New
     from .base import JsonModel          →  from ..base import JsonModel
     from .care_plan import CarePlan      →  from .care_plan import CarePlan   (unchanged; same package)
     from .grading import Grading         →  from ..grading import Grading
     from .input import Input             →  from ..input import Input
     from .metrics import Metrics         →  from ..metrics import Metrics
     ```

3. Create `backend/models/care_plan/versions/v1_2.py`:
   - Copy content from `backend/models/care_plan_versions/v1_2.py`.
   - Replace absolute model imports with relative ones:
     ```python
     # Old
     from models.base import JsonModel
     from models.care_plan import CarePlan
     # New (two levels up from models/care_plan/versions/ to models/)
     from ...base import JsonModel
     from ..care_plan import CarePlan
     ```
   - The `from utils.constants import Constants` import is absolute and stays unchanged.

4. Create `backend/models/care_plan/__init__.py`:
   ```python
   """Care-plan domain model re-exports.

   NOTE: backend/care_plan/ is the pipeline-logic package (CarePlanPipeline, CarePlanV1_2Pipeline).
   This package (models/care_plan/) contains only the Pydantic domain models for the care-plan family.
   Import from `care_plan.*` for pipeline code; import from `models.care_plan.*` for model types.
   """

   from .care_plan import CarePlan
   from .envelope import CarePlanInternal
   from .versions.v1_2 import CarePlanV1_2

   __all__ = ["CarePlan", "CarePlanInternal", "CarePlanV1_2"]
   ```

5. Create `backend/models/care_plan/versions/__init__.py`:
   ```python
   from .v1_2 import CarePlanV1_2

   __all__ = ["CarePlanV1_2"]
   ```

6. Delete:
   - `backend/models/care_plan.py`
   - `backend/models/envelope.py`
   - `backend/models/care_plan_versions/v1_2.py`
   - `backend/models/care_plan_versions/` directory (now empty)

7. Run:
   ```bash
   cd /root/projects/juno/backend
   python -c "
   from models.care_plan.care_plan import CarePlan
   from models.care_plan.envelope import CarePlanInternal
   from models.care_plan.versions.v1_2 import CarePlanV1_2
   print('All care-plan imports OK')
   print('CarePlan registry:', CarePlan._registry)
   "
   ```
   `CarePlan._registry` must contain `{'1.2': <class '...CarePlanV1_2'>}`.

**Acceptance:**
- All five new files exist; all three old files and the `care_plan_versions/` directory are deleted.
- Import smoke test passes and registry contains `CarePlanV1_2`.
- `pytest tests/models/test_care_plan.py tests/models/test_envelope.py -v` passes after Task 03.6 updates those test imports (or passes now if they go through the top-level re-export, which is updated in Task 03.5).

**Commit:** `refactor: reorganize care-plan models into models/care_plan/`

---

### Task 03.5: Update `models/__init__.py` top-level re-exports

**Goal:** Update `backend/models/__init__.py` to import from the new internal paths while keeping the public surface identical. Add `ResolvedInput` to the public surface (new export, needed before Task 03.6 moves it).

**Files (edit):**
- `backend/models/__init__.py`

**Steps:**
1. Replace the entire content of `backend/models/__init__.py` with:
   ```python
   """Backend model exports."""

   from .base import JsonModel, VersionedModel
   from .errors import ApiResponse, ErrorDetail, StatusEnum
   from .care_plan.care_plan import CarePlan
   from .care_plan.envelope import CarePlanInternal
   from .grading import Grading, GradingEntry, build_grading
   from .input import Input, InputFile, FileInput, TextInput, DocIdInput, BatchDatasetInput, ResolvedInput
   from .metrics import Metrics
   # Import to trigger CarePlanV1_2 self-registration in CarePlan._registry.
   from .care_plan.versions.v1_2 import CarePlanV1_2  # noqa: F401

   __all__ = [
       "JsonModel",
       "VersionedModel",
       "ApiResponse",
       "ErrorDetail",
       "StatusEnum",
       "CarePlan",
       "CarePlanInternal",
       "Grading",
       "GradingEntry",
       "build_grading",
       "Input",
       "InputFile",
       "FileInput",
       "TextInput",
       "DocIdInput",
       "BatchDatasetInput",
       "ResolvedInput",
       "Metrics",
       "CarePlanV1_2",
   ]
   ```
   Note: `ResolvedInput` is listed in `__all__` and the import line. It will be added to `models/input.py` in Task 03.6 — this file must be committed after Task 03.6, or the `ResolvedInput` import line must be added in Task 03.6's commit if done atomically.

   > Note: To avoid an import error between tasks, add the `ResolvedInput` line to this file in the same commit as Task 03.6 (i.e., treat this file's final form as part of Task 03.6). For now in this task, update only the care-plan import paths (`.care_plan.care_plan`, `.care_plan.envelope`, `.care_plan.versions.v1_2`) and leave the `ResolvedInput` line out until Task 03.6.

2. Run:
   ```bash
   cd /root/projects/juno/backend
   python -c "from models import CarePlan, CarePlanInternal, CarePlanV1_2, Input, Metrics, Grading; print('top-level re-exports OK')"
   ```

**Acceptance:**
- `from models import CarePlan, CarePlanInternal, CarePlanV1_2` all work.
- `pytest tests/models/ -v` passes (the test files that import via `models.care_plan` path are updated in Task 03.6).

**Commit:** `chore: update models/__init__.py to import from new internal paths`

---

### Task 03.6: Move `ResolvedInput` into `models/input.py` as a `JsonModel`; update call sites

**Goal:** Remove the `@dataclass ResolvedInput` from `routes/care_plan.py` and add it as a `JsonModel` to `models/input.py`. Rename `combined_pdf_bytes: bytes | None` to `combined_pdf_size: float | None` to store only the byte count (a plain `float`/double) rather than the actual binary data. Update the calling code so the PDF bytes are uploaded before constructing `ResolvedInput`, and the size is stored for observability.

> Note (Q3 decision): The PRD proposed `combined_pdf_bytes: bytes | None` on `ResolvedInput` as a `JsonModel` field. The user decision is to store the PDF size as a `float` (double) instead of carrying raw `bytes` in the model. This avoids the non-JSON-serializable bytes field entirely while keeping useful metadata. The raw bytes still flow through the route code as a local variable; they are uploaded to GCS before `ResolvedInput` is constructed, and only the byte count is stored on the model for observability/logging.

**Files (edit):**
- `backend/models/input.py` — add `ResolvedInput` class
- `backend/models/__init__.py` — add `ResolvedInput` to the import line and `__all__`
- `backend/routes/care_plan.py` — remove `@dataclass`, add import
- `backend/routes/care_plan_jobs.py` — refactor `_resolve_input_for_job` to upload PDF before calling `_resolve_uploaded_files`

**Steps:**

1. **`backend/models/input.py`** — append the following class at the bottom of the file (after the `Input` union definition):
   ```python
   class ResolvedInput(JsonModel):
       """Structured representation of a resolved pipeline input.

       Built in route helpers before the pipeline is invoked; carries the extracted
       text, metadata about the source, and (for file inputs) the size in bytes of
       the merged PDF that was produced and uploaded to GCS.

       combined_pdf_size stores the byte count of the merged PDF as a float for
       observability. The raw bytes are uploaded to GCS by the caller before this
       object is constructed; this model never holds binary data directly.
       """

       text: str
       source_description: str
       source_filename: str
       combined_pdf_size: float | None = None
       source_kind: str = "upload"
       file_count: int = 0
       file_types: list[str] = Field(default_factory=list)
   ```

2. **`backend/routes/care_plan.py`**:
   - Remove line 13: `from dataclasses import dataclass`
   - Remove the `@dataclass` class block (lines 75–88, the `ResolvedInput` dataclass and its `__post_init__`).
   - Add import:
     ```python
     from models.input import ResolvedInput
     ```
   - In `_resolve_uploaded_files()` (currently around line 153), refactor the return statement:
     - Before the `return ResolvedInput(...)` call, capture `combined_pdf_size`:
       ```python
       combined_pdf_size = float(len(combined_pdf_bytes)) if combined_pdf_bytes is not None else None
       ```
     - Change the `ResolvedInput(...)` instantiation:
       ```python
       return ResolvedInput(
           text="\n".join(text_parts).strip(),
           source_description=source_filename,
           source_filename=source_filename,
           combined_pdf_size=combined_pdf_size,
           file_count=file_count,
           file_types=file_types,
       ), combined_pdf_bytes
       ```
     - Update the return type annotation to `-> tuple[ResolvedInput, bytes | None]`.

3. **`backend/routes/care_plan_jobs.py`** — in `_resolve_input_for_job()`, update the file-upload branch to unpack the new tuple return:
   ```python
   resolved, raw_pdf_bytes = _resolve_uploaded_files(uploads)
   pdf_gcs_uri = None
   if raw_pdf_bytes:
       pdf_gcs_uri = upload_combined_pdf(raw_pdf_bytes, user_id)
   ```
   Remove the old `if resolved.combined_pdf_bytes:` check (now replaced by `if raw_pdf_bytes:`).

4. **`backend/models/__init__.py`** — finalize the `ResolvedInput` export:
   - Update the `.input` import line to include `ResolvedInput`:
     ```python
     from .input import Input, InputFile, FileInput, TextInput, DocIdInput, BatchDatasetInput, ResolvedInput
     ```
   - Add `"ResolvedInput"` to `__all__`.

5. Run:
   ```bash
   cd /root/projects/juno/backend
   python -c "
   from models.input import ResolvedInput
   r = ResolvedInput(text='hello', source_description='test', source_filename='test.pdf', combined_pdf_size=1024.0, file_types=['pdf'])
   print('ResolvedInput OK:', r)
   "
   ```

**Acceptance:**
- `models/input.py` exports `ResolvedInput` as a `JsonModel` with `combined_pdf_size: float | None`.
- `routes/care_plan.py` has no `@dataclass` import or `ResolvedInput` class definition; it imports `ResolvedInput` from `models.input`.
- `routes/care_plan_jobs.py` unpacks the tuple and uses `raw_pdf_bytes` for the GCS upload.
- `from models import ResolvedInput` works.
- `pytest tests/models/test_input_metrics.py -v` passes.

**Commit:** `refactor: move ResolvedInput to models/input.py as JsonModel; store pdf size as float`

---

### Task 03.7: Update all internal call-site imports to canonical new paths

**Goal:** Update every file that still uses stale import paths (`models.care_plan` the old flat module, `models.envelope`, `models.care_plan_versions.v1_2`, `utils.athena_client.AthenaAPIError`) to use the new canonical paths. Update the affected test files.

**Files (edit):**

Production code:
- `backend/routes/worker.py` — `models.envelope`, `models.care_plan` (if present)
- `backend/routes/care_plan.py` — `models.care_plan`, `models.envelope` (old flat imports from lines 30–31)
- `backend/care_plan/v1_2/pipeline.py` — `models.care_plan` and `models.care_plan_versions.v1_2`

Test files:
- `backend/tests/models/test_care_plan.py` — imports `models.care_plan` and `models.care_plan_versions.v1_2`
- `backend/tests/models/test_envelope.py` — imports `models.care_plan_versions.v1_2`
- `backend/tests/care_plan/test_pipeline_schema.py` — imports `models.care_plan_versions.v1_2`
- `backend/tests/models/test_readpath_tolerance.py` — imports `models.care_plan_versions.v1_2`
- `backend/tests/utils/test_athena_client.py` — may import `AthenaAPIError` from `utils.athena_client`

**Steps:**

1. **`backend/routes/worker.py`**:
   - Change `from models.envelope import CarePlanInternal` → `from models.care_plan.envelope import CarePlanInternal`
   - If line 220 contains `from utils.athena_client import athena_client, AthenaAPIError`, split to:
     ```python
     from utils.athena_client import athena_client
     from models.external_api.athena_errors import AthenaAPIError
     ```

2. **`backend/routes/care_plan.py`**:
   - Change `from models.care_plan import CarePlan` (line 30) → `from models.care_plan.care_plan import CarePlan`
   - Change `from models.envelope import CarePlanInternal` (line 31) → `from models.care_plan.envelope import CarePlanInternal`

3. **`backend/care_plan/v1_2/pipeline.py`**:
   - Change `from models.care_plan import CarePlan` → `from models.care_plan.care_plan import CarePlan`
   - Change `from models.care_plan_versions.v1_2 import CarePlanV1_2` → `from models.care_plan.versions.v1_2 import CarePlanV1_2`

4. **`backend/tests/models/test_care_plan.py`**:
   - Change `from models.care_plan import CarePlan` → `from models.care_plan.care_plan import CarePlan`
   - Change `from models.care_plan_versions.v1_2 import CarePlanV1_2, Diagnosis` → `from models.care_plan.versions.v1_2 import CarePlanV1_2, Diagnosis`

5. **`backend/tests/models/test_envelope.py`**:
   - Change `from models.care_plan_versions.v1_2 import CarePlanV1_2` → `from models.care_plan.versions.v1_2 import CarePlanV1_2`

6. **`backend/tests/care_plan/test_pipeline_schema.py`**:
   - Change `from models.care_plan_versions.v1_2 import CarePlanV1_2` → `from models.care_plan.versions.v1_2 import CarePlanV1_2`

7. **`backend/tests/models/test_readpath_tolerance.py`**:
   - Change `from models.care_plan_versions.v1_2 import CarePlanV1_2` → `from models.care_plan.versions.v1_2 import CarePlanV1_2`

8. **`backend/tests/utils/test_athena_client.py`**:
   - If it imports `AthenaAPIError` from `utils.athena_client`, change to `from models.external_api.athena_errors import AthenaAPIError`.

9. Confirm no stale paths remain:
   ```bash
   grep -r "models\.care_plan_versions\|models\.envelope\|from models\.care_plan import\|from models import.*CarePlan[^V]" \
     /root/projects/juno/backend --include="*.py" | grep -v ".venv"
   ```
   Expected: zero results.

10. Run full smoke test:
    ```bash
    cd /root/projects/juno/backend
    python -c "
    from models.care_plan.care_plan import CarePlan
    from models.care_plan.envelope import CarePlanInternal
    from models.care_plan.versions.v1_2 import CarePlanV1_2
    from models.external_api.athena_models import AthenaTokenRequest
    from models.external_api.athena_errors import AthenaAPIError
    from models.input import ResolvedInput
    from models import CarePlan, CarePlanInternal, CarePlanV1_2, Input, Metrics, Grading, ResolvedInput
    print('All imports OK')
    print('CarePlan registry:', CarePlan._registry)
    "
    ```

**Acceptance:**
- All stale import paths are gone from production and test code.
- Full smoke test prints `All imports OK` and shows registry `{'1.2': ...CarePlanV1_2...}`.
- `pytest tests/models/ tests/care_plan/ tests/utils/test_athena_client.py -v` passes with no import errors.

**Commit:** `chore: update all import paths to new canonical model locations`

---

## Verification

After all tasks are complete, run these commands from `backend/`:

```bash
cd /root/projects/juno/backend

# 1. Full top-level import smoke test
python -c "
from models.care_plan.care_plan import CarePlan
from models.care_plan.envelope import CarePlanInternal
from models.care_plan.versions.v1_2 import CarePlanV1_2
from models.external_api.athena_models import AthenaTokenRequest
from models.external_api.athena_errors import AthenaAPIError
from models.input import ResolvedInput
from models import CarePlan, CarePlanInternal, CarePlanV1_2, Input, Metrics, Grading, ResolvedInput
print('All imports OK')
print('CarePlan registry:', CarePlan._registry)
"
# Expected: prints 'All imports OK' and registry = {'1.2': <class '...CarePlanV1_2'>}

# 2. Run affected tests only
pytest tests/models/ tests/care_plan/ tests/utils/test_athena_client.py -v

# 3. Confirm no stale paths remain
grep -r "models\.care_plan_versions\|from models\.envelope\|from models\.care_plan import\|athena_manifest" \
  /root/projects/juno/backend --include="*.py" | grep -v ".venv"
# Expected: zero lines

# 4. Lint check (if project uses ruff or flake8)
ruff check backend/models/ backend/routes/ backend/tests/models/ 2>/dev/null || true
```

**Definition of done:**
- All 7 tasks committed individually with their prescribed commit messages.
- Smoke test prints `All imports OK` with registry populated.
- Affected pytest suite passes (no failures, no import errors).
- Stale-path grep returns zero results.
- `models/athena_manifest.py`, `models/athena.py`, `models/care_plan.py`, `models/envelope.py`, `models/care_plan_versions/` are all absent from the repository.
- `ResolvedInput` is a `JsonModel` in `models/input.py` with `combined_pdf_size: float | None` (no `bytes` field).
