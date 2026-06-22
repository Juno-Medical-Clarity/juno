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
and generates the LLM's JSON schema. Strict (`extra="forbid"`) so LLM drift fails loudly. There are
**no third-party writers** of these payloads, so strict everywhere is safe.

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
   `care_plan` + `metrics` + `input` + `grading`). Nothing is in production, so this is a hard
   rename: **no `SimplifyOutput` alias** and no transitional shim — call-sites move to
   `CarePlanInternal` directly (SP2 owns the route call-sites).
6. **Drop `appointment.schema.json`.** Pydantic becomes the single source of truth; the v1.2 pipeline
   prompt generates its schema from `CarePlanV1_2.model_json_schema()` instead of reading the file.
7. Define the **typed contract each layer returns** so SP2 can compose routes:
   simplify pipeline → `CarePlanV1_2` (`pipeline.run()` returns the typed model itself),
   grading → `Grading`, input resolution → `Input`, run telemetry → `Metrics`,
   the composite → `CarePlanInternal`.
8. Write the **per-model unit-test plan/specs** (round-trip, strict-reject, version dispatch). SP1
   only authors specs in this doc; SP6 owns the broader test reorg + CI wiring.

## 3. Non-Goals

- **Not** consolidating or renaming routes, and **not** doing the global `simplify → care_plan`
  rename across routes/blueprints — that is **SP2**. SP1 aligns *model* names
  (`SimplifyOutput → CarePlanInternal`) and **hard-flips the inner envelope/wire key to `care_plan`**
  (the cross-cutting key decision; see §4.6) — there is no alias and no staged rename.
- **Not** removing the `v1` / `v1_1` pipelines or their routes — that is **SP2/SP3**. SP1's
  `CarePlan` registry therefore only ships the **v1.2** concrete model, but the base/registry are
  version-agnostic so older/newer versions plug in.
- **Not** changing scoring math or the grading schema — SP3 (grading rework) already landed the
  `Grading`/`GradingEntry`/`build_grading` shape; SP1 only re-expresses those classes in Pydantic
  with identical field names and output JSON.
- **Not** changing the SSE protocol, the GCS/PDF flow, or auth.
- **Not** building any Firestore data-migration machinery, and **not** writing legacy-handling code.
  Per the owner directive nothing is in production and there is barely any data — old data is not a
  concern. Reads stay tolerant (Optional `raw`) only because it costs nothing, not because a
  migration path is owed (see §4.6, §9).

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
config and the canonical `to_dict`/`from_dict` helpers, plus a generic **version-dispatch mixin** that
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
    to_dict/from_dict are the project's canonical (de)serialize helpers and wrap
    model_dump(mode="json") / model_validate. They are kept because call-sites use
    them broadly, not as transitional shims.
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


# Module-level version constant — single source of truth for this model's version
# string. Imported by SP4 (the `care_plan_version` log dimension) via
# `from models.care_plan import CARE_PLAN_VERSION`.
CARE_PLAN_VERSION = "1.2"


# ---- concrete v1.2 --------------------------------------------------------
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
    raw: RawArtifacts | None = None   # kept + saved
```

**Why `raw: RawArtifacts | None`** — the pipeline always populates it; Optional simply keeps reads
tolerant at zero cost (a stray old doc without `raw` still validates) without any migration
machinery. New writes always set it. (The save path no longer strips it — see §4.6.)

**LLM-schema generation for the structured fields.** The LLM's `structure_appointment_note` prompt
needs only the *structured* part of the schema — NOT `terms`/`raw` (those are added by the pipeline
after the LLM call). Provide a dedicated schema view so the prompt schema and the persisted model
cannot drift:

```python
class CarePlanV1_2StructuredLLM(JsonModel):
    """The subset of CarePlanV1_2 the LLM is asked to produce.
    Identical field types to CarePlanV1_2 minus terms/raw (added post-LLM)."""
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

### 4.4 `models/grading.py` — re-express SP3 grading in Pydantic (typed shell + open breakdown)

Grades are modeled as a **LIST of grade entries** (`entries: list[GradingEntry]`), which is already
the shape and is intentionally expandable as more grading types are added later. Each entry is a
**common typed shell** — fields that stay constant across grading types (`name`, `target`, `grade`,
and an optional human-readable `description`) — wrapping an **OPEN/flexible `grade_breakdown`** whose
inner keys differ per grading type. `build_grading()` and `_METHOD_REASONING` are unchanged in logic.
`GradingEntry`'s hand-written `to_dict`/`from_dict` are removed (the base provides them).

