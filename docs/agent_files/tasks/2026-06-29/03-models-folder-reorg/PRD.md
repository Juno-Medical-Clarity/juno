# PRD: SP03 — Models Folder Reorganization

**Sub-project:** SP03  
**Branch context:** `users/tejitpabari/llm-code-check` (or a clean branch off `main`)  
**Date:** 2026-06-29  
**Status:** Planning — no implementation started

---

## 1. Problem

The `backend/models/` directory is a flat pile of 9 files with no internal structure. Three separate concerns are co-located with no clear grouping:

1. **Care-plan domain models** (`care_plan.py`, `envelope.py`, `care_plan_versions/v1_2.py` and its 11 sub-models) — the largest family, with an orphaned subdirectory (`care_plan_versions/`) that looks like a misspelling of the `care_plan/` package elsewhere in the backend.
2. **External API contract models** (`athena.py`, 12 models for Athena Health requests/responses) — currently dead/unused but needed for SP04; use `extra="allow"` in violation of the house `extra="forbid"` standard.
3. **Dead code** (`athena_manifest.py`) — 5 models that live only to satisfy a test file; the models are never imported by production code.

Additionally, `ResolvedInput` is a plain Python `@dataclass` defined inside `routes/care_plan.py` (line 75) — the only dataclass in route code. It describes structured pipeline input and belongs with the rest of the input models.

The stale docstring in `models/care_plan.py` line 8 claims *"Concrete versions live in care_plan/v*/models.py"* but the concrete version lives at `models/care_plan_versions/v1_2.py`.

---

## 2. Goals

1. Group care-plan models into `models/care_plan/` with a `versions/` sub-directory for concrete version types.
2. Create `models/external_api/` to house Athena request/response models and the `AthenaAPIError` exception class (currently at `utils/athena_client.py:24`).
3. Delete `models/athena_manifest.py` and its test file `tests/models/test_athena_manifest.py` — both are dead.
4. Move `ResolvedInput` from `routes/care_plan.py` into `models/input.py`, converting it from a `@dataclass` to a `JsonModel`.
5. Fix the stale comment in `models/care_plan.py` (line 8).
6. Keep `models/__init__.py` re-exports stable so `from models import X` call sites outside `models/` require zero changes for everything except `ResolvedInput` (which gets a new home — update its two call sites in routes).
7. Leave `models/grading.py`, `models/metrics.py`, and `models/errors.py` exactly where they are.

**What this SP does NOT do:** Wire the Athena models into the HTTP client (SP04). Define `models/job.py` (SP05). Touch pipeline logic (SP07). Touch the error system (SP01, which provides `JunoError` that SP04 will wire into `AthenaAPIError`).

---

## 3. Non-Goals

- Implementing or wiring Athena HTTP client calls — that is SP04.
- Tightening Athena model `extra` config to `"forbid"` unilaterally — see open question Q1.
- Moving `models/base.py` — it stays top-level (RESOLVED, see §9).
- Creating a `models/manifest/` folder — explicitly decided against (RESOLVED, see §9).
- Adding `models/job.py` — that is SP05.
- Changing the SP01 error hierarchy — SP01 defines `JunoError`; this SP only relocates `AthenaAPIError` and keeps it as a plain `Exception` subclass until SP01 lands.
- Frontend changes — N/A.
- Changing any API response shapes.

---

## 4. Architecture Decisions

### A. Target Directory Layout

```
backend/models/
    base.py                           # UNCHANGED — shared base for all models
    input.py                          # UPDATED — gains ResolvedInput
    grading.py                        # UNCHANGED
    metrics.py                        # UNCHANGED
    errors.py                         # UNCHANGED (SP01 owns this)
    __init__.py                       # UPDATED — re-exports kept stable
    care_plan/
        __init__.py                   # NEW — re-exports the care-plan family
        care_plan.py                  # MOVED from models/care_plan.py
        envelope.py                   # MOVED from models/envelope.py
        versions/
            __init__.py               # NEW — empty or re-exports CarePlanV1_2
            v1_2.py                   # MOVED from models/care_plan_versions/v1_2.py
    external_api/
        __init__.py                   # NEW — re-exports Athena models + AthenaAPIError
        athena_models.py              # MOVED from models/athena.py (12 models)
        athena_errors.py              # EXTRACTED from utils/athena_client.py (AthenaAPIError)

# DELETED:
#   models/athena_manifest.py
#   models/care_plan_versions/          (entire directory)
```

---

### B. File-by-File Move Table

