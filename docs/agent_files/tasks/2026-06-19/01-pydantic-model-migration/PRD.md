# PRD: Pydantic Model Migration (SP1)

Sub-project 1 of 6, and the **foundation** of the Juno backend refactor — every other
sub-project (SP2 route consolidation, SP3 utils cleanup, SP4 observability, SP5 frontend,
SP6 testing) depends on the typed models defined here. This sub-project lands **first**.

## 1. Problem

The backend has a **hand-written serialization framework** instead of a real schema. Models in
`backend/models/` are plain `@dataclass`es that subclass an in-house `JsonModel` /
`VersionedJsonModel` base (`backend/models/base.py`):

- `JsonModel.to_dict()` is `dataclasses.asdict()`; `from_dict()` reflects over
  `__dataclass_fields__`, resolves type hints, and recursively reconstructs nested models by
  hand. This re-implements, badly, what Pydantic does natively.
- `VersionedJsonModel` maintains a per-base `_registry` via `__init_subclass__` plus a `register()`
  decorator and a `_is_registered` flag to suppress double-dispatch — a brittle bespoke version
  router (`base.py:76-161`).
- `SimplifiedCarePlan` (`care_plan.py`) is **not actually a schema**: it is `version: str` + an
  opaque `data: dict`. The real care-plan shape (doc_type, diagnosis, medications, terms, raw, …)
  lives **only** in a JSON file fed to the LLM (`simplify/v1_2/appointment.schema.json`) and in
  hard-coded backfill defaults inside `pipeline.py:239-261`. Nothing validates that the persisted
  care plan matches that shape. The schema-of-record is a string blob, not the model.
- Each of `grading.py`, `input.py`, `metrics.py` hand-writes its own `to_dict()` / `from_dict()`,
  duplicating boilerplate and drifting (e.g. `GradingEntry.from_dict` vs the base reflective path).
- There is **no validation at all**. LLM output is `json.loads`-ed, backfilled with defaults, and
  shoved into `data: dict`. If the model emits an extra field, a renamed field, or a wrong type, it
  is silently persisted. LLM drift is invisible until the frontend breaks.
- The JSON schema string in `appointment.schema.json` and the Python defaults in `pipeline.py` are
  **two copies of the same contract** that must be kept in sync by hand.

We want the **model to BE the schema** — like a C# DTO with a JSON converter plus validation:
one Pydantic v2 class defines the shape, validates on construction, (de)serializes through itself,
and generates the LLM's JSON schema. Strict (`extra="forbid"`) so LLM drift fails loudly.

Two correctness bugs surface from reading the current code, both fixed by SP1's locked decisions:

1. **`raw` is silently dropped on save.** `utils/save_output.py:_without_raw()` strips the `raw`
   key before persisting to Firestore. But the re-grade endpoint (`routes/grading.py:55-58`) reads
   `output_data.simplified_care_plan.raw.text` to re-score a saved doc — which is **always absent**
   for persisted docs. The saved-id re-grade path is effectively broken today. SP1's locked
   decision "raw is kept + saved" fixes this.
2. **`SimplifyOutput.input` is double-written.** The pipeline constructs the envelope with
   `input=Input.from_text(text)` (`simplify_v1_2.py:447`) then the stream layer overwrites
   `result_data["input"] = input_model.to_dict()` (`simplify_v1_2.py:515`). The typed envelope is
   not the single source of truth. SP1 makes the envelope authoritative; SP2 owns removing the
   override.

## 2. Goals

1. Convert **all** backend models to Pydantic v2 `BaseModel`: `base.py`, `care_plan.py`,
   `envelope.py`, `grading.py`, `input.py`, `metrics.py`, and update `__init__.py` exports.
2. Build a **full per-version `CarePlan` framework**: a version-agnostic base + a registry keyed by
   version string + a concrete `CarePlanV1_2` that models the real v1.2 shape (structured fields +
   `terms` + `raw`) as a true Pydantic schema. Adding a future `v1_3` = one new subclass + one
   registry line, no base changes.
