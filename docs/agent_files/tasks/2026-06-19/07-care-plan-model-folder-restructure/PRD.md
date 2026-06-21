# PRD: Care Plan Model & Folder Restructure (SP-07)

Sub-project 7 of the Juno backend refactor. **No other SP depends on this one**; it is a
purely structural cleanup that removes dead model code, reorganises folders, and finishes
the grading model's upgrade to the per-version framework. It can land independently at any
point after SP-01 (Pydantic migration) is in.

## 1. Problem

After SP-01 (Pydantic migration), several structural loose ends remain that prevent the
codebase from matching the stated architecture:

1. **`CarePlanV1_2StructuredLLM` still exists** (`models/care_plan.py:144-161`). SP-01
   intentionally left it in place because the pipeline uses it. But the locked decision is
   to remove it and generate the LLM schema directly from `CarePlanV1_2` by filtering out
   `terms` and `raw`. The class duplicates every structured field with no additional value.

2. **All v1.2-specific model types live in `models/care_plan.py`** alongside the
   version-agnostic `CarePlan` base. The locked decision is that `models/care_plan.py`
   should contain ONLY `CarePlan(VersionedModel)` (and `CARE_PLAN_VERSION`). All concrete
   v1.2 types (`CarePlanV1_2`, `ReasonForVisit`, `DiagnosisDetail`, `Diagnosis`,
   `Medication`, `Test`, `Procedure`, `OtherInstruction`, `FollowUp`, `WarningSign`,
   `GlossaryTerm`, `RawArtifacts`) belong in the pipeline folder they serve, not in the
   shared model base.

3. **The pipeline folder is named `simplify/`** (`backend/simplify/`). The locked decision
   renames it to `care_plan/` at the backend folder level. The class `V1_2Pipeline` is also
   renamed to `CarePlanV1_2Pipeline` inside that file.

4. **`before_score` and `after_score` remain on `CarePlanInternal`** (`envelope.py:21-22`).
   SP-01 explicitly noted these as internal-only fields that will be removed from the
   envelope once the route removes them from the sentinel tuple. The locked decision removes
   them now: they are consumed only by `build_grading()` and do not need envelope-level
   transport after that call is made.

5. **`is_legacy_shape` remains in `envelope.py`** (`envelope.py:38-43`). The locked
   decision deletes it: it is confirmed not imported or called anywhere outside its own
   module, and the condition it checks (`"care_plan" not in data`) is trivially inlineable
   on the one theoretical future call site if ever needed.

6. **`_METHOD_REASONING` is a plain dict** (`grading.py:27-34`). The locked decision
   converts it to a `GradingMethodReason` Enum so the set of valid grading method names is
   typed and the string keys are not stringly typed.

7. **`Grading` is a plain `JsonModel`**, not a `VersionedModel`. The locked decision
   upgrades it to a `VersionedModel` subclass with a `grading_version_value` class variable
   tied to `GRADING_VERSION`. This mirrors the `CarePlan` pattern.

The current test suite is written against the old structure — tests import from
`simplify.v1_2.*` and reference `V1_2Pipeline`, `CarePlanV1_2StructuredLLM`, and
`is_legacy_shape`. Those tests must be updated in lockstep with the code changes.

## 2. Goals

1. Remove `CarePlanV1_2StructuredLLM` from `models/care_plan.py` and from
   `models/__init__.py`. Replace its use in the pipeline with an `exclude_fields()` helper
   that generates the LLM schema from `CarePlanV1_2` by filtering the schema dict.
2. Move all v1.2-specific types out of `models/care_plan.py` into
   `care_plan/v1_2/models.py`. Keep `models/care_plan.py` as the thin base-only file it
   was designed to be.
3. Rename `backend/simplify/` → `backend/care_plan/` (folder rename). Update
   `__init__.py`, `interface.py`, `v1_2/__init__.py`, `v1_2/pipeline.py` in place.
4. Rename `V1_2Pipeline` → `CarePlanV1_2Pipeline` in `care_plan/v1_2/pipeline.py`. Update
   all importing call sites.
5. Remove `before_score` and `after_score` from `CarePlanInternal`. Update the yield
   sentinel tuple in `routes/care_plan.py` and the unpacking in both
   `routes/care_plan.py` and `routes/batch.py`.
6. Delete `is_legacy_shape` from `envelope.py` and from `models/__init__.py`. Update the
   one test that asserts on it.