```python
# backend/models/grading.py  (model portion)
from pydantic import Field
from .base import JsonModel

# Module-level version constant for the grading data model — imported by SP4
# (the `grading_version` log dimension) via `from models.grading import GRADING_VERSION`.
GRADING_VERSION = "1.0"

class GradingEntry(JsonModel):
    # ---- typed shell: constant across grading types ----
    name: str
    target: Literal["before", "after"]
    grade: float
    description: str | None = None      # optional per-grade human-readable note (varies, may be unset)
    # ---- open/flexible: shape differs per grading type ----
    grade_breakdown: dict | None = None
    reasoning: str | None = None

class Grading(JsonModel):
    entries: list[GradingEntry] = Field(default_factory=list)
    enabled: bool = True
    graded_at: str | None = None
```

`grade_breakdown: dict | None` is the **intentional open escape hatch** — its keys vary per grading
type, so it is deliberately NOT a strict sub-schema even though `extra="forbid"` governs every other
field. This is the resolved design for expanding grading types later: add fields to the typed shell
only when they are constant across types; everything type-specific lives inside `grade_breakdown`.
`build_grading()` constructs `GradingEntry(...)` exactly as today (it does not set `description`, so
existing entries get `description=None`, which is omitted/None on the wire). `Grading()` (no args)
still yields `{"entries": [], "enabled": True, "graded_at": None}`, and each entry now also carries
`description` (None by default).

### 4.5 `models/input.py` & `models/metrics.py` — Pydantic, same fields

`Input`, `InputFile`, `Metrics` become `JsonModel` subclasses with the same fields and the same
classmethod constructors (`from_text`, `from_file_uploads`, `from_doc_id`, `from_batch_dataset`,
`Metrics.start`). Hand-written `Input.from_dict` is removed (base handles nested `InputFile`).
`models/input.py` also exposes a module-level constant `INPUT_VERSION = "1.0"` — imported by SP4
(the `input_version` log dimension) via `from models.input import INPUT_VERSION`.

**`Metrics.step_durations_ms` is REMOVED** (coordinated with SP4 §9.7): per-step durations are emitted
exactly once via the SP4 code marker (the `marker_duration_ms` metric + `op_complete` timeline log),
so a parallel per-step map in the serialized `Metrics` payload would duplicate that bookkeeping. Drop
the `step_durations_ms` field from `Metrics`; the route no longer captures or assigns per-step
durations. `Metrics` keeps its request-level fields (e.g. `total_duration_ms`, `saved_id`, version/input
metadata); `metrics.saved_id = ...` still works (Pydantic models are mutable by default).

One subtlety: `InputFile.from_file_uploads` reads `werkzeug` streams; keep it as a `@classmethod`
exactly as today — Pydantic does not interfere with arbitrary classmethods.

### 4.6 `models/envelope.py` — rename to `CarePlanInternal`; flip key to `care_plan`; persist `raw`

```python
# backend/models/envelope.py
from .base import JsonModel
from .care_plan import CarePlan
from .grading import Grading
from .input import Input
from .metrics import Metrics

class CarePlanInternal(JsonModel):
    """Internal composite of one pipeline run: care plan + run telemetry + input + grading,
    plus internal-only readability scores (before/after) that are NOT part of the care plan."""
    metrics: Metrics
    input: Input
    grading: Grading
    care_plan: CarePlan                       # wire key: "care_plan" (hard flip)
    before_score: dict | None = None          # internal-only; lives here, not in CarePlan
    after_score: dict | None = None           # internal-only; lives here, not in CarePlan
```

**Output-key decision — RESOLVED: hard-flip the inner envelope/wire key to `care_plan` NOW.**
This is the cross-cutting key decision that binds SP1/SP2/SP5: the inner key for care-plan content is
`care_plan`, decided once. There is **NO `simplified_care_plan` alias**, no `AliasChoices`, no
`serialization_alias`, and no staged "keep + alias now, flip later". The Python attribute and the
serialized/persisted JSON key are both `care_plan`. The previous staged-rename plan is **overridden**.

```python
    care_plan: CarePlan
    model_config = ConfigDict(extra="forbid")   # no populate_by_name / alias needed
```

