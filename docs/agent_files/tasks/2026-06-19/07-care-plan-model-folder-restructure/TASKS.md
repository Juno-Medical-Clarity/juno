# Tasks: Care Plan Model & Folder Restructure (SP-07)

Read `PRD.md` in this folder first. This sub-project is purely structural — no logic
changes, no LLM prompt changes, no frontend changes. It can land independently after
SP-01 (Pydantic migration). All §9 questions are `[RESOLVED]`; no open items remain.

Task order: dependencies flow top-to-bottom. Tasks 1–3 must complete before Tasks 4–7
(they create the new package that later tasks import). Tasks 8–9 depend on Tasks 1–7.
Task 10 (test folder rename + test updates) is the final sweep.

---

### Task 1 — Create `backend/care_plan/` package skeleton

**Files (all NEW):**
- `backend/care_plan/__init__.py`
- `backend/care_plan/interface.py`
- `backend/care_plan/v1_2/__init__.py`

**Changes:**

1. Create `backend/care_plan/__init__.py` as an empty file (matches the current
   `backend/simplify/__init__.py` which is also empty).

2. Create `backend/care_plan/interface.py` by copying
   `backend/simplify/interface.py` verbatim, then update the docstring comment block:
   ```python
   """
   interface.py - Base class for all care_plan pipeline versions.

   To add a new version:
   1. Create care_plan/v<X>/ with __init__.py and pipeline.py
   2. Subclass CarePlanPipeline, implement run()
   3. Register the pipeline in routes/care_plan.py
   """
   ```
   The `CarePlanPipeline` ABC class body is **unchanged**.

3. Create `backend/care_plan/v1_2/__init__.py` with exactly:
   ```python
   # Import models to trigger CarePlanV1_2 self-registration in CarePlan._registry.
   from care_plan.v1_2.models import CarePlanV1_2  # noqa: F401
   ```

**Acceptance:**
- `python -c "from care_plan.interface import CarePlanPipeline"` succeeds from
  `backend/` working directory.
- `backend/care_plan/v1_2/__init__.py` exists and contains the registration import.
- `backend/simplify/` still exists (not deleted yet — Task 3 does that).

---

### Task 2 — Create `backend/care_plan/v1_2/models.py` (move v1.2 types out of `models/care_plan.py`)

**Files:**
- `backend/care_plan/v1_2/models.py` (NEW)

**Changes:**

Create `backend/care_plan/v1_2/models.py`. Copy all concrete v1.2 types verbatim from
`backend/models/care_plan.py` — field definitions, defaults, and types are unchanged.
Only the import header and the module docstring change:

```python
"""Concrete v1.2 care-plan model types."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from models.base import JsonModel
from models.care_plan import CarePlan, CARE_PLAN_VERSION

Source = Literal["documents", "recording", "notes"]
Importance = Literal["high", "low"]


class ReasonForVisit(JsonModel):
    reason: str = ""
    description: str = ""


class DiagnosisDetail(JsonModel):
    # ... copy exactly from models/care_plan.py lines 22-28


class Diagnosis(JsonModel):
    # ... copy exactly from models/care_plan.py lines 30-33


class Medication(JsonModel):
    # ... copy exactly from models/care_plan.py lines 36-49


class Test(JsonModel):
    # ... copy exactly from models/care_plan.py lines 52-58


class Procedure(JsonModel):
    # ... copy exactly from models/care_plan.py lines 62-68


class OtherInstruction(JsonModel):
    # ... copy exactly from models/care_plan.py lines 72-79


class FollowUp(JsonModel):
    time_frame: str = ""
    description: str = ""


class WarningSign(JsonModel):
    # ... copy exactly from models/care_plan.py lines 83-95


class GlossaryTerm(JsonModel):
    definition: str
    source: str
    imgUrl: str | None = None
    altText: str | None = None


class RawArtifacts(JsonModel):
    text: str
    simplified_text: str
    clarified_text: str


class CarePlanV1_2(CarePlan):
    version_value: ClassVar[str] = CARE_PLAN_VERSION

    doc_type: Literal["care_plan"] = "care_plan"
    version: Literal["1.2"] = CARE_PLAN_VERSION
    urgency: Literal["normal", "caution", "concern", "urgent"] = "normal"
    summary: str = ""
    reason_for_visit: list[ReasonForVisit] = Field(default_factory=list)
    diagnosis: Diagnosis = Field(default_factory=Diagnosis)
    medications: list[Medication] = Field(default_factory=list)
    tests: list[Test] = Field(default_factory=list)
    procedures: list[Procedure] = Field(default_factory=list)
    other: list[OtherInstruction] = Field(default_factory=list)
    follow_up: list[FollowUp] = Field(default_factory=list)
    warning_signs: list[WarningSign] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    low_priority: list[str] = Field(default_factory=list)
    terms: dict[str, GlossaryTerm] = Field(default_factory=dict)
    raw: RawArtifacts | None = None
```