7. Convert `_METHOD_REASONING` to `GradingMethodReason(str, Enum)` in `grading.py`.
8. Promote `Grading` to `VersionedModel` with `grading_version_value = GRADING_VERSION`.
9. Update all imports across routes, tests, and `models/__init__.py` to reflect the above.

## 3. Non-Goals

- **Not** changing any LLM prompts (SP-09 owns prompt extraction).
- **Not** changing the SSE protocol, scoring math, or grading entry count/shape.
- **Not** moving `models/grading.py` — it stays at `backend/models/grading.py`.
- **Not** moving `models/envelope.py` — it stays at `backend/models/envelope.py`.
- **Not** adding a new pipeline version or changing the v1-2 pipeline logic.
- **Not** touching the frontend (no frontend changes at all).
- **Not** migrating Firestore data (locked: no migration concern).
- **Not** changing the `build_grading()` signature or the 14-entry output structure.

## 4. Architecture Decisions

### 4.1 `models/care_plan.py` — thin base only

After this SP, `models/care_plan.py` contains exactly two things:

```python
# backend/models/care_plan.py
from __future__ import annotations
from .base import VersionedModel

CARE_PLAN_VERSION = "1.2"

class CarePlan(VersionedModel):
    """Version-agnostic care-plan family base. Concrete versions live in care_plan/v*/models.py."""
    doc_type: str
    version: str

    @classmethod
    def from_pipeline_result(cls, version: str, data: dict) -> "CarePlan":
        """Validate pipeline output against the concrete care-plan version."""
        return cls.from_dict({**data, "version": version})
```

`CARE_PLAN_VERSION` stays here because it is the module-level constant imported by SP-04
(`from models.care_plan import CARE_PLAN_VERSION`) and used as `CarePlanV1_2.version_value`.
The type aliases `Source` and `Importance` move to `care_plan/v1_2/models.py` where they
are actually used.

The concrete `CarePlanV1_2` and all its sub-models are **no longer in this file**. They are
imported and registered via the new `care_plan/v1_2/models.py` (self-registration happens
at import time through `__init_subclass__`). The `care_plan/v1_2/__init__.py` must import
from `care_plan/v1_2/models.py` so that `CarePlanV1_2` is registered before any pipeline
or route code calls `CarePlan.from_dict`. This is the same pattern used by any future
version: add `care_plan/v2/models.py` and import it in `care_plan/v2/__init__.py`.

**Registration guarantee:** `routes/care_plan.py` imports `care_plan.v1_2.pipeline`, which
imports `CarePlanV1_2` from `care_plan.v1_2.models`, which triggers `__init_subclass__`
and registers `"1.2"` in `CarePlan._registry`. No explicit registration call is required.

### 4.2 `care_plan/v1_2/models.py` — new file for v1.2 types

All concrete v1.2 types move here verbatim. The file structure:

```python
# backend/care_plan/v1_2/models.py
from __future__ import annotations
from typing import ClassVar, Literal
from pydantic import Field
from models.base import JsonModel
from models.care_plan import CarePlan, CARE_PLAN_VERSION

Source = Literal["documents", "recording", "notes"]
Importance = Literal["high", "low"]

class ReasonForVisit(JsonModel): ...
class DiagnosisDetail(JsonModel): ...
class Diagnosis(JsonModel): ...
class Medication(JsonModel): ...
class Test(JsonModel): ...
class Procedure(JsonModel): ...
class OtherInstruction(JsonModel): ...
class FollowUp(JsonModel): ...
class WarningSign(JsonModel): ...
class GlossaryTerm(JsonModel): ...
class RawArtifacts(JsonModel): ...

class CarePlanV1_2(CarePlan):
    version_value: ClassVar[str] = CARE_PLAN_VERSION
    doc_type: Literal["care_plan"] = "care_plan"
    version: Literal["1.2"] = CARE_PLAN_VERSION
    # ... all fields identical to current models/care_plan.py:CarePlanV1_2
```

All field definitions, defaults, and types are unchanged from the current
`models/care_plan.py`. This is a file move, not a schema change. The import path changes
from `from models.care_plan import CarePlanV1_2` to
`from care_plan.v1_2.models import CarePlanV1_2` at all call sites in the pipeline file.
The route (`routes/care_plan.py`) already uses `from models.care_plan import CarePlan`
which stays unchanged since `CarePlan` remains in `models/care_plan.py`.