`to_dict()` emits `care_plan` directly via the inherited `model_dump(mode="json")` — no `by_alias`
handling required. SP2 (routes/saved read path) and SP5 (frontend) consume the `care_plan` key; there
is no transitional window because nothing is in production.

**`before_score`/`after_score` placement — RESOLVED.** These readability scores are run-internal and
do **not** belong on the care plan. They are kept **out of `CarePlan`/`CarePlanV1_2`** and instead
carried on `CarePlanInternal` (the internal composite). The care-plan model therefore has no score
fields; the route/pipeline sets them on `CarePlanInternal` when present.

`is_legacy_shape(data)` stays (used to distinguish old flat outputs); update its docstring to check
for the `care_plan` key.

**`raw` persistence fix (locked).** `utils/save_output.py:_without_raw()` must be **removed** so `raw`
is saved. This is a SP1-adjacent change to a util — flagged for the dev in TASKS Task 7 and called out
for the human in §8 because it changes what lands in Firestore.

### 4.7 `models/__init__.py` — exports

Export the new names only. **No transitional aliases** (no `SimplifyOutput`, no `SimplifiedCarePlan`)
— nothing is in production, breaking changes are fine, and we keep no dead shims:

```python
from .base import JsonModel, VersionedModel
from .care_plan import CarePlan, CarePlanV1_2, CarePlanV1_2StructuredLLM
from .envelope import CarePlanInternal, is_legacy_shape
from .grading import Grading, GradingEntry, build_grading
from .input import Input, InputFile
from .metrics import Metrics
```

> ⚠️ The old `SimplifiedCarePlan` `{version, data}` wrapper is **gone**, not aliased. Call-sites that
> did `SimplifiedCarePlan.from_pipeline_result("1.2", data)` move to `CarePlan.from_pipeline_result`
> (returns a validated `CarePlanV1_2`; see §4.8). Likewise `SimplifyOutput` is fully replaced by
> `CarePlanInternal`. SP2 owns updating the route call-sites; SP1 provides the real names + the
> constructor helper. Because the v1/v1_1 routes still import `SimplifiedCarePlan` today, SP1's
> Task 10 makes the **mechanical** call-site swaps required to keep imports resolving (no behavior
> change), since there is no alias to lean on.

### 4.8 Typed layer contracts (the SP2 hand-off)

These are the precise return types each layer exposes after SP1:

| Layer | Function (current) | Returns after SP1 |
|---|---|---|
| Simplify pipeline | `V1_2Pipeline.run(text)` | `CarePlanV1_2` (the model itself — RESOLVED) |
| Grading | `build_grading(before, before_text, after, after_text)` | `Grading` |
| Input resolution | `_input_model_from_resolved(resolved)` | `Input` |
| Run telemetry | `Metrics.start(...)` | `Metrics` |
| Composite | route assembly | `CarePlanInternal` |

**`pipeline.run()` — RESOLVED: use it, and it returns the model.** `V1_2Pipeline.run(text)` must
return a `CarePlanV1_2` (built via `CarePlan.from_pipeline_result("1.2", {**structured, "terms":
..., "raw": {...}})`), **not** a dict, and it must no longer fold `before_score`/`after_score` into
the care-plan dict — those scores belong on `CarePlanInternal` (§4.6). Where the final
`CarePlanInternal` composition physically lives (inside `run()` here, or in the route under SP2/SP3)
is the implementer's call, but the contract is fixed: `run()` returns the typed `CarePlanV1_2`. This
removes the prior "route inlines the steps; `run()` is dead/secondary" divergence — `run()` is the
path, and it is typed.

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
    before_score=before_score, after_score=after_score,   # internal-only, optional
)
result = internal.to_dict()   # serialized ONCE; wire key is "care_plan"
```

## 5. API Change Summary

SP1 **flips the inner care-plan key on the wire** (the cross-cutting key decision; nothing is in
production so this is a hard, immediate change). The envelope key becomes `care_plan`:

```
POST /simplify  (v1-2)   — response keys: { metrics, input, grading, care_plan }   (was simplified_care_plan)
POST /simplify/grade     — unchanged: { grading }
GET  /simplify/saved/<id>— response keys flip simplified_care_plan -> care_plan
```

> SP2 owns the route/blueprint `simplify → care_plan` rename and SP5 owns the frontend read of the
> `care_plan` key. SP1 lands the model + envelope that emit `care_plan`; SP2/SP5 follow. There is no
> alias bridging the two windows — they coordinate on the single decided key.

Two real, intended changes in **persisted** data:

```
Firestore simplify_outputs.output_data
  KEY:  simplified_care_plan  ->  care_plan   (hard flip, no alias)
  raw:  BEFORE STRIPPED before save (_without_raw)  ->  AFTER SAVED