Copy all fields exactly — do not summarize or drop any field.

**Acceptance:**
- `python -c "from care_plan.v1_2.models import CarePlanV1_2; print(CarePlanV1_2.version_value)"` prints `1.2` from the `backend/` working directory.
- `python -c "from care_plan.v1_2 import CarePlanV1_2"` also works (via the `__init__.py` from Task 1).
- `CarePlanV1_2.model_validate({"doc_type": "care_plan", "version": "1.2"})` passes.

---

### Task 3 — Create `backend/care_plan/v1_2/pipeline.py` (move + update pipeline)

**Files:**
- `backend/care_plan/v1_2/pipeline.py` (NEW — adapted from `backend/simplify/v1_2/pipeline.py`)

**Changes:**

Create `backend/care_plan/v1_2/pipeline.py`. The file is a modified copy of
`backend/simplify/v1_2/pipeline.py` with the following changes:

**A. Update the module docstring** (first line): replace `simplify/v1_2/pipeline.py`
with `care_plan/v1_2/pipeline.py`.

**B. Replace the import block** (lines 25–38 of the original):
```python
# REMOVE these imports:
from models.care_plan import (
    CARE_PLAN_VERSION,
    CarePlan,
    CarePlanV1_2,
    CarePlanV1_2StructuredLLM,
)
from simplify.interface import CarePlanPipeline

# ADD these imports instead:
import copy

from models.care_plan import CARE_PLAN_VERSION, CarePlan
from care_plan.interface import CarePlanPipeline
from care_plan.v1_2.models import CarePlanV1_2
```
Keep all other imports (`json`, `logging`, `pydantic.ValidationError`, `utils.*`) unchanged.

**C. Replace the `_STRUCTURING_SCHEMA` constant** (lines 43–46 of the original):
```python
# REMOVE:
_STRUCTURING_SCHEMA = json.dumps(
    CarePlanV1_2StructuredLLM.model_json_schema(),
    indent=2,
)

# ADD (after the imports, before the class):
def _llm_schema(model_cls, exclude: set[str]) -> dict:
    """Generate a JSON schema from model_cls with the given field names excluded."""
    schema = copy.deepcopy(model_cls.model_json_schema())
    props = schema.get("properties", {})
    for field in exclude:
        props.pop(field, None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in exclude]
    return schema


_STRUCTURING_SCHEMA = json.dumps(
    _llm_schema(CarePlanV1_2, exclude={"terms", "raw"}),
    indent=2,
)
```

**D. Rename the class** (line 49 of the original):
```python
# REMOVE:
class V1_2Pipeline(CarePlanPipeline):

# ADD:
class CarePlanV1_2Pipeline(CarePlanPipeline):
```

**E. Update `structure_appointment_note`** (lines 174–179 of the original):
```python
# REMOVE:
try:
    model = CarePlanV1_2StructuredLLM.model_validate(raw)
except ValidationError as e:
    raise ValueError(f"LLM structure output failed validation: {e}") from e

return model.model_dump(mode="json")

# ADD:
try:
    model = CarePlanV1_2.model_validate(raw)
except ValidationError as e:
    raise ValueError(f"LLM structure output failed validation: {e}") from e

return model.model_dump(mode="json", exclude={"terms", "raw"})
```

All other methods (`_generate_text`, `_generate_json`, `simplify_language_with_term_plan`,
`clarify_and_action`, `run`) are copied verbatim — no logic changes.

**Acceptance:**
- `python -c "from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline"` succeeds.
- `CarePlanV1_2Pipeline` is accessible; `V1_2Pipeline` does NOT exist in this module.
- `_llm_schema(CarePlanV1_2, {"terms", "raw"})["properties"]` does not contain `"terms"` or `"raw"`.
- `_STRUCTURING_SCHEMA` is valid JSON (parse it with `json.loads`).