### 4.3 Removing `CarePlanV1_2StructuredLLM` — the `exclude_fields` helper

The class is used in exactly one place: `care_plan/v1_2/pipeline.py` at module level for
`_STRUCTURING_SCHEMA`, and inside `structure_appointment_note` for validation.

**Replacement — module-level schema generation:**

```python
# care_plan/v1_2/pipeline.py  (replaces the StructuredLLM import + module-level constant)
import copy

def _llm_schema(model_cls, exclude: set[str]) -> dict:
    """Generate a JSON schema from model_cls with the given field names excluded."""
    schema = copy.deepcopy(model_cls.model_json_schema())
    props = schema.get("properties", {})
    for field in exclude:
        props.pop(field, None)
    # Also remove from required list if present
    schema.get("required", [])  # required is rare with defaults; pop anyway
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in exclude]
    return schema

_STRUCTURING_SCHEMA = json.dumps(
    _llm_schema(CarePlanV1_2, exclude={"terms", "raw"}),
    indent=2,
)
```

**Replacement — validation in `structure_appointment_note`:**

```python
# was: model = CarePlanV1_2StructuredLLM.model_validate(raw)
# now: validate against CarePlanV1_2 but allow terms/raw to be absent (they have defaults)
try:
    model = CarePlanV1_2.model_validate(raw)
except ValidationError as e:
    raise ValueError(f"LLM structure output failed validation: {e}") from e
return model.model_dump(mode="json", exclude={"terms", "raw"})
```

**Why this is correct:** The LLM only produces the structured fields; `terms` and `raw`
are `None` / `{}` by default in `CarePlanV1_2`, so `model_validate` with only structured
fields succeeds. Calling `model_dump(exclude={"terms", "raw"})` ensures the returned dict
has exactly the structured fields — matching the old `CarePlanV1_2StructuredLLM.model_dump`
output shape. The `extra="forbid"` guard on the LLM output is preserved because
`CarePlanV1_2` still rejects unknown fields.

**Schema correctness:** `_llm_schema` produces a schema without `terms` and `raw` in
`properties`. This is equivalent to the old `CarePlanV1_2StructuredLLM.model_json_schema()`
output. A unit test asserts this equivalence (see §7).

### 4.4 Folder rename: `backend/simplify/` → `backend/care_plan/`

This is a filesystem rename plus import-path update across four files and all test files
that reference the old path.

Old → new file paths:

| Old path | New path |
|---|---|
| `backend/simplify/__init__.py` | `backend/care_plan/__init__.py` |
| `backend/simplify/interface.py` | `backend/care_plan/interface.py` |
| `backend/simplify/v1_2/__init__.py` | `backend/care_plan/v1_2/__init__.py` |
| `backend/simplify/v1_2/pipeline.py` | `backend/care_plan/v1_2/pipeline.py` |

The `backend/simplify/` directory is deleted after the new `backend/care_plan/` is
populated. No other files move. `backend/models/` is unaffected.

**Import changes in `care_plan/v1_2/pipeline.py`:**

```python
# Old (to be removed):
from simplify.interface import CarePlanPipeline
# New:
from care_plan.interface import CarePlanPipeline

# Old (to be removed):
from models.care_plan import CARE_PLAN_VERSION, CarePlan, CarePlanV1_2, CarePlanV1_2StructuredLLM
# New:
from models.care_plan import CARE_PLAN_VERSION, CarePlan
from care_plan.v1_2.models import CarePlanV1_2
```

**Import changes in `care_plan/interface.py`:** No imports to change; the docstring
comment referencing `simplify/v<X>/` updates to `care_plan/v<X>/`.

**Import change in `routes/care_plan.py`:**

```python
# Old:
from simplify.v1_2.pipeline import V1_2Pipeline
# New:
from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
```

And the usage at `routes/care_plan.py:348` updates:
```python
# Old:
pipeline = V1_2Pipeline()
# New:
pipeline = CarePlanV1_2Pipeline()
```

### 4.5 Rename `V1_2Pipeline` → `CarePlanV1_2Pipeline`

Inside `care_plan/v1_2/pipeline.py`, the class declaration changes:

```python
# Old:
class V1_2Pipeline(CarePlanPipeline):
# New:
class CarePlanV1_2Pipeline(CarePlanPipeline):
```

No logic changes. All internal method references use `self.*` so no other lines in the
file change. The old name appears in:

- `routes/care_plan.py:32` (import) → updated per §4.4
- `routes/care_plan.py:348` (instantiation) → updated per §4.4
- `tests/models/test_pipeline_executors.py:40` (`@patch("routes.care_plan.V1_2Pipeline",
  ...)`) → update to `@patch("routes.care_plan.CarePlanV1_2Pipeline", ...)`
- `tests/simplify/test_pipeline_interface.py:19` (source-text assertion) → see §4.10
- `tests/simplify/test_pipeline_schema.py:9` (import) → see §4.10

### 4.6 Remove `before_score` and `after_score` from `CarePlanInternal`

**Current envelope.py:**
```python
class CarePlanInternal(JsonModel):
    metrics: Metrics
    input: Input
    grading: Grading
    care_plan: CarePlan
    before_score: dict | None = None   # REMOVE
    after_score: dict | None = None    # REMOVE
```

**New envelope.py:**
```python
class CarePlanInternal(JsonModel):
    metrics: Metrics
    input: Input
    grading: Grading
    care_plan: CarePlan
    # before_score and after_score are removed; scores are consumed by build_grading()
    # before CarePlanInternal is constructed and do not need envelope-level transport.
```

**Impact on the sentinel tuple** (`routes/care_plan.py:472`):

`before_score` and `after_score` are only present in the sentinel so the route can pass
them to `CarePlanInternal`. Once removed from the envelope, they are consumed immediately
in `run_care_plan_pipeline` (where they are computed) and never need to leave that
generator. The sentinel tuple shrinks:

```python
# Old (care_plan.py:472):
yield (RESULT_SENTINEL, care_plan, grading, text, clarified, before_score, after_score)

# New:
yield (RESULT_SENTINEL, care_plan, grading, text, clarified)
```

**Impact on unpacking** (`routes/care_plan.py:551`):

```python
# Old:
_, care_plan, grading, _raw_text, _clarified_text, before_score, after_score = pipeline_result
envelope = CarePlanInternal(
    metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
    before_score=before_score, after_score=after_score,
)

# New:
_, care_plan, grading, _raw_text, _clarified_text = pipeline_result
envelope = CarePlanInternal(
    metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
)
```

**Impact on `routes/batch.py:201-210`:**

```python
# Old:
_, care_plan, grading, _raw_text, _clarified_text, before_score, after_score = chunk
envelope = CarePlanInternal(
    metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
    before_score=before_score, after_score=after_score,
)

# New:
_, care_plan, grading, _raw_text, _clarified_text = chunk
envelope = CarePlanInternal(
    metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
)
```

**Wire format change:** `to_dict()` will no longer emit `"before_score"` and
`"after_score"` keys at the top level of the response envelope. These keys were already
`None` in the happy path when grading is disabled. With grading enabled they conveyed the
raw score dicts — but that information is already fully captured inside
`grading.entries[*].grade_breakdown` and `grading.entries[*].grade`. No caller (frontend
or batch consumer) reads `before_score`/`after_score` off the wire for anything other
than debugging. The test at `tests/routes/test_care_plan_route.py:295-296` asserts on
`before_score` and `after_score` in the final payload — that test must be updated to
assert those keys are absent.

### 4.7 Delete `is_legacy_shape` from `envelope.py`

`is_legacy_shape` is defined at `envelope.py:38-43` and exported from `models/__init__.py`.
It is not imported anywhere outside its own module except tests that test the function
itself. The function body is two lines and trivially inlineable if ever needed. Delete it.

```python
# Delete from envelope.py:
def is_legacy_shape(data: dict) -> bool:
    return "care_plan" not in data
```

```python
# Delete from models/__init__.py:
from .envelope import CarePlanInternal, is_legacy_shape   # remove is_legacy_shape
# __all__ removes "is_legacy_shape"
```

Tests affected:
- `tests/models/test_envelope.py:134-138` — the `test_is_legacy_shape_checks_for_care_plan_key`
  test. Delete this test.
- `tests/models/test_exports.py:20,30` — references to `is_legacy_shape` in the export
  list assertions. Remove those lines.

### 4.8 `_METHOD_REASONING` → `GradingMethodReason(str, Enum)`

**Current `grading.py:27-34`:** plain `dict` mapping method name strings to reasoning
strings.

**New:**