3. **Strict validation everywhere:** `model_config = ConfigDict(extra="forbid")` on every model, so
   unknown / renamed / extra fields raise `ValidationError`. Document the LLM-output interaction.
4. **`raw` is part of the model and is SAVED** (kept in persisted Firestore output, not stripped).
5. Rename the composite envelope `SimplifyOutput` → **`CarePlanInternal`** (internal composite of
   `care_plan` + `metrics` + `input` + `grading`). Keep a thin `SimplifyOutput` alias for one
   release so SP2 can migrate call-sites without a hard break.
6. **Drop `appointment.schema.json`.** Pydantic becomes the single source of truth; the v1.2 pipeline
   prompt generates its schema from `CarePlanV1_2.model_json_schema()` instead of reading the file.
7. Define the **typed contract each layer returns** so SP2 can compose routes:
   simplify pipeline → `CarePlanV1_2` (a `CarePlan` subclass), grading → `Grading`,
   input resolution → `Input`, run telemetry → `Metrics`, the composite → `CarePlanInternal`.
8. Write the **per-model unit-test plan/specs** (round-trip, strict-reject, version dispatch). SP1
   only authors specs in this doc; SP6 owns the broader test reorg + CI wiring.

## 3. Non-Goals

- **Not** consolidating or renaming routes, and **not** doing the global `simplify → care_plan`
  rename across routes/blueprints — that is **SP2**. SP1 only aligns *model* names
  (`SimplifyOutput → CarePlanInternal`) and exposes the alias.
- **Not** removing the `v1` / `v1_1` pipelines or their routes — that is **SP2/SP3**. SP1's
  `CarePlan` registry therefore only ships the **v1.2** concrete model, but the base/registry are
  version-agnostic so older/newer versions plug in.
- **Not** changing scoring math or the grading schema — SP3 (grading rework) already landed the
  `Grading`/`GradingEntry`/`build_grading` shape; SP1 only re-expresses those classes in Pydantic
  with identical field names and output JSON.
- **Not** changing the SSE protocol, the GCS/PDF flow, or auth.
- **Not** building a Firestore data-migration runner. SP1 specifies the read-path back-compat
  strategy and flags the migration as **manual** (see §8, §9).

## 4. Architecture Decisions

### 4.0 Dependency: pin Pydantic in requirements

Pydantic v2 (`2.13.4`) is already importable in the deployed venv (transitive via
`google-cloud-aiplatform`), but it is **not pinned** in `backend/requirements.txt`. Relying on a
transitive dep for a load-bearing import is unsafe. Add an explicit pin (see §8 — this is a manual
step the human performs, because it changes the dependency contract).

```
pydantic>=2.7,<3
```

### 4.1 `models/base.py` — Pydantic base + version registry mixin

Replace the dataclass `JsonModel`/`VersionedJsonModel` with a Pydantic base that carries the strict
config and the back-compat serialization aliases, plus a generic **version-dispatch mixin** that
any versioned model family can use.