| Old path | New path | Action |
|---|---|---|
| `models/care_plan.py` | `models/care_plan/care_plan.py` | Move; fix stale comment |
| `models/envelope.py` | `models/care_plan/envelope.py` | Move; update internal imports |
| `models/care_plan_versions/v1_2.py` | `models/care_plan/versions/v1_2.py` | Move; update imports |
| `models/athena.py` | `models/external_api/athena_models.py` | Move; rename file |
| `models/athena_manifest.py` | _(deleted)_ | Delete |
| `utils/athena_client.py` lines 24–30 (`AthenaAPIError`) | `models/external_api/athena_errors.py` | Extract class; update `utils/athena_client.py` to import from new location |
| `routes/care_plan.py` lines 75–88 (`ResolvedInput`) | `models/input.py` (append) | Move + convert from `@dataclass` to `JsonModel` |
| `tests/models/test_athena_manifest.py` | _(deleted)_ | Delete with `athena_manifest.py` |

---

### C. Per-File Implementation Notes

#### `models/care_plan/care_plan.py`

Move the file. Fix line 8 stale comment from:

```python
"""Version-agnostic care-plan family base. Concrete versions live in care_plan/v*/models.py."""
```

to:

```python
"""Version-agnostic care-plan family base. Concrete versions live in models/care_plan/versions/."""
```

Update the relative import:

```python
# Old
from .base import VersionedModel
# New (relative from inside models/care_plan/)
from ..base import VersionedModel
```

---

#### `models/care_plan/envelope.py`

Move the file. Update all relative imports (currently relative to `models/`):

```python
# Old
from .base import JsonModel
from .care_plan import CarePlan
from .grading import Grading
from .input import Input
from .metrics import Metrics

# New (relative from inside models/care_plan/)
from ..base import JsonModel
from .care_plan import CarePlan
from ..grading import Grading
from ..input import Input
from ..metrics import Metrics
```

---

#### `models/care_plan/versions/v1_2.py`

Move the file. Update imports (currently uses absolute `models.*` paths):

```python
# Old
from models.base import JsonModel
from models.care_plan import CarePlan

# New (relative from inside models/care_plan/versions/)
from ...base import JsonModel
from ..care_plan import CarePlan
```

The `utils.constants` import is absolute and stays unchanged.

---

#### `models/care_plan/__init__.py` (NEW)

Re-export the family so `from models.care_plan import X` works:

```python
"""Care-plan domain model re-exports."""

from .care_plan import CarePlan
from .envelope import CarePlanInternal
from .versions.v1_2 import CarePlanV1_2

__all__ = ["CarePlan", "CarePlanInternal", "CarePlanV1_2"]
```

---

#### `models/care_plan/versions/__init__.py` (NEW)

Empty file is sufficient. Optionally re-export:

```python
from .v1_2 import CarePlanV1_2

__all__ = ["CarePlanV1_2"]
```

---

#### `models/external_api/athena_models.py`

Move the content of `models/athena.py` verbatim. File-level docstring and all 12 classes are unchanged. The only change is the filename — this is a rename, not a content edit. The `extra="allow"` on each model stays as-is pending Q1 resolution.

Classes moved (all 12):
- `AthenaTokenRequest`
- `AthenaTokenResponse`
- `AthenaEncounterSummaryRequest`
- `AthenaEncounterSummaryResponse`
- `AthenaClinicalDocumentMeta`
- `AthenaClinicalDocumentListRequest`
- `AthenaClinicalDocumentListResponse`
- `AthenaClinicalDocumentContentRequest`
- `AthenaClinicalDocumentContentResponse`
- `AthenaPushDocumentRequest`
- `AthenaPushDocumentResponse`

---

#### `models/external_api/athena_errors.py` (NEW)

Extract `AthenaAPIError` from `utils/athena_client.py` lines 24–30:

```python
"""Athena Health API error types."""


class AthenaAPIError(Exception):
    """Raised when an Athena API call returns a non-200 status."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Athena API error {status_code}: {body[:200]}")
```

Note: SP01 will introduce `JunoError` as the project-wide base exception. When SP01 lands, `AthenaAPIError` should be updated to inherit from `JunoError` instead of `Exception`. For now, keep it as `Exception` to avoid a cross-SP dependency.

---

#### `models/external_api/__init__.py` (NEW)

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

---

#### `models/input.py` — Add `ResolvedInput`

Append `ResolvedInput` at the bottom of `models/input.py`, converting it from a `@dataclass` to a `JsonModel`.

Current `@dataclass` in `routes/care_plan.py` lines 75–88:

```python
@dataclass
class ResolvedInput:
    text: str
    source_description: str
    source_filename: str
    combined_pdf_bytes: bytes | None = None
    source_kind: str = "upload"
    file_count: int = 0
    file_types: list = None

    def __post_init__(self):
        if self.file_types is None:
            self.file_types = []
```

New `JsonModel` to append to `models/input.py`:

```python
class ResolvedInput(JsonModel):
    """Structured representation of a resolved pipeline input.

    Built in route helpers before the pipeline is invoked; carries the extracted
    text, metadata about the source, and (for file inputs) the merged PDF bytes.
    """

    text: str
    source_description: str
    source_filename: str
    combined_pdf_bytes: bytes | None = None
    source_kind: str = "upload"
    file_count: int = 0
    file_types: list[str] = Field(default_factory=list)
```

**Breaking change note:** `combined_pdf_bytes: bytes` is not JSON-serializable. `JsonModel` has `extra="forbid"` but does not mandate that all fields are JSON-native — only `to_dict()` / `model_dump(mode="json")` will fail if bytes are included. Since `ResolvedInput` is never serialized to Firestore or returned over the wire (it is an in-process handoff object), this is safe. If `to_dict()` is ever called on it, bytes will raise — document this clearly in the class docstring.

**Why `JsonModel` instead of staying a `@dataclass`?** Consistency — every model in `models/` inherits from `JsonModel`; `ResolvedInput` belongs in `models/`; it should follow the same pattern. It also gains Pydantic validation (e.g., `file_types` will always be a list, removing the `__post_init__` workaround).

---

#### `models/__init__.py` — Update Re-exports

Update to re-export from new internal paths while keeping the public surface identical. Add `ResolvedInput` to the public surface (new export):

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

All existing `from models import X` call sites continue to work without change.

---

#### `utils/athena_client.py` — Update Import

After extracting `AthenaAPIError`, update `utils/athena_client.py`:

1. Remove lines 24–30 (the `AthenaAPIError` class definition).
2. Add import at top:

```python
from models.external_api.athena_errors import AthenaAPIError
```

The class is referenced at lines 64, 82, and 90 of `utils/athena_client.py` — those call sites are unchanged.

---

#### `routes/care_plan.py` — Remove `ResolvedInput`

1. Remove the `@dataclass` import: `from dataclasses import dataclass` (line 13).
2. Remove the `ResolvedInput` class definition (lines 75–88).
3. Add import:

```python
from models.input import ResolvedInput
```

All internal usages of `ResolvedInput` within `routes/care_plan.py` (lines 153–208) are unchanged — same attribute names, same field defaults.

---

### D. Import Blast Radius

#### Production code that imports from `models/` — full table

| File | What it imports | Change needed? |
|---|---|---|
| `routes/worker.py` | `from models.envelope import CarePlanInternal` (line 17) | Yes — update to `from models.care_plan.envelope import CarePlanInternal` OR rely on `from models import CarePlanInternal` (zero-change) |
| `routes/worker.py` | `from models.input import TextInput, DocIdInput` (line 18) | No change — `models/input.py` stays in place |
| `routes/worker.py` | `from models.metrics import Metrics` (line 19) | No change — `models/metrics.py` stays in place |
| `routes/care_plan.py` | `from models.metrics import Metrics` (line 28) | No change |
| `routes/care_plan.py` | `from models.grading import Grading, build_grading, GRADING_VERSION` (line 29) | No change |
| `routes/care_plan.py` | `from models.care_plan import CarePlan` (line 30) | Yes — update to `from models.care_plan.care_plan import CarePlan` OR use top-level `from models import CarePlan` |
| `routes/care_plan.py` | `from models.envelope import CarePlanInternal` (line 31) | Yes — update or use top-level re-export |
| `routes/care_plan.py` | `from models.input import INPUT_VERSION` (line 32) | No change |
| `routes/grading.py` | `from models.grading import build_grading` (line 11) | No change |
| `care_plan/v1_2/pipeline.py` | `from models.care_plan import CarePlan` (line 27) | Yes — update to `from models.care_plan.care_plan import CarePlan` OR use top-level |
| `care_plan/v1_2/pipeline.py` | `from models.care_plan_versions.v1_2 import CarePlanV1_2` (line 29) | Yes — update to `from models.care_plan.versions.v1_2 import CarePlanV1_2` |
| `models/care_plan_versions/v1_2.py` (internal) | `from models.base import JsonModel` | Resolved by relative imports in the moved file |
| `models/care_plan_versions/v1_2.py` (internal) | `from models.care_plan import CarePlan` | Resolved by relative imports in the moved file |
| `routes/worker.py` | `from utils.athena_client import athena_client, AthenaAPIError` (line 220) | Yes — update to `from models.external_api.athena_errors import AthenaAPIError` and keep `athena_client` from `utils.athena_client` |