```python
# backend/models/grading.py
import enum

class GradingMethodReason(str, enum.Enum):
    smog           = "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials"
    flesch_kincaid = "Flesch-Kincaid Reading Ease + Grade Level (1975) — sentence length × syllable load"
    dale_chall     = "Dale-Chall (1948/1995) — difficult words outside the 3,000 familiar-word list"
    pemat          = "PEMAT (AHRQ 2013) — automated approximation of items 3,8,14,21-22 (understandability) and 27-33 (actionability)"
    sam            = "SAM (Doak et al. 1996) — automated approximation of content, literacy demand, and layout/typography domains"
    cdc_cci        = "CDC Clear Communication Index — automated approximation of main message, behavioral recommendations, numbers, and call-to-action items"
```

**Usage update in `build_grading`** (`grading.py:59`):

```python
# Old:
reasoning=_METHOD_REASONING[method_name],

# New:
reasoning=GradingMethodReason[method_name].value,
```

`str, Enum` means `GradingMethodReason.smog.value` is the string — same value as today,
same `reasoning` field on `GradingEntry`. No wire format change.

The iteration list in `build_grading` (`"smog", "flesch_kincaid", ...`) can optionally be
replaced with `list(GradingMethodReason.__members__)` to derive the set from the Enum,
removing the separate hard-coded list. This is cleaner but is an implementer's call.

`GradingMethodReason` is added to `models/__init__.py` exports and `__all__`.

### 4.9 `Grading` → `VersionedModel` subclass

**Current:** `Grading(JsonModel)` — a plain `JsonModel`.

**New:**

```python
# backend/models/grading.py

class Grading(VersionedModel):
    """Versioned grading result for a single pipeline run."""
    grading_version_value: ClassVar[str] = GRADING_VERSION
    version: str = GRADING_VERSION   # inherited required field, defaulted

    entries: list[GradingEntry] = Field(default_factory=list)
    enabled: bool = True
    graded_at: str | None = None
```

**Wire format change:** `Grading().to_dict()` will now emit `"version": "1.0"` in addition
to `entries`, `enabled`, and `graded_at`. This changes the persisted `grading` sub-object
in Firestore (a new `version` key) and the SSE result payload's `grading` field.

**Impact:** The test at `tests/models/test_grading_model.py:29-30` asserts:
```python
assert Grading().to_dict() == {"entries": [], "enabled": True, "graded_at": None}
```
This assertion must be updated to:
```python
assert Grading().to_dict() == {"version": "1.0", "entries": [], "enabled": True, "graded_at": None}
```

`Grading` as a `VersionedModel` also registers itself in `VersionedModel._registry` via
`__init_subclass__`. But `Grading` is a **direct subclass of `VersionedModel`** (not of a
family base that itself subclasses `VersionedModel`) — this means it gets a **fresh, empty
`_registry`** per the `__init_subclass__` logic in `base.py`. Since there is only one
Grading version now, there is no dispatch call site to worry about; `Grading.from_dict`
will call `model_validate` directly (the `version_value is not None` branch). If a future
`GradingV1_1` is added, the family-base pattern applies the same way as `CarePlan`.

**`build_grading` return:** No change. `Grading(entries=entries, enabled=True,
graded_at=...)` still works — `version` has a default so it does not need to be passed.

### 4.10 Test file updates

The following test files import from `simplify.*` or reference symbols that change, and
must be updated:

| File | Change required |
|---|---|
| `tests/simplify/test_pipeline_schema.py:8-9` | `from simplify.v1_2 import pipeline as pipeline_module` → `from care_plan.v1_2 import pipeline as pipeline_module`; `from simplify.v1_2.pipeline import V1_2Pipeline` → `from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline` |
| `tests/simplify/test_pipeline_schema.py:23` | `pipeline = V1_2Pipeline.__new__(V1_2Pipeline)` → `CarePlanV1_2Pipeline` |
| `tests/simplify/test_pipeline_schema.py:32` | same |
| `tests/simplify/test_pipeline_schema.py:44` | `monkeypatch.setattr(pipeline_module, ...)` — module ref correct once import above is fixed |
| `tests/simplify/test_pipeline_interface.py:19` | Assert `"class V1_2Pipeline(CarePlanPipeline):"` → `"class CarePlanV1_2Pipeline(CarePlanPipeline):"` |
| `tests/simplify/test_pipeline_interface.py:10,14` | `assert (BACKEND_DIR / "simplify" / "v1_2").is_dir()` → `(BACKEND_DIR / "care_plan" / "v1_2").is_dir()`; `BACKEND_DIR / "simplify" / "interface.py"` → `BACKEND_DIR / "care_plan" / "interface.py"`; `BACKEND_DIR / "simplify" / "v1_2" / "pipeline.py"` → `BACKEND_DIR / "care_plan" / "v1_2" / "pipeline.py"` |
| `tests/simplify/test_pipeline_interface.py:18` | `"from simplify.interface import CarePlanPipeline"` → `"from care_plan.interface import CarePlanPipeline"` |
| `tests/models/test_pipeline_executors.py:40` | `@patch("routes.care_plan.V1_2Pipeline", ...)` → `@patch("routes.care_plan.CarePlanV1_2Pipeline", ...)` |
| `tests/models/test_care_plan.py:13,98` | Remove import of `CarePlanV1_2StructuredLLM`; update `test_structured_llm_schema_properties_match_care_plan_structured_fields` to use `_llm_schema` helper (or inline the schema generation call); update imports of `CarePlanV1_2` to `from care_plan.v1_2.models import CarePlanV1_2` |
| `tests/models/test_exports.py:11,28` | Remove `CarePlanV1_2StructuredLLM` from import list and `__all__` assertion; remove `is_legacy_shape` from import list and `__all__` assertion; add `GradingMethodReason` |
| `tests/models/test_envelope.py:134-138` | Delete `test_is_legacy_shape_checks_for_care_plan_key` |
| `tests/models/test_envelope.py:47-71` | Update `before_score`/`after_score` assertions: those keys are no longer in `to_dict()` output; the set check at line 59-66 must remove them; lines 67-68 and 70-71 must be removed or rewritten |
| `tests/models/test_envelope.py:108-122` | Update `test_care_plan_internal_round_trips_composite_scores` — scores no longer exist on the envelope at all; consider converting to a test that confirms scores are absent |
| `tests/models/test_grading_model.py:29-30` | Update `Grading().to_dict()` expectation to include `"version": "1.0"` |
| `tests/routes/test_care_plan_route.py:295-296` | Remove assertions `final_payload["before_score"] == ...` and `final_payload["after_score"] == ...`; optionally assert `"before_score" not in final_payload` |
| `tests/fixtures/care_plan.py:44-45` | Remove `"before_score": None` and `"after_score": None` from the fixture dict |

Additionally, all test files that currently import `CarePlanV1_2` via
`from models.care_plan import CarePlanV1_2` must update that import to
`from care_plan.v1_2.models import CarePlanV1_2`. Audit:

```bash
grep -rn "from models.care_plan import.*CarePlanV1_2" backend/tests/
```

### 4.11 `models/__init__.py` — updated exports

```python
# backend/models/__init__.py
from .base import JsonModel, VersionedModel
from .care_plan import CarePlan                          # CarePlanV1_2 no longer here
from .envelope import CarePlanInternal                   # is_legacy_shape removed
from .grading import Grading, GradingEntry, GradingMethodReason, build_grading
from .input import Input, InputFile
from .metrics import Metrics

__all__ = [
    "JsonModel",
    "VersionedModel",
    "CarePlan",
    # CarePlanV1_2 and CarePlanV1_2StructuredLLM removed from top-level export
    "CarePlanInternal",
    # is_legacy_shape removed
    "Grading",
    "GradingEntry",
    "GradingMethodReason",
    "build_grading",
    "Input",
    "InputFile",
    "Metrics",
]
```

`CarePlanV1_2` is no longer exported from the `models` package root. Callers that need it
import directly from `care_plan.v1_2.models`. This is intentional: version-specific types
belong to the pipeline layer, not the generic model layer.

### 4.12 `care_plan/v1_2/__init__.py` — ensure registration at import time

```python
# backend/care_plan/v1_2/__init__.py
# Import models to trigger CarePlanV1_2 self-registration in CarePlan._registry.
from care_plan.v1_2.models import CarePlanV1_2  # noqa: F401
```

This single import guarantees that `CarePlan.from_dict({"version": "1.2", ...})` works
regardless of import order, as long as `care_plan.v1_2` (the package) has been imported
— which it always is because the pipeline module is in `care_plan.v1_2.pipeline`.

## 5. API Change Summary

Two wire-format changes (backend response payloads):

**1. `before_score` / `after_score` removed from the top-level SSE result envelope:**