```

Before/after of a persisted output (abridged):

```jsonc
// BEFORE (old key + raw stripped on save)
{ "simplified_care_plan": { "version":"1.2", "doc_type":"appointment_note",
    "summary":"...", "terms": {...} } }            // no "raw"

// AFTER (new key + new doc_type + raw saved)
{ "care_plan": { "version":"1.2", "doc_type":"care_plan",
    "summary":"...", "terms": {...},
    "raw": { "text":"...", "simplified_text":"...", "clarified_text":"..." } } }
```

Behavioral change (not a shape change): an LLM structure-step response that contains an unknown
field, or a wrong-typed field, now returns the existing SSE `{"step":"error", ...}` instead of
silently persisting bad data.

## 6. Frontend Change Summary

SP1 itself edits no frontend files, but because the inner key is **hard-flipped to `care_plan`**, the
frontend must consume `care_plan` in lockstep — this is the SP1/SP2/SP5 cross-cutting key decision,
not a staged rename. SP5 owns the frontend changes:
- rename `SimplifyOutput.simplified_care_plan → care_plan` (and optionally `SimplifyOutput →
  CarePlanInternal`) in `frontend/src/types/envelope.ts` / `simplify.ts`;
- update the one reader at `frontend/src/components/OutputGradingCard.tsx` (`output.simplified_care_plan.raw?.text`)
  to `output.care_plan.raw?.text`;
- drop the vestigial `before_score?`/`after_score?` on `AppointmentNote` (`simplify.ts:103-104`) —
  those scores moved into `Grading` under SP3 and (where still surfaced) live on `CarePlanInternal`,
  never on the care plan.

There is no transitional window or alias: SP2 (backend routes) and SP5 (frontend) land the single
`care_plan` key together.

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
  - Defaults: validating a minimal `{"version":"1.2","doc_type":"care_plan"}` fills all list
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
  - `Metrics.start(...)` then mutate `total_duration_ms`/`saved_id` then `to_dict()` reflects
    mutations (mutability preserved). `to_dict()` has **no** `step_durations_ms` key (field removed, §4.5).
- **CarePlanInternal**
  - Round-trip; serialized JSON has the key **`care_plan`** (no `simplified_care_plan` alias exists).
  - `before_score`/`after_score` are accepted and round-trip on `CarePlanInternal`, and are **absent**
    from the nested `care_plan` dict (scores live on the composite, not the care plan).
- **Read-path tolerance (cheap, not a migration)**
  - A persisted care plan **without `raw`** still `model_validate`s (because `raw` is Optional) — the
    read path tolerates a stray old doc at zero cost. No migration machinery is tested or required;
    per the owner directive old data is not a concern.

## 8. Manual Intervention Required From You

1. **Pin Pydantic in `backend/requirements.txt`** (`pydantic>=2.7,<3`). It is currently only a
   transitive dependency; do not let the migration rely on that. (Dependency-contract change → human.)
2. **Approve removing `_without_raw()` from `utils/save_output.py`** so `raw` is persisted. (LOCKED:
   `raw` is kept and saved.) This changes what lands in Firestore (slightly larger docs; includes the
   original source text). Confirm there is no PHI/retention policy that requires stripping
   `raw.text` before storage. **This is the single most important confirmation in SP1.**

> Previously-manual items now RESOLVED by the owner, no longer requiring you:
> - **Firestore data migration / legacy handling:** none. Nothing is in production and there is
>   barely any data; old data is not a concern. Reads stay tolerant (Optional `raw`) at zero cost —
>   no migration runner, no backfill, no legacy-fallback code. (was §8.3)
> - **Staged `simplified_care_plan → care_plan` rename:** overridden. The inner key is hard-flipped
>   to `care_plan` now, with no alias and no staged window; SP2 (routes) and SP5 (frontend) follow
>   the single decided key. (was §8.4)

## 9. Open Questions & Decisions

1. **Migration of already-persisted outputs (old flat shape).**
   `[RESOLVED: No migration, no legacy-handling code. Nothing is in production and there is barely any
   data — old data is not a concern. Reads stay tolerant only because it is free: GET
   /simplify/saved/<id> returns output_data as a raw dict (saved_outputs.py:90) and never
   re-validates, and raw is Optional so a stray old doc validates if it ever is run through a model.
   No validate-on-read fallback, no backfill runner, no is_legacy_shape-driven migration path.]`

2. **Strictness of `terms` and `raw`.**
   `[RESOLVED: Strict (extra="forbid") is fine. There are NO third-party writers of these payloads —
   terms is built by our deterministic build_glossary_from_simplified_text and raw is set by the
   pipeline. raw is kept AND saved (locked). GlossaryTerm and RawArtifacts stay strict.]`

3. **`before_score`/`after_score` placement.**
   `[RESOLVED: These live on the INTERNAL composite model CarePlanInternal, NOT on CarePlan/
   CarePlanV1_2. The public/care-plan model has no score fields. See §4.6 — before_score/after_score
   are optional fields on CarePlanInternal; the pipeline/route sets them there when present. The
   frontend's vestigial before_score?/after_score? on AppointmentNote are dropped by SP5.]`

4. **`grade_breakdown` typing.**
   `[RESOLVED: Grades are a LIST of entries (list[GradingEntry]), expandable as more grading types
   are added. Each entry is a common typed shell — fields constant across grading types (name,
   target, grade, and an optional description) — wrapping an OPEN/flexible grade_breakdown: dict |
   None whose inner keys differ per grading type. grade_breakdown is the one intentional escape hatch
   from extra="forbid". Future grading types add fields to the typed shell ONLY when constant across
   types; everything type-specific goes inside grade_breakdown. See §4.4.]`

5. **`pipeline.py.run()` vs route assembly.**
   `[RESOLVED: USE pipeline.run(), and run() returns the typed model itself (CarePlanV1_2), not a
   dict. run() must stop folding before_score/after_score into the care plan — those go on
   CarePlanInternal (§4.6). Where the final CarePlanInternal composition physically lives (in run()
   here vs the route under SP2/SP3) is the implementer's call, but the contract is fixed: run()
   returns CarePlanV1_2. The old "route inlines steps; run() is dead/secondary" divergence is
   eliminated. See §4.8.]`

6. **Inner envelope/wire key for care-plan content (cross-cutting SP1/SP2/SP5).**
   `[RESOLVED: Hard-flip to care_plan NOW. One decided key — no simplified_care_plan alias, no
   AliasChoices/serialization_alias, no staged "keep + alias now, flip later". The Python attribute
   and the serialized/persisted JSON key are both care_plan. SP2 (routes/saved read path) and SP5
   (frontend) consume care_plan in lockstep; no transitional window. This overrides any earlier
   staged-rename language in this PRD. See §4.6, §5, §6.]`

7. **`doc_type` value (cross-cutting with SP5).**
   `[RESOLVED (2026-06-20): doc_type changes from "appointment_note" to "care_plan" everywhere. The
   backend model is the source of truth: CarePlanV1_2 and CarePlanV1_2StructuredLLM both pin
   doc_type: Literal["care_plan"] = "care_plan", so the LLM is asked to produce (and the model
   validates) doc_type="care_plan". SP5 matches the frontend literal in the same lockstep release.
   See §4.2.]`

8. **Module-level version constants for observability (cross-cutting with SP4).**
   `[RESOLVED (2026-06-20): models expose module-level version constants as the single source of truth
   for SP4's log dimensions — CARE_PLAN_VERSION = "1.2" (models/care_plan.py, used as the
   CarePlanV1_2.version default and version_value), GRADING_VERSION = "1.0" (models/grading.py),
   INPUT_VERSION = "1.0" (models/input.py). SP4 imports these via the root path
   (from models.care_plan import CARE_PLAN_VERSION, etc.) and stamps g.care_plan_version /
   g.grading_version / g.input_version. See §4.2, §4.4, §4.5.]`

9. **`Metrics.step_durations_ms` (cross-cutting with SP4).**
   `[RESOLVED (2026-06-20): REMOVED from the Metrics model. Per-step durations are emitted exactly
   once by SP4's code marker (marker_duration_ms metric + op_complete timeline log); duplicating them
   in the serialized Metrics payload is the bookkeeping SP4 deletes. The route no longer captures or
   assigns per-step durations. Metrics keeps total_duration_ms / saved_id / version+input metadata.
   See §4.5 and SP4 §9.7.]`