---

### Task 4 — Delete `backend/simplify/` directory

**Files:**
- `backend/simplify/__init__.py` — DELETE
- `backend/simplify/interface.py` — DELETE
- `backend/simplify/v1_2/__init__.py` — DELETE
- `backend/simplify/v1_2/pipeline.py` — DELETE
- Remove the `backend/simplify/` directory tree entirely.

**Prerequisite:** Tasks 1–3 must be complete. Verify `from care_plan.v1_2.pipeline
import CarePlanV1_2Pipeline` works before deleting.

**How:**
```bash
rm -rf backend/simplify/
```

**Acceptance:**
- `backend/simplify/` directory does not exist.
- `python -c "from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline"` still succeeds.
- `python -c "from simplify.v1_2.pipeline import V1_2Pipeline"` now raises `ModuleNotFoundError`.

---

### Task 5 — Slim down `backend/models/care_plan.py` to base-only

**File:** `backend/models/care_plan.py`

**Changes:**

Remove everything except the two items the PRD specifies remain: `CARE_PLAN_VERSION` and
`CarePlan(VersionedModel)`. The new file content:

```python
"""Strict Pydantic care-plan models."""

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

Remove from this file:
- All imports except `from __future__ import annotations` and `from .base import VersionedModel`
- `Source`, `Importance` type aliases (they move to `care_plan/v1_2/models.py` — already done in Task 2)
- `ReasonForVisit`, `DiagnosisDetail`, `Diagnosis`, `Medication`, `Test`, `Procedure`,
  `OtherInstruction`, `FollowUp`, `WarningSign`, `GlossaryTerm`, `RawArtifacts`
- `CarePlanV1_2`
- `CarePlanV1_2StructuredLLM`

**Acceptance:**
- `python -c "from models.care_plan import CarePlan, CARE_PLAN_VERSION"` succeeds.
- `python -c "from models.care_plan import CarePlanV1_2"` raises `ImportError`.
- `python -c "from models.care_plan import CarePlanV1_2StructuredLLM"` raises `ImportError`.
- `CarePlan.from_dict({"version": "1.2", "doc_type": "care_plan"})` returns a `CarePlanV1_2`
  instance (registration still works via the `care_plan.v1_2` package import chain).

---

### Task 6 — Update `backend/models/__init__.py` exports

**File:** `backend/models/__init__.py`

**Changes:**

Replace the current content with:

```python
"""Backend model exports."""

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

Note: `GradingMethodReason` is added here; it will exist after Task 7 completes. If
running Task 6 before Task 7 causes an `ImportError`, apply Tasks 7 first or apply
both together.

**Acceptance:**
- `python -c "from models import CarePlan, CarePlanInternal, Grading, GradingEntry, GradingMethodReason, build_grading, Input, InputFile, JsonModel, Metrics, VersionedModel"` succeeds.
- `python -c "from models import CarePlanV1_2"` raises `ImportError`.
- `python -c "from models import CarePlanV1_2StructuredLLM"` raises `ImportError`.
- `python -c "from models import is_legacy_shape"` raises `ImportError`.
- `python -c "import models; print(models.__all__)"` matches exactly the list above.

---

### Task 7 — Convert `_METHOD_REASONING` to `GradingMethodReason` enum in `grading.py`

**File:** `backend/models/grading.py`

**Changes:**

**A. Add `import enum` at the top of the file** (after `from datetime import ...`).

**B. Replace the `_METHOD_REASONING` dict** (lines 27–34) with a `GradingMethodReason` enum:
```python
class GradingMethodReason(str, enum.Enum):
    smog           = "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials"
    flesch_kincaid = "Flesch-Kincaid Reading Ease + Grade Level (1975) — sentence length × syllable load"
    dale_chall     = "Dale-Chall (1948/1995) — difficult words outside the 3,000 familiar-word list"
    pemat          = "PEMAT (AHRQ 2013) — automated approximation of items 3,8,14,21-22 (understandability) and 27-33 (actionability)"
    sam            = "SAM (Doak et al. 1996) — automated approximation of content, literacy demand, and layout/typography domains"
    cdc_cci        = "CDC Clear Communication Index — automated approximation of main message, behavioral recommendations, numbers, and call-to-action items"
```