```jsonc
// BEFORE
{
  "care_plan": { ... },
  "metrics": { ... },
  "input": { ... },
  "grading": { ... },
  "before_score": { "composite": 42, ... },   // REMOVED
  "after_score":  { "composite": 91, ... }    // REMOVED
}

// AFTER
{
  "care_plan": { ... },
  "metrics": { ... },
  "input": { ... },
  "grading": { ... }
}
```

Scoring information is still fully present inside `grading.entries[*].grade` and
`grading.entries[*].grade_breakdown`. No consumer reads `before_score`/`after_score`
from the wire for display purposes.

**2. `grading.version` added:**

```jsonc
// BEFORE
{ "entries": [...], "enabled": true, "graded_at": "..." }

// AFTER
{ "version": "1.0", "entries": [...], "enabled": true, "graded_at": "..." }
```

This is a new key in the persisted Firestore `grading` sub-object and the SSE payload.
The frontend ignores unknown keys so this is non-breaking on that side. Firestore reads
are tolerant (locked decision); old docs without `version` validate because
`VersionedModel.from_dict` dispatches on `version` only when called on a family base with
no `version_value` — calling `Grading.from_dict(old_dict)` with missing `version` will
fail. See Open Questions §9.1.

**No other route changes.** The `POST /care_plan` and `POST /care_plan/batch` endpoint
paths, SSE step sequence, and all other fields are unchanged.

## 6. Frontend Change Summary

N/A. This SP makes no frontend changes. The removal of `before_score`/`after_score` from
the envelope (§4.6) is the only wire-level change, and the frontend does not read those
keys (the frontend reads `care_plan`, `grading`, `metrics`, `input`). The `grading.version`
addition (§4.9) is additive and ignored by the frontend.

## 7. Testing

All tests pass after the import and assertion updates in §4.10. No new test files are
created; existing tests are updated in place.

**New or changed test assertions to add:**

- **`_llm_schema` helper test** (add to `tests/simplify/test_pipeline_schema.py` or new
  `tests/care_plan/test_v1_2_pipeline.py`):
  - `_llm_schema(CarePlanV1_2, {"terms", "raw"})["properties"]` has no `terms` or `raw`
    key.
  - The schema properties set equals `set(CarePlanV1_2.model_fields) - {"terms", "raw"}`.
  - A `CarePlanV1_2` instance validated from the LLM fields only (no `terms`/`raw`) passes
    `model_validate`.
  - `model_dump(exclude={"terms", "raw"})` on that instance does not contain `terms` or
    `raw` keys.

- **`GradingMethodReason` enum test** (add to `tests/models/test_grading_model.py`):
  - `GradingMethodReason["smog"].value` equals the expected reasoning string.
  - `build_grading(...)` entries have `reasoning` equal to the corresponding
    `GradingMethodReason` member's value.

- **`Grading` as `VersionedModel` test** (update `tests/models/test_grading_model.py`):
  - `Grading().to_dict()` includes `"version": "1.0"`.
  - `Grading.from_dict({"version": "1.0", "entries": [], "enabled": True, "graded_at": None})`
    round-trips correctly.

- **Folder-rename structural tests** (update `tests/simplify/test_pipeline_interface.py`):
  - `backend/care_plan/v1_2/` exists.
  - `backend/simplify/` does NOT exist.
  - `care_plan/interface.py` source contains `"from care_plan.interface import CarePlanPipeline"`.
  - `care_plan/v1_2/pipeline.py` source contains `"class CarePlanV1_2Pipeline(CarePlanPipeline):"`.

- **`CarePlanInternal` without scores** (update `tests/models/test_envelope.py`):
  - `CarePlanInternal(...)` without `before_score`/`after_score` kwargs works.
  - `model.to_dict()` does NOT contain `"before_score"` or `"after_score"` keys.
  - Constructing with `before_score=...` kwargs raises `ValidationError` (strict extra
    checking confirms the fields are truly gone, not just defaulted).

## 8. Manual Intervention Required From You

1. **Approve the `before_score`/`after_score` wire removal.** These two keys disappear
   from the SSE result payload and from Firestore-persisted output docs. Confirm no
   external consumer (batch tool, monitoring dashboard, downstream script) reads those
   keys from the persisted output docs.

2. **Approve adding `"version": "1.0"` to persisted `grading` sub-objects.** Firestore
   `simplify_outputs.output_data.grading` gains a new `version` key. Old persisted docs
   without it will fail `Grading.from_dict()` if that path is ever called on them directly.
   Confirm the grading re-read path (if any) either does not call `Grading.from_dict` or
   tolerates a missing `version` key. See Open Questions §9.1.