```python
# backend/models/base.py
from __future__ import annotations
from typing import Any, ClassVar, Type, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T", bound="JsonModel")


class JsonModel(BaseModel):
    """Strict Pydantic base for all backend models.

    extra="forbid"  -> reject unknown/renamed/extra fields (catches LLM drift).
    The to_dict/from_dict shims keep the old call-sites working during the SP1→SP2
    transition; new code should prefer model_dump()/model_validate() directly.
    """
    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict:
        # mode="json" so datetimes/enums serialise to JSON-native types for Firestore.
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T:
        return cls.model_validate(data)


VT = TypeVar("VT", bound="VersionedModel")


class VersionedModel(JsonModel):
    """Mixin for a family of models dispatched by a `version` string field.

    Each concrete family base (e.g. CarePlan) sets its own _registry and the
    field name that holds the version. Subclasses self-register via __init_subclass__
    using the class attribute `version_value`.
    """
    version: str

    # Each *family base* gets its own registry (see CarePlan below).
    _registry: ClassVar[dict[str, Type["VersionedModel"]]] = {}
    # Concrete subclasses set this to the version string they handle.
    version_value: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # A direct family base (parent is VersionedModel) gets a fresh registry.
        if VersionedModel in cls.__bases__:
            cls._registry = {}
        # A concrete subclass with a declared version_value self-registers.
        elif getattr(cls, "version_value", None) is not None:
            cls._registry[cls.version_value] = cls

    @classmethod
    def from_dict(cls: Type[VT], data: dict) -> VT:
        """Dispatch on data['version'] to the registered concrete subclass.

        Called on a family base -> looks up subclass, validates with it.
        Called on a concrete subclass -> validates directly (no dispatch).
        """
        if cls.version_value is not None:           # concrete subclass
            return cls.model_validate(data)
        version = data.get("version")
        if version is None:
            raise ValueError(f"Missing 'version' key for {cls.__name__}")
        subclass = cls._registry.get(version)
        if subclass is None:
            available = ", ".join(sorted(cls._registry)) or "(none registered)"
            raise ValueError(
                f"Unknown version {version!r} for {cls.__name__}. Available: {available}"
            )
        return subclass.model_validate(data)  # type: ignore[return-value]
```

Notes:
- `extra="forbid"` is inherited by every subclass automatically.
- The registry is keyed by the literal version string (`"1.2"`), matching today's behavior.
- We rename `VersionedJsonModel → VersionedModel` and drop the `register()` decorator + the
  `_is_registered` flag; self-registration via `version_value` is simpler and removes the
  decorator-vs-registry footgun documented in `care_plan.py:82-88` today.

### 4.2 `models/care_plan.py` — the per-version CarePlan framework

This is the core deliverable. `CarePlan` is the version-agnostic family base; `CarePlanV1_2` is the
concrete, fully-typed v1.2 schema derived from `appointment.schema.json` + the `pipeline.py`
defaults + the frontend `AppointmentNote` type.

```python
# backend/models/care_plan.py
from __future__ import annotations
from typing import ClassVar, Literal
from pydantic import BaseModel, ConfigDict, Field
from .base import VersionedModel, JsonModel


# ---- shared sub-models (strict) ------------------------------------------
class ReasonForVisit(JsonModel):
    reason: str = ""
    description: str = ""

class DiagnosisDetail(JsonModel):
    title: str = ""
    plain_name: str = ""
    description: str = ""
    what_it_means_for_you: str = ""
    severity: Literal["high", "medium", "low"] | None = None

class Diagnosis(JsonModel):
    main_conclusion: str = ""
    changed_since_last_visit: str = ""
    details: list[DiagnosisDetail] = Field(default_factory=list)

class Medication(JsonModel):
    title: str = ""
    plain_name: str = ""
    why: str = ""
    dosage: str = ""
    frequency: str = ""
    timing: str = ""
    duration: str = ""
    instructions: str = ""
    side_effects_to_watch: str = ""
    importance: Literal["high", "low"] = "low"
    source: Literal["documents", "recording", "notes"] | None = None
    change: bool = False
    change_description: str = ""

class Test(JsonModel):
    title: str = ""
    plain_name: str = ""
    why: str = ""
    description: str = ""
    preparation: str = ""
    importance: Literal["high", "low"] = "low"
    source: Literal["documents", "recording", "notes"] | None = None

class Procedure(JsonModel):
    title: str = ""
    plain_name: str = ""
    why: str = ""
    what_to_expect: str = ""
    timeframe: str = ""
    importance: Literal["high", "low"] = "low"
    source: Literal["documents", "recording", "notes"] | None = None

class OtherInstruction(JsonModel):
    title: str = ""
    why: str = ""
    steps: list[str] = Field(default_factory=list)
    description: str = ""
    frequency: str = ""
    duration: str = ""
    importance: Literal["high", "low"] = "low"
    source: Literal["documents", "recording", "notes"] | None = None

class FollowUp(JsonModel):
    time_frame: str = ""
    description: str = ""

class WarningSign(JsonModel):
    symptom: str = ""
    what_it_might_mean: str = ""
    what_to_do: str = ""
    urgency: Literal["emergency", "call_doctor", "monitor", "normal_side_effect"] = "monitor"
    related_to: str = ""
    importance: Literal["high", "low"] = "low"
    source: Literal["documents", "recording", "notes"] | None = None

class GlossaryTerm(JsonModel):
    definition: str
    source: str
    imgUrl: str | None = None
    altText: str | None = None

class RawArtifacts(JsonModel):
    """Intermediate pipeline text. Part of the model and PERSISTED (locked decision)."""
    text: str
    simplified_text: str
    clarified_text: str


# ---- family base ----------------------------------------------------------
class CarePlan(VersionedModel):
    """Version-agnostic care-plan family base. Concrete versions register below."""
    doc_type: str
    version: str


# ---- concrete v1.2 --------------------------------------------------------
class CarePlanV1_2(CarePlan):
    version_value: ClassVar[str] = "1.2"

    doc_type: Literal["appointment_note"] = "appointment_note"
    version: Literal["1.2"] = "1.2"
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
    raw: RawArtifacts | None = None   # kept + saved
```