**C. Update `build_grading`** — in the `for method_name in (...)` loop, change the
`reasoning=` line from (line 59 of current file):
```python
# REMOVE:
reasoning=_METHOD_REASONING[method_name],

# ADD:
reasoning=GradingMethodReason[method_name].value,
```

Optionally (implementer's call, per PRD §4.8): replace the hard-coded list
`("smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci")` with
`list(GradingMethodReason.__members__)` to derive it from the enum.

No other changes to `grading.py`. `Grading` stays as `JsonModel` — do NOT add a
`version` field or promote to `VersionedModel` (PRD §4.9 RESOLVED).

**Acceptance:**
- `python -c "from models.grading import GradingMethodReason; print(GradingMethodReason['smog'].value)"` prints the SMOG reasoning string.
- `GradingMethodReason` has exactly 6 members: `smog`, `flesch_kincaid`, `dale_chall`, `pemat`, `sam`, `cdc_cci`.
- `Grading().to_dict()` still equals `{"entries": [], "enabled": True, "graded_at": None}` (unchanged wire shape).

---

### Task 8 — Remove `before_score` and `after_score` from `CarePlanInternal` and `is_legacy_shape` from `envelope.py`

**File:** `backend/models/envelope.py`

**Changes:**

**A. Remove `before_score` and `after_score` fields** from `CarePlanInternal`:
```python
# REMOVE these two lines from CarePlanInternal:
before_score: dict | None = None
after_score: dict | None = None
```
The class docstring should also be updated to drop mention of scores.

**B. Delete `is_legacy_shape`** — remove the entire function (lines 38–43):
```python
# REMOVE:
def is_legacy_shape(data: dict) -> bool:
    """Return True if *data* lacks the new-style 'care_plan' top-level key.

    Used to distinguish legacy flat outputs from the structured envelope format.
    """
    return "care_plan" not in data
```

The final `envelope.py` has no `is_legacy_shape` function and `CarePlanInternal` has no
`before_score`/`after_score` fields. No other changes to the file.

**Acceptance:**
- `python -c "from models.envelope import CarePlanInternal"` succeeds.
- `python -c "from models.envelope import is_legacy_shape"` raises `ImportError`.
- Constructing `CarePlanInternal(metrics=..., input=..., grading=..., care_plan=...)` works without `before_score`/`after_score`.
- Constructing with `before_score={...}` as a kwarg raises `ValidationError` (extra fields forbidden).
- `CarePlanInternal(...).to_dict()` does NOT contain `"before_score"` or `"after_score"` keys.

---

### Task 9 — Update `routes/care_plan.py` and `routes/batch.py` for renamed pipeline and removed scores

**Files:**
- `backend/routes/care_plan.py`
- `backend/routes/batch.py`

**Changes in `routes/care_plan.py`:**

1. **Replace the import** (line 32):
   ```python
   # REMOVE:
   from simplify.v1_2.pipeline import V1_2Pipeline
   # ADD:
   from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
   ```

2. **Replace the pipeline instantiation** (line 348):
   ```python
   # REMOVE:
   pipeline = V1_2Pipeline()
   # ADD:
   pipeline = CarePlanV1_2Pipeline()
   ```

3. **Shrink the sentinel yield** (line 472). The `before_score` and `after_score` locals
   are still computed and passed to `build_grading()` earlier in `run_care_plan_pipeline` —
   that call is unchanged. Only the yield tuple shrinks, since the scores no longer need
   to travel outside the generator:
   ```python
   # REMOVE:
   yield (RESULT_SENTINEL, care_plan, grading, text, clarified, before_score, after_score)
   # ADD:
   yield (RESULT_SENTINEL, care_plan, grading, text, clarified)
   ```

4. **Shrink the unpacking** (line 551):
   ```python
   # REMOVE:
   _, care_plan, grading, _raw_text, _clarified_text, before_score, after_score = pipeline_result
   envelope = CarePlanInternal(
       metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
       before_score=before_score, after_score=after_score,
   )
   # ADD:
   _, care_plan, grading, _raw_text, _clarified_text = pipeline_result
   envelope = CarePlanInternal(
       metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
   )
   ```

**Changes in `routes/batch.py`:**

Update the unpacking and `CarePlanInternal` construction (lines 201–210):
```python
# REMOVE:
_, care_plan, grading, _raw_text, _clarified_text, before_score, after_score = chunk
envelope = CarePlanInternal(
    metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
    before_score=before_score, after_score=after_score,
)
# ADD:
_, care_plan, grading, _raw_text, _clarified_text = chunk
envelope = CarePlanInternal(
    metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
)
```

**Acceptance:**
- `python -c "import routes.care_plan"` succeeds (no `ImportError` or `NameError`).
- `python -c "import routes.batch"` succeeds.
- `grep "V1_2Pipeline" backend/routes/care_plan.py` returns nothing.
- `grep "before_score\|after_score" backend/routes/care_plan.py` — only lines inside
  `run_care_plan_pipeline` where the scores are computed and passed to `build_grading()`.
  The yield tuple and the unpacking below it must have NO `before_score`/`after_score`.
- `grep "before_score\|after_score" backend/routes/batch.py` returns nothing.

---

### Task 10 — Update all tests to reflect the restructure

**Files (all existing — in-place edits):**

#### 10a. Rename test folder `tests/simplify/` → `tests/care_plan/`

```bash
mv backend/tests/simplify/ backend/tests/care_plan/
```

Update `BACKEND_DIR` depth: `test_pipeline_interface.py` line 4 currently uses
`Path(__file__).resolve().parents[2]` (from `tests/simplify/`). After the move the
depth is the same (`tests/care_plan/` is still two levels deep), so no change needed.

#### 10b. `tests/care_plan/test_pipeline_interface.py`

Replace all `simplify` path references with `care_plan`:

```python
# REMOVE:
assert (BACKEND_DIR / "simplify" / "v1_2").is_dir()
# ADD:
assert (BACKEND_DIR / "care_plan" / "v1_2").is_dir()

# REMOVE:
interface_source = (BACKEND_DIR / "simplify" / "interface.py").read_text()
# ADD:
interface_source = (BACKEND_DIR / "care_plan" / "interface.py").read_text()

# REMOVE:
v1_2_source = (BACKEND_DIR / "simplify" / "v1_2" / "pipeline.py").read_text()
# ADD:
v1_2_source = (BACKEND_DIR / "care_plan" / "v1_2" / "pipeline.py").read_text()
```

Update source-text assertions (line 18–20):
```python
# REMOVE:
assert "from simplify.interface import CarePlanPipeline" in v1_2_source
assert "class V1_2Pipeline(CarePlanPipeline):" in v1_2_source
# ADD:
assert "from care_plan.interface import CarePlanPipeline" in v1_2_source
assert "class CarePlanV1_2Pipeline(CarePlanPipeline):" in v1_2_source
```

Add assertion that the old folder is gone:
```python
assert not (BACKEND_DIR / "simplify").exists()
```

#### 10c. `tests/care_plan/test_pipeline_schema.py`

1. Replace imports (lines 8–9):
   ```python
   # REMOVE:
   from simplify.v1_2 import pipeline as pipeline_module
   from simplify.v1_2.pipeline import V1_2Pipeline
   # ADD:
   from care_plan.v1_2 import pipeline as pipeline_module
   from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
   ```

2. Replace all `V1_2Pipeline` references with `CarePlanV1_2Pipeline` (lines 21, 23, 32,
   44 — every occurrence in the file).

3. Add a new test for the `_llm_schema` helper at the bottom of the file:
   ```python
   def test_llm_schema_excludes_terms_and_raw():
       from care_plan.v1_2.pipeline import _llm_schema
       from care_plan.v1_2.models import CarePlanV1_2

       schema = _llm_schema(CarePlanV1_2, {"terms", "raw"})
       props = schema["properties"]

       assert "terms" not in props
       assert "raw" not in props
       expected = set(CarePlanV1_2.model_fields) - {"terms", "raw"}
       assert set(props) == expected


   def test_llm_schema_model_validate_without_terms_and_raw():
       from care_plan.v1_2.models import CarePlanV1_2

       model = CarePlanV1_2.model_validate(
           {"doc_type": "care_plan", "version": "1.2", "summary": "You came in for care."}
       )
       dumped = model.model_dump(mode="json", exclude={"terms", "raw"})

       assert "terms" not in dumped
       assert "raw" not in dumped
       assert dumped["summary"] == "You came in for care."
   ```

#### 10d. `tests/models/test_care_plan.py`

1. Update the import block (lines 9–15): remove `CarePlanV1_2StructuredLLM` from the
   `from models.care_plan import ...` import. Add a new import:
   ```python
   from care_plan.v1_2.models import CarePlanV1_2
   ```
   Remove `CarePlanV1_2` from the `models.care_plan` import (it no longer lives there).

2. Rewrite `test_structured_llm_schema_properties_match_care_plan_structured_fields`
   (lines 95–100) to use the `_llm_schema` helper instead of `CarePlanV1_2StructuredLLM`:
   ```python
   def test_structured_llm_schema_properties_match_care_plan_structured_fields():
       from care_plan.v1_2.pipeline import _llm_schema
       from care_plan.v1_2.models import CarePlanV1_2

       care_plan_fields = set(CarePlanV1_2.model_fields)
       structured_fields = care_plan_fields - {"terms", "raw"}
       schema_properties = set(_llm_schema(CarePlanV1_2, {"terms", "raw"})["properties"])

       assert schema_properties == structured_fields
   ```

3. Update all other imports of `CarePlanV1_2` in this file to use
   `from care_plan.v1_2.models import CarePlanV1_2` (the class is no longer in
   `models.care_plan`).

#### 10e. `tests/models/test_exports.py`

1. Remove `CarePlanV1_2`, `CarePlanV1_2StructuredLLM`, and `is_legacy_shape` from the
   `from models import (...)` import block.
2. Add `GradingMethodReason` to that import block.
3. Rewrite the `__all__` assertion to match PRD §4.11 exactly:
   ```python
   assert models.__all__ == [
       "JsonModel",
       "VersionedModel",
       "CarePlan",
       "CarePlanInternal",
       "Grading",
       "GradingEntry",
       "GradingMethodReason",
       "build_grading",
       "Input",
       "InputFile",
       "Metrics",
   ]
   ```
4. Remove any import or assertion line that references `CarePlanV1_2`, `CarePlanV1_2StructuredLLM`,
   or `is_legacy_shape`.

#### 10f. `tests/models/test_envelope.py`

1. **`_envelope_dict()` helper** (lines 36–44): remove `"before_score": None` and
   `"after_score": None` from the dict.

2. **`test_care_plan_internal_serializes_with_care_plan_key_and_scores_present`** (lines 47–71):
   - Remove `before_score` and `after_score` from the `set(data)` equality check (line 59–66).
   - Remove lines 67–68 (`assert data["before_score"] is None` / `assert data["after_score"] is None`).
   - Remove lines 70–71 (`assert "before_score" not in data["care_plan"]` / same for after).
   - Rename the test to `test_care_plan_internal_serializes_with_care_plan_key`.
   - Add a positive assertion that scores are absent:
     ```python
     assert "before_score" not in data
     assert "after_score" not in data
     ```
   - Add a ValidationError check:
     ```python
     def test_care_plan_internal_rejects_extra_score_kwargs():
         from models.envelope import CarePlanInternal
         from pydantic import ValidationError
         with pytest.raises(ValidationError):
             CarePlanInternal(
                 metrics=_metrics(),
                 input=Input.from_text("Patient note"),
                 grading=Grading(),
                 care_plan=_care_plan(),
                 before_score={"composite": 60},
             )
     ```

3. **`test_care_plan_internal_accepts_route_v1_2_kwargs_and_serializes_care_plan_key`** (lines 74–92):
   Remove the `before_score` and `after_score` kwargs from the `CarePlanInternal(...)` call.
   Remove assertions on `data["before_score"]` and `data["after_score"]`. Rename the test
   to `test_care_plan_internal_accepts_route_v1_2_kwargs_and_serializes_care_plan_key`.

4. **`test_care_plan_internal_round_trips_composite_scores`** (lines 108–122):
   Delete this test entirely. Replace with:
   ```python
   def test_care_plan_internal_scores_are_absent_from_envelope():
       from models.envelope import CarePlanInternal

       model = CarePlanInternal(
           metrics=_metrics(),
           input=Input.from_text("Patient note"),
           grading=Grading(),
           care_plan=_care_plan(),
       )
       data = model.to_dict()

       assert "before_score" not in data
       assert "after_score" not in data
   ```

5. **`test_is_legacy_shape_checks_for_care_plan_key`** (lines 134–138): **Delete** this
   entire test.

#### 10g. `tests/models/test_grading_model.py`

Add two new tests after the existing ones:

```python
def test_grading_method_reason_enum_has_expected_members():
    from models.grading import GradingMethodReason

    assert set(GradingMethodReason.__members__) == {
        "smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci"
    }


def test_grading_method_reason_smog_value_matches_expected_string():
    from models.grading import GradingMethodReason

    assert GradingMethodReason["smog"].value == (
        "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials"
    )


def test_build_grading_entries_have_reasoning_from_enum(monkeypatch):
    from models.grading import GradingMethodReason, build_grading
    from utils.scoring import score_text

    before_score = score_text(FIXTURE_TEXT)
    after_score = score_text(FIXTURE_CLARIFIED)
    grading = build_grading(before_score, FIXTURE_TEXT, after_score, FIXTURE_CLARIFIED)

    method_entries = [e for e in grading.entries if e.name != "combined"]
    for entry in method_entries:
        assert entry.reasoning == GradingMethodReason[entry.name].value
```

Do NOT update `test_grading_default_serializes_expected_json` — the wire shape
(`{"entries": [], "enabled": True, "graded_at": None}`) is unchanged (PRD §4.9).

#### 10h. `tests/models/test_pipeline_executors.py`

Update the `@patch` decorator (line 40):
```python
# REMOVE:
@patch("routes.care_plan.V1_2Pipeline", ...)
# ADD:
@patch("routes.care_plan.CarePlanV1_2Pipeline", ...)
```
Apply to every `@patch("routes.care_plan.V1_2Pipeline", ...)` call in the file.

Also update `tests/integration/test_care_plan_persistence.py` — every occurrence of
`@patch("routes.care_plan.V1_2Pipeline", ...)` (lines 64, 118, 181, 232, 268, 311):
```python
# REMOVE:
@patch("routes.care_plan.V1_2Pipeline", return_value=FakePipeline())
# ADD:
@patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FakePipeline())
```

#### 10i. `tests/routes/test_care_plan_route.py`

Lines 295–296 — replace score assertions with absence assertions:
```python
# REMOVE:
assert final_payload["before_score"] == {"before": 1}
assert final_payload["after_score"] == {"after": 2}
# ADD:
assert "before_score" not in final_payload
assert "after_score" not in final_payload
```

Also audit the test setup above line 295: if the test injects a mock pipeline that
produces a sentinel tuple with 7 elements (including `before_score`/`after_score`), shrink
that mock to 5 elements to match the new sentinel shape:
```python
# Anywhere the mock pipeline yields a tuple like:
(RESULT_SENTINEL, care_plan, grading, text, clarified, {"before": 1}, {"after": 2})
# Change to:
(RESULT_SENTINEL, care_plan, grading, text, clarified)
```

#### 10j. `tests/fixtures/care_plan.py`

Remove `"before_score"` and `"after_score"` keys from `SAMPLE_PIPELINE_OUTPUT` dict
(lines 44–45):
```python
# REMOVE:
"before_score": None,
"after_score": None,
```
Also update the comment on line 16 to remove the `(plus optional before_score/after_score)`
parenthetical.

**Acceptance for Task 10 as a whole:**
- `grep -rn "V1_2Pipeline" backend/tests/` returns nothing.
- `grep -rn "CarePlanV1_2StructuredLLM" backend/tests/` returns nothing.
- `grep -rn "is_legacy_shape" backend/tests/` returns nothing.
- `grep -rn "from simplify" backend/tests/` returns nothing.
- `grep -rn "before_score\|after_score" backend/tests/fixtures/care_plan.py` returns nothing.
- `python -m pytest backend/tests/ -q` passes (all tests green).

---

## Summary of what requires you (not a dev agent)

1. **Wire removal of `before_score`/`after_score` — CONFIRMED** (PRD §8.1). No consumer
   reads these keys from the SSE envelope. A dev agent may proceed.

2. **Folder rename `simplify/` → `care_plan/` in deploy/CI config — CONFIRMED** (PRD §8.3).
   No CI or deploy config references `simplify/`. A dev agent may proceed.

3. **Run `grep -rn "from models.care_plan import.*CarePlanV1_2" backend/`** before Task 2
   to catch any call site not covered in this task list (PRD §9.2 RESOLVED). The known
   hits are `tests/models/test_care_plan.py:13`, `tests/models/test_envelope.py:9`, and
   `backend/simplify/v1_2/pipeline.py:25–30`. If the grep finds others, fix them as part
   of the relevant task above.