3. **Confirm no deploy config references `simplify/` by path.** Cloud Run's Dockerfile,
   `cloudbuild.yaml`, or any startup script that copies or references
   `backend/simplify/` must be updated. Check `backend/Dockerfile` and any CI config.

## 9. Open Questions & Decisions

1. **`Grading.from_dict` on old persisted docs without `"version"`.**
   `[OPEN]` — The `VersionedModel.from_dict` dispatch branch raises `ValueError("Missing
   'version' key")` when called on the family base with no `version_value`. Old Firestore
   docs without `grading.version` would fail if read back through `Grading.from_dict`.
   However, `routes/saved_outputs.py` reads `output_data` as a raw dict and does not
   call `Grading.from_dict`. If no code path calls `Grading.from_dict` on persisted docs,
   this is safe. Verify with `grep -rn "Grading.from_dict" backend/routes/`. If found,
   either make `version` field optional with a default (`version: str = GRADING_VERSION`)
   so `model_validate` fills it in, or keep `Grading` as a plain `JsonModel` and only
   add the enum/version changes without the `VersionedModel` promotion.

2. **`care_plan/v1_2/models.py` import path for `CarePlanV1_2` in route tests.**
   `[OPEN]` — Test files that create `CarePlanV1_2` directly (e.g.
   `tests/simplify/test_pipeline_happy_path.py:22`, `tests/models/test_envelope.py:24`)
   currently import `from models.care_plan import CarePlanV1_2`. After the move these
   must import `from care_plan.v1_2.models import CarePlanV1_2`. Do a full audit of all
   test files and non-pipeline files importing `CarePlanV1_2` directly before starting
   the move.

3. **`simplify/` as a Python package name vs `care_plan/` collision with `models/care_plan.py`.**
   `[RESOLVED: No collision]` — `backend/care_plan/` is a package (directory with
   `__init__.py`), and `backend/models/care_plan.py` is a module. Python resolves them
   separately: `import care_plan` finds the package; `from models.care_plan import ...`
   finds the module under `models/`. Both can coexist in the same `sys.path` root
   (`backend/`) with no conflict because one is `care_plan` (package) and the other is
   `models.care_plan` (sub-module of `models`).

4. **`exclude_fields` / `_llm_schema` helper placement.**
   `[OPEN]` — The helper can live as a private function in `care_plan/v1_2/pipeline.py`
   (used only there) or as a shared utility in `utils/schema.py` (if future pipeline
   versions also need to exclude fields from their schema). Since only one pipeline version
   exists and SP-09 may reorganise the pipeline file, keeping it private in pipeline.py is
   safer for now. Revisit if a v1.3 pipeline needs the same pattern.

5. **Test folder rename: `tests/simplify/` → `tests/care_plan/`.**
   `[OPEN]` — The source folder is renamed `simplify/ → care_plan/` but the test folder
   is `tests/simplify/`. For consistency, `tests/simplify/` should become `tests/care_plan/`.
   This SP's scope includes updating the imports inside those files; whether to also rename
   the test folder itself is left to the implementer. Renaming the test folder is a one-line
   filesystem move with no logic impact.

6. **`Grading` as its own family base vs. a direct `VersionedModel` subclass.**
   `[OPEN]` — If `Grading` subclasses `VersionedModel` directly (no intermediate family
   base), it gets its own `_registry` that starts empty. `Grading.from_dict` will hit the
   `version_value is None` branch and try to dispatch — but there are no subclasses
   registered, so it will raise. The correct resolution is to set `grading_version_value`
   on `Grading` directly (making `Grading` a concrete implementation, not a family base).
   That means `Grading.from_dict` calls `cls.model_validate(data)` directly. This works
   but means adding a second Grading version would require converting `Grading` into a
   family base and introducing `GradingV1_0` — more disruption than the `CarePlan` pattern.
   Alternative: just add `version: str = GRADING_VERSION` as a plain field on the existing
   `JsonModel`-based `Grading` without making it a `VersionedModel`. This satisfies the
   wire-format goal (version appears in the dict) with zero dispatch complexity. Decide
   before implementation which path to take. The recommendation is: **use `JsonModel` with
   a plain `version` field** unless the owner confirms dispatch is needed now.