**Why `raw: RawArtifacts | None`** — the pipeline always populates it, but a re-validated saved doc
written before this migration may lack it; Optional keeps reads tolerant while new writes always set
it. (The save path no longer strips it — see §4.6.)

**LLM-schema generation for the structured fields.** The LLM's `structure_appointment_note` prompt
needs only the *structured* part of the schema — NOT `terms`/`raw` (those are added by the pipeline
after the LLM call). Provide a dedicated schema view so the prompt schema and the persisted model
cannot drift:

```python
class CarePlanV1_2StructuredLLM(JsonModel):
    """The subset of CarePlanV1_2 the LLM is asked to produce.
    Identical field types to CarePlanV1_2 minus terms/raw (added post-LLM)."""
    doc_type: Literal["appointment_note"] = "appointment_note"
    version: Literal["1.2"] = "1.2"
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
```

`json.dumps(CarePlanV1_2StructuredLLM.model_json_schema(), indent=2)` replaces the
`_STRUCTURING_SCHEMA` read from `appointment.schema.json` in `pipeline.py`.

> Maintenance note for the dev: rather than restating every field in two classes, the cleaner
> implementation is to put all structured fields on a shared mixin and have both `CarePlanV1_2`
> (adds `terms`/`raw`) and `CarePlanV1_2StructuredLLM` inherit it. Either approach is acceptable as
> long as the field set/types stay identical; TASKS.md leaves the exact factoring to the dev but
> requires a test asserting the two schemas share the structured field set.

### 4.3 Strict validation × LLM output — how `extra="forbid"` interacts

The LLM is the only untrusted producer. Three consequences, all intended:

1. **LLM emits an unknown/renamed field** (drift) → `model_validate` raises `ValidationError`. This
   is the *point* — we want drift to fail loudly, not be silently persisted. The pipeline's
   structure step must validate the LLM JSON through `CarePlanV1_2StructuredLLM.model_validate(...)`
   and treat a `ValidationError` as a step error (existing SSE error path in
   `simplify_v1_2.py:401-406`).
2. **LLM omits a field** → covered by defaults (every structured field has a default), so omission
   does not raise; this preserves today's `pipeline.py` backfill behavior **inside the model**
   instead of a separate `defaults` dict. The backfill block (`pipeline.py:239-258`) is deleted.
3. **LLM returns the right fields with wrong types** (e.g. `questions` as a string) →
   `ValidationError`. Today this silently persists garbage.