**Recommended approach:** Update all direct path imports to their new canonical paths. The top-level `models/__init__.py` re-exports are a stability net for external callers, not a license to use stale internal paths within `models/` itself.

---

#### Routes that consume `ResolvedInput`

`ResolvedInput` is currently defined and used only within `routes/care_plan.py`. It is not imported anywhere else. After the move, add the following import to `routes/care_plan.py`:

```python
from models.input import ResolvedInput
```

`routes/care_plan_jobs.py` does not reference `ResolvedInput` directly — it calls `_resolve_uploaded_files()` which returns a `ResolvedInput`, but the caller only uses the returned object's attributes, so no import change is needed there.

---

#### Tests that reference moved models

| Test file | Change |
|---|---|
| `tests/models/test_athena_manifest.py` | DELETE entire file — tests only dead code |
| `tests/models/test_care_plan.py` | Update imports: `from models.care_plan.care_plan import CarePlan` (or via top-level) |
| `tests/models/test_envelope.py` | Update imports: `from models.care_plan.envelope import CarePlanInternal` (or via top-level) |
| `tests/care_plan/test_pipeline_schema.py` | Update imports if they reference `models.care_plan_versions.v1_2` — change to `models.care_plan.versions.v1_2` |
| `tests/models/test_base.py` | No change — `models/base.py` is unmoved |
| `tests/models/test_errors.py` | No change |
| `tests/models/test_grading_model.py` | No change |
| `tests/models/test_input_metrics.py` | No change — `models/input.py` is unmoved |
| `tests/models/test_readpath_tolerance.py` | Check for `care_plan_versions` references; update to `care_plan.versions` if present |
| `tests/utils/test_athena_client.py` | Update: `from utils.athena_client import AthenaAPIError` → `from models.external_api.athena_errors import AthenaAPIError` (or keep via `utils.athena_client` if the re-export is preserved there) |

---

### E. Naming Collision Guidance

`backend/care_plan/` is a top-level Python package containing pipeline logic:
- `care_plan/interface.py` — `CarePlanPipeline` ABC
- `care_plan/v1_2/pipeline.py` — `CarePlanV1_2Pipeline`

`backend/models/care_plan/` (new) is a subfolder within the models package containing domain models:
- `models/care_plan/care_plan.py` — `CarePlan` base model
- `models/care_plan/envelope.py` — `CarePlanInternal`
- `models/care_plan/versions/v1_2.py` — `CarePlanV1_2` typed model

**Python will not confuse these** because they resolve to different import roots:
- Pipeline: `from care_plan.interface import CarePlanPipeline`
- Models: `from models.care_plan.care_plan import CarePlan`

**Developer guidance to add to the module docstrings:**

In `models/care_plan/__init__.py`:
```
# NOTE: backend/care_plan/ is the pipeline-logic package (CarePlanPipeline, CarePlanV1_2Pipeline).
# This package (models/care_plan/) contains only the Pydantic domain models for the care-plan family.
# Import from `care_plan.*` for pipeline code; import from `models.care_plan.*` for model types.
```

See Q2 in §9 for the open question of whether this naming is acceptable long-term.

---

## 5. API Change Summary

No API surface changes. All HTTP response shapes are unchanged. All Firestore document shapes are unchanged. The reorganization is purely internal to the Python package structure.

---

## 6. Frontend Change Summary

N/A. This sub-project makes no frontend changes.

---

## 7. Testing

### Verification after each move

After moving each file, run:

```bash
cd /root/projects/juno/backend
python -c "from models import CarePlan, CarePlanInternal, CarePlanV1_2, Input, Metrics, Grading, ResolvedInput"
```

This confirms that all top-level re-exports still work.

### Full test suite (relevant subset)

Run only the tests directly affected by the moves:

```bash
cd /root/projects/juno/backend
pytest tests/models/ tests/care_plan/ tests/utils/test_athena_client.py -v
```

Do not run the full test suite (project rule: only run tests directly needed by the task).

### Manual smoke test