Because the prompt schema is generated from the same model, the set of fields the LLM is told to
produce is exactly the set the validator accepts — drift is structurally prevented at the source and
caught at the sink.

### 4.4 `models/grading.py` — re-express SP3 grading in Pydantic (no behavior change)

`Grading` / `GradingEntry` keep identical field names and output JSON; only the base changes to
Pydantic. `build_grading()` and `_METHOD_REASONING` are unchanged in logic. `GradingEntry`'s
hand-written `to_dict`/`from_dict` are removed (the base provides them).

```python
# backend/models/grading.py  (model portion)
from pydantic import Field
from .base import JsonModel

class GradingEntry(JsonModel):
    name: str
    target: Literal["before", "after"]
    grade: float
    grade_breakdown: dict | None = None
    reasoning: str | None = None

class Grading(JsonModel):
    entries: list[GradingEntry] = Field(default_factory=list)
    enabled: bool = True
    graded_at: str | None = None
```

`grade_breakdown: dict | None` stays a loose `dict` (its keys vary per method; it is not a strict
sub-schema). `build_grading()` constructs `GradingEntry(...)` exactly as today. `Grading()`
(no args) still yields `{"entries": [], "enabled": True, "graded_at": None}`.

### 4.5 `models/input.py` & `models/metrics.py` — Pydantic, same fields

`Input`, `InputFile`, `Metrics` become `JsonModel` subclasses with the same fields and the same
classmethod constructors (`from_text`, `from_file_uploads`, `from_doc_id`, `from_batch_dataset`,
`Metrics.start`). Hand-written `Input.from_dict` is removed (base handles nested `InputFile`).
`Metrics.step_durations_ms` stays a `dict[str, float]` and is still mutated in place by the route —
Pydantic models are mutable by default, so `metrics.step_durations_ms[...] = x` and
`metrics.saved_id = ...` keep working.

One subtlety: `InputFile.from_file_uploads` reads `werkzeug` streams; keep it as a `@classmethod`
exactly as today — Pydantic does not interfere with arbitrary classmethods.

### 4.6 `models/envelope.py` — rename to `CarePlanInternal`; persist `raw`

```python
# backend/models/envelope.py
from .base import JsonModel
from .care_plan import CarePlan
from .grading import Grading
from .input import Input
from .metrics import Metrics

class CarePlanInternal(JsonModel):
    """Internal composite of one pipeline run: care plan + run telemetry + input + grading."""
    metrics: Metrics
    input: Input
    grading: Grading
    care_plan: CarePlan            # was: simplified_care_plan: SimplifiedCarePlan

# Back-compat alias for the SP1→SP2 transition window. SP2 removes it.
SimplifyOutput = CarePlanInternal
```

**Output-key decision (`simplified_care_plan` vs `care_plan`).** The persisted/serialized JSON key
is the global `simplify → care_plan` rename, which is **SP2's** job (it touches routes, the saved
read path, and SP5's frontend). To avoid SP1 shipping a breaking output-shape change before SP2 is
ready, SP1 keeps the **serialized key as `simplified_care_plan`** by aliasing the field:

```python
    care_plan: CarePlan = Field(
        serialization_alias="simplified_care_plan",
        validation_alias=AliasChoices("care_plan", "simplified_care_plan"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
```

This makes the Python attribute `care_plan` (aligned name) while the wire JSON stays
`simplified_care_plan` (unchanged for the frontend until SP5). SP2 flips the serialization alias to
`care_plan` and updates the frontend in lockstep. **Confirm this staging in §9.**

`is_legacy_shape(data)` stays (used to distinguish old flat outputs); update its docstring to check
for the `simplified_care_plan` key (the still-current wire key).

**`raw` persistence fix.** `utils/save_output.py:_without_raw()` must be **removed** so `raw` is
saved (locked decision #4). This is technically a SP1-adjacent change to a util — flagged for the
dev in TASKS Task 7, and called out for the human in §8 because it changes what lands in Firestore.

### 4.7 `models/__init__.py` — exports

Export the new names and keep transitional aliases:

```python
from .base import JsonModel, VersionedModel
from .care_plan import CarePlan, CarePlanV1_2, CarePlanV1_2StructuredLLM
from .envelope import CarePlanInternal, SimplifyOutput, is_legacy_shape
from .grading import Grading, GradingEntry, build_grading
from .input import Input, InputFile
from .metrics import Metrics
# Transitional alias so SP2 can migrate gradually:
SimplifiedCarePlan = CarePlanV1_2  # NOTE: was a generic dict-wrapper; now the v1.2 model
```

> ⚠️ `SimplifiedCarePlan` changes meaning: it was a `{version, data}` wrapper that accepted **any**
> version 1.0/1.1/1.2; it is now the concrete v1.2 model. Call-sites that did
> `SimplifiedCarePlan.from_pipeline_result("1.2", data)` must move to building `CarePlanV1_2`
> (see §4.8). SP2 owns route call-sites; SP1 provides the alias + the constructor helper so the
> transition is mechanical.

### 4.8 Typed layer contracts (the SP2 hand-off)

These are the precise return types each layer exposes after SP1:

| Layer | Function (current) | Returns after SP1 |
|---|---|---|
| Simplify pipeline | `V1_2Pipeline.run(text)` / route assembly | `CarePlanV1_2` |
| Grading | `build_grading(before, before_text, after, after_text)` | `Grading` |
| Input resolution | `_input_model_from_resolved(resolved)` | `Input` |
| Run telemetry | `Metrics.start(...)` | `Metrics` |
| Composite | route assembly | `CarePlanInternal` |

Construction helper to replace `SimplifiedCarePlan.from_pipeline_result`:

```python
# care_plan.py
@classmethod
def from_pipeline_result(cls, version: str, data: dict) -> "CarePlan":
    """Validate a pipeline-produced dict into the right concrete CarePlan version."""
    return CarePlan.from_dict({**data, "version": version})
```

So `CarePlan.from_pipeline_result("1.2", {**structured, "terms": ..., "raw": {...}})` returns a
validated `CarePlanV1_2`. Note this now **validates** (and will raise on drift) where the old code
blindly stored a dict — a deliberate, desirable behavior change.

Route composition target (SP2 will write this; SP1 guarantees it type-checks):

```python
internal = CarePlanInternal(
    metrics=metrics, input=input_model, grading=grading, care_plan=care_plan,
)
result = internal.to_dict()   # serialized ONCE; wire key still "simplified_care_plan"
```

## 5. API Change Summary

SP1 is deliberately **output-shape-preserving on the wire** (the rename of the JSON key is SP2):

```
POST /simplify  (v1-2)   — unchanged response keys: { metrics, input, grading, simplified_care_plan }
POST /simplify/grade     — unchanged: { grading }
GET  /simplify/saved/<id>— unchanged response keys
```

The one real, intended change in **persisted** data:

```
Firestore simplify_outputs.output_data.simplified_care_plan
  BEFORE: "raw" key STRIPPED before save (_without_raw)
  AFTER:  "raw": { text, simplified_text, clarified_text }  is SAVED
```

Before/after of a persisted care plan (abridged):

```jsonc
// BEFORE (raw stripped on save)
{ "simplified_care_plan": { "version":"1.2", "doc_type":"appointment_note",
    "summary":"...", "terms": {...} } }            // no "raw"

// AFTER
{ "simplified_care_plan": { "version":"1.2", "doc_type":"appointment_note",
    "summary":"...", "terms": {...},
    "raw": { "text":"...", "simplified_text":"...", "clarified_text":"..." } } }
```

Behavioral change (not a shape change): an LLM structure-step response that contains an unknown
field, or a wrong-typed field, now returns the existing SSE `{"step":"error", ...}` instead of
silently persisting bad data.

## 6. Frontend Change Summary

**No frontend changes are required by SP1** — the wire shape is preserved (key stays
`simplified_care_plan`, all field names identical). SP5 owns the eventual `care_plan` key rename and
can also drop `before_score?`/`after_score?` from `AppointmentNote` (those already moved into
`Grading` under SP3; they are vestigial in `simplify.ts:103-104`).

Note for SP5: `frontend/src/types/envelope.ts` already mirrors the envelope and is forward-compatible
with these models. When SP2 flips the serialization alias to `care_plan`, SP5 renames
`SimplifyOutput.simplified_care_plan → care_plan` and (optionally) `SimplifyOutput → CarePlanInternal`.

## 7. Testing

SP1 authors specs; SP6 wires them into CI. Per-model `pytest` specs:

- **base / VersionedModel**
  - `JsonModel(extra="forbid")`: constructing any model with an unknown kwarg raises
    `ValidationError`.
  - Version dispatch: `CarePlan.from_dict({"version":"1.2", ...})` returns a `CarePlanV1_2`.
  - Unknown version: `CarePlan.from_dict({"version":"9.9"})` raises `ValueError` listing available
    versions.
  - Missing version: `CarePlan.from_dict({...no version...})` raises `ValueError`.
- **CarePlanV1_2**
  - Round-trip: `CarePlanV1_2.model_validate(d).model_dump(mode="json") == d` for a full fixture
    (the real v1.2 sample output, including `terms` + `raw`).
  - Strict reject: a fixture with an extra top-level key (`"foo": 1`) raises `ValidationError`.
  - Strict reject nested: an extra key inside `medications[0]` raises `ValidationError`.
  - Defaults: validating a minimal `{"version":"1.2","doc_type":"appointment_note"}` fills all list
    fields with `[]`, `diagnosis` with its default, `raw=None`.
  - `raw` survives round-trip (present in `model_dump`).
  - Schema generation: `CarePlanV1_2StructuredLLM.model_json_schema()` is a dict; its `properties`
    set equals the structured field set of `CarePlanV1_2` minus `{terms, raw}`.
- **Grading / GradingEntry**
  - Round-trip equals SP3's expected JSON (`{entries, enabled, graded_at}`); `Grading()` →
    `{"entries": [], "enabled": True, "graded_at": None}`.
  - `build_grading(before, before_text, after, after_text)` still yields 14 entries (unchanged from
    SP3) — guards that the Pydantic migration didn't alter behavior.
- **Input / InputFile / Metrics**
  - Round-trip with nested `InputFile` list.
  - `Input.from_text/from_doc_id/from_file_uploads` produce the same dicts as today.
  - `Metrics.start(...)` then mutate `step_durations_ms`/`saved_id` then `to_dict()` reflects
    mutations (mutability preserved).
- **CarePlanInternal**
  - Round-trip; serialized JSON has the key `simplified_care_plan` (alias), not `care_plan`.
  - Validation accepts both `care_plan=` and `simplified_care_plan=` input (AliasChoices).
- **Read-path back-compat (critical)**
  - A legacy persisted doc that has the flat care plan **without `raw`** still
    `model_validate`s (because `raw` is Optional) — proves old saved docs don't break the read path.
  - A legacy doc whose care plan contains a now-removed/extra field (if any historical drift exists)
    is handled per the §9 decision (lenient read vs strict) — test both the chosen behavior.

## 8. Manual Intervention Required From You

1. **Pin Pydantic in `backend/requirements.txt`** (`pydantic>=2.7,<3`). It is currently only a
   transitive dependency; do not let the migration rely on that. (Dependency-contract change → human.)
2. **Approve removing `_without_raw()` from `utils/save_output.py`** so `raw` is persisted. This
   changes what lands in Firestore (slightly larger docs; includes the original source text). Confirm
   there is no PHI/retention policy that requires stripping the original `raw.text` before storage —
   if there is, we keep `_without_raw` and the saved-id re-grade path stays broken / must use a
   different source. **This is the single most important confirmation in SP1.**
3. **Decide the migration strategy for already-persisted Firestore docs** in the old flat shape
   (see §9). Default plan: **no migration; tolerant reads** (Optional `raw`, lenient legacy read
   path). If you want a one-time backfill (e.g. to make old docs re-gradable, which needs `raw`),
   that is a separate manual script — out of SP1's automated scope; SP1 will provide the spec only
   if you ask.
4. **Confirm the staged-rename approach** in §4.6/§9: SP1 keeps the wire key `simplified_care_plan`
   (only the Python attribute becomes `care_plan`), and SP2 flips the wire key + frontend together.
   If you'd rather rename the wire key now, SP1 and SP5 must land together — say so and we re-plan.

## 9. Open Questions

1. **Migration of already-persisted outputs (old flat shape).** Historical `simplify_outputs` docs
   were saved by the old code (e.g. `simplified_care_plan` is a flat dict, **no `raw`**, and may
   predate the envelope entirely — `is_legacy_shape` exists precisely for pre-envelope docs). When
   we add `extra="forbid"`, do we *ever* run these old docs through the new validators on read? Two
   options:
   - **(A) Tolerant reads (recommended):** `GET /simplify/saved/<id>` returns `output_data` as a raw
     dict (it does today — `saved_outputs.py:90`), **never** re-validating through the model. Old
     docs render as-is; only *new* writes are validated. Lowest risk, zero migration. The only place
     that re-reads a saved care plan into logic is the re-grade endpoint, which only touches
     `raw.text`/`raw.clarified_text` — and old docs lack `raw`, so re-grade of an old doc already
     returns the "No source text found" 400 (`grading.py:60-61`). That is acceptable (old docs were
     never re-gradable). **Need your confirmation that tolerant reads are acceptable.**
   - **(B) Validate-on-read with a legacy fallback:** wrap reads in `model_validate`, and on
     `ValidationError` fall back to returning the raw dict. More code, marginal benefit. Not
     recommended.
   My recommendation: **(A)**. Flagged in §8.3 as a human decision.

2. **Strictness of `terms` and `raw`.** `terms` is a `dict[str, GlossaryTerm]` with strict
   `GlossaryTerm` — but `terms` is built by our own deterministic code
   (`build_glossary_from_simplified_text`), not the LLM, so strictness is safe. `raw` is also
   ours. Both are strict. Confirm no third party writes extra keys into either.

3. **Is `before_score`/`after_score` truly gone from the care plan?** SP3 moved scores into
   `Grading`; the pipeline no longer injects them into the care-plan dict (`pipeline.py` keeps them
   only in its standalone `run()` return, which the v1-2 *route* does not use —
   `simplify_v1_2.py:423-431` builds the care plan without scores). So `CarePlanV1_2` correctly has
   no score fields. Confirm no other caller expects scores nested under the care plan. (Frontend
   still declares vestigial `before_score?`/`after_score?` — harmless, SP5 cleans up.)

4. **`grade_breakdown` typing.** Left as loose `dict | None` because its shape varies per scoring
   method (SP3 design). If we later want strict per-method breakdown models, that's an additive SP
   — out of scope now. Confirm loose dict is acceptable for the strict-everywhere goal (it is the
   one intentional escape hatch).

5. **`pipeline.py.run()` vs route assembly divergence.** The standalone `V1_2Pipeline.run()` returns
   a dict still containing `before_score`/`after_score` and is **not** the path the route uses
   (the route inlines the steps). SP1 models the *route's* output. Should `run()` be brought in line
   (return `CarePlanV1_2`) now, or left for SP2/SP3 dead-code cleanup? Recommendation: leave it;
   note it as dead/secondary so SP3 can remove or align it. Flag for SP2/SP3.