```bash
cd /root/projects/juno/backend
python -c "
from models.care_plan.care_plan import CarePlan
from models.care_plan.envelope import CarePlanInternal
from models.care_plan.versions.v1_2 import CarePlanV1_2
from models.external_api.athena_models import AthenaTokenRequest
from models.external_api.athena_errors import AthenaAPIError
from models.input import ResolvedInput
print('All imports OK')
print('CarePlan registry:', CarePlan._registry)
"
```

The `CarePlan._registry` should contain `{'1.2': <class 'CarePlanV1_2'>}` — this confirms the self-registration side effect still fires correctly after the move.

### Test file deletions

Delete `tests/models/test_athena_manifest.py` — it tests only `models/athena_manifest.py` which is being deleted. The test currently passes only because it reads from `preset-data/manifest.json` and the `AthenaEncounterManifest` / `AthenaClinicalDocManifest` models; none of that code is production-wired.

---

## 8. Manual Intervention

No manual intervention is required beyond standard code review. All changes are pure Python refactoring with no data migrations, no environment variable changes, and no deployment steps.

**Recommended commit sequence** (to make each step independently reviewable):

1. `chore: delete models/athena_manifest.py and test_athena_manifest.py` — removes dead code first, making subsequent diffs cleaner.
2. `refactor: extract AthenaAPIError to models/external_api/athena_errors.py` — creates the new file, updates `utils/athena_client.py`.
3. `refactor: move Athena models to models/external_api/athena_models.py` — moves `models/athena.py`.
4. `refactor: reorganize care-plan models into models/care_plan/` — moves `care_plan.py`, `envelope.py`, `care_plan_versions/v1_2.py`; creates `models/care_plan/__init__.py` and `models/care_plan/versions/__init__.py`.
5. `refactor: move ResolvedInput into models/input.py as JsonModel` — removes `@dataclass` from routes, adds `JsonModel` to input.py, updates `routes/care_plan.py` import.
6. `chore: update models/__init__.py and all internal imports` — final cleanup pass to update all call sites to canonical new paths.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Athena models use `extra="allow"` (every model in `models/external_api/athena_models.py`). The house standard is `extra="forbid"`. Switching to `forbid` would raise `ValidationError` if Athena ever returns an undocumented field. Recommended: change to `forbid` as part of SP04 wiring (when the models are actually exercised), not SP03. | [OPEN] — defer to SP04 to decide; leave `extra="allow"` untouched in SP03. |
| Q2 | The `backend/care_plan/` pipeline package and `backend/models/care_plan/` models subfolder share the `care_plan` name segment. Python does not confuse them (different import roots). Is the naming acceptable, or should the models subfolder be renamed to `models/care_plan_models/` or `models/plans/` to eliminate any visual ambiguity? | [OPEN] — current recommendation is to keep `models/care_plan/` with clear docstring guidance (see §4.E). Raise with the team if onboarding confusion is observed after the PR merges. |
| Q3 | `ResolvedInput.combined_pdf_bytes` is `bytes`, which is not JSON-native. Converting `ResolvedInput` to `JsonModel` retains `extra="forbid"` but does not prevent instantiation with bytes — only `to_dict()` / serialization would fail. Should `combined_pdf_bytes` be excluded from the model (e.g. carried out-of-band)? | [OPEN] — `ResolvedInput` is never serialized; the bytes field is fine as-is. Add a docstring warning. Re-evaluate if `ResolvedInput` is ever written to Firestore. |
| Q4 | `models/base.py` stays at `models/base.py` — not moved. | [RESOLVED] |
| Q5 | `models/athena_manifest.py` deleted; no `models/manifest/` folder created. | [RESOLVED] |
| Q6 | Athena HTTP client moves to `services/external_api/` in SP04; its data models and `AthenaAPIError` go to `models/external_api/`. | [RESOLVED — this SP creates `models/external_api/`; SP04 creates `services/external_api/`] |
| Q7 | Pipeline owns care-plan orchestration (SP07). | [RESOLVED — no pipeline changes in SP03] |
| Q8 | Coordination with SP01: `AthenaAPIError` should eventually inherit from `JunoError`. SP03 keeps it as plain `Exception`; SP01 or SP04 updates the base class. | [DEFERRED to SP04 or post-SP01 cleanup] |
| Q9 | Coordination with SP04: SP04 wires the Athena models from `models/external_api/athena_models.py` into the HTTP client. SP03 must land before SP04. | [RESOLVED — explicit ordering constraint; communicate to SP04 implementer] |
| Q10 | Coordination with SP05: SP05 adds `models/job.py` at the top level of `models/`. SP03 does not touch this path. | [RESOLVED — no conflict] |
