# Tasks: Pydantic Model Migration (SP1)

Read `PRD.md` in this folder first. This is the foundation sub-project; land it before SP2–SP6.

**Ground rules for the dev agent:**
- Pydantic v2 only. Every model subclasses `JsonModel` (which sets `extra="forbid"`).
- Do **not** rename routes or blueprints — that is SP2. **DO** flip the inner envelope/wire key to
  `care_plan` (cross-cutting key decision; see PRD §4.6/§5). There is **no `simplified_care_plan`
  alias** and no staged rename.
- Do **not** touch the `v1`/`v1_1` pipelines or routes' logic — that is SP2/SP3. The only exception
  is mechanical import/call-site swaps needed to keep them resolving once the old aliases are gone
  (Task 10), since SP1 ships **no** `SimplifyOutput`/`SimplifiedCarePlan` aliases.
- Keep `to_dict()` / `from_dict()` working everywhere they are called today (the base provides them).
- Nothing is in production: breaking changes are fine, and we keep **no** transitional shims, dead
  code, or migration/legacy-handling code.
- After each task, run the file's own tests (Task 9) for that model before moving on.

---

### Task 1 — Rewrite `models/base.py` as Pydantic base + version mixin

**File:** `backend/models/base.py` (full rewrite)

Replace the dataclass `JsonModel` / `VersionedJsonModel` with the Pydantic `JsonModel` and
`VersionedModel` exactly per PRD.md §4.1. Specifics:

- `JsonModel(BaseModel)` with `model_config = ConfigDict(extra="forbid")`.
- `to_dict(self) -> dict` returns `self.model_dump(mode="json")` (mode="json" so
  datetimes/enums become JSON-native for Firestore).
- `from_dict(cls, data)` returns `cls.model_validate(data)`.
- `VersionedModel(JsonModel)` with `version: str`, a `_registry: ClassVar[dict]`, a
  `version_value: ClassVar[str | None] = None`, the `__init_subclass__` self-registration logic
  (fresh registry for direct family bases; auto-register concrete subclasses that set
  `version_value`), and the dispatching `from_dict`.

Delete `VersionedJsonModel`, the `register()` decorator, and the `_is_registered` flag.

**Acceptance criteria:**
- `JsonModel` subclass with an extra kwarg raises `pydantic.ValidationError`.
- `VersionedModel.from_dict` dispatches on `version`; missing/unknown version raises `ValueError`.
- `import models.base` succeeds with no remaining `dataclasses`/`typing.get_type_hints` references.

**Depends on:** none (do this first).

---

### Task 2 — `models/care_plan.py`: CarePlan framework + v1.2 model

**File:** `backend/models/care_plan.py` (full rewrite)

Implement, exactly per PRD.md §4.2:
1. All strict sub-models: `ReasonForVisit`, `DiagnosisDetail`, `Diagnosis`, `Medication`, `Test`,
   `Procedure`, `OtherInstruction`, `FollowUp`, `WarningSign`, `GlossaryTerm`, `RawArtifacts`.
   Every field has a default (matching `pipeline.py`'s backfill) except `RawArtifacts`/`GlossaryTerm`
   required fields and the `Literal` defaults shown in the PRD.
2. `CarePlan(VersionedModel)` family base with `doc_type: str` and `version: str`.
3. Module-level constant `CARE_PLAN_VERSION = "1.2"` in `models/care_plan.py` (PRD §4.2, §9.8). Then
   `CarePlanV1_2(CarePlan)` with `version_value = CARE_PLAN_VERSION`, `doc_type: Literal["care_plan"] =
   "care_plan"`, `version: Literal["1.2"] = CARE_PLAN_VERSION`, all structured fields + `terms` +
   `raw: RawArtifacts | None = None`.
4. `CarePlanV1_2StructuredLLM(JsonModel)` — the LLM-facing subset (structured fields only, NO
   `terms`/`raw`). You may factor the shared structured fields into a mixin both classes inherit;
   if you do, the field set/types must stay identical. (See PRD.md §4.2 maintenance note.)
5. `CarePlan.from_pipeline_result(cls, version, data)` classmethod per PRD.md §4.8 — merges
   `version` into `data` and dispatches via `CarePlan.from_dict` (this VALIDATES, raising on drift).

Field-source crosscheck (use all three, they agree): `appointment.schema.json`,
`pipeline.py` defaults block (lines ~239-258), `frontend/src/types/simplify.ts` `AppointmentNote`.
Include `source: "documents"|"recording"|"notes"` (Optional) on `Medication`/`Test`/`Procedure`/
`OtherInstruction`/`WarningSign` — it's in the JSON schema and frontend even though the pipeline
defaults omit it.

**Acceptance criteria:**
- `CarePlanV1_2.model_validate(full_v12_fixture)` round-trips: `.model_dump(mode="json")` equals the
  fixture (build the fixture from a real v1.2 output incl. `terms` + `raw`).
- Extra top-level key or extra nested key (e.g. in `medications[0]`) raises `ValidationError`.
- Minimal `{"version":"1.2","doc_type":"care_plan"}` validates; lists default to `[]`,
  `diagnosis` to its default, `raw` to `None`. A dict with `doc_type:"appointment_note"` now raises
  `ValidationError` (doc_type is `Literal["care_plan"]`).
- `CarePlan.from_dict({"version":"1.2", **structured})` returns a `CarePlanV1_2` instance.
- `CarePlanV1_2StructuredLLM.model_json_schema()` returns a dict whose `properties` keys equal the
  structured field set of `CarePlanV1_2` minus `{"terms","raw"}`.

**Depends on:** Task 1.

---

### Task 3 — `models/grading.py`: re-express in Pydantic (no behavior change)

**File:** `backend/models/grading.py` (edit model classes; keep `build_grading` + `_METHOD_REASONING`)

Grades stay a **LIST of entries** (`entries: list[GradingEntry]`), expandable as more grading types
are added. Each entry is a **typed shell** (fields constant across grading types) wrapping an
**OPEN/flexible** `grade_breakdown` whose inner keys vary per grading type. Per PRD.md §4.4:

- Add module-level constant `GRADING_VERSION = "1.0"` in `models/grading.py` (PRD §4.4, §9.8) —
  imported by SP4 for the `grading_version` log dimension.
- Convert `GradingEntry` and `Grading` to `JsonModel` subclasses.
- `GradingEntry` typed-shell fields: `name: str`, `target: Literal["before","after"]`,
  `grade: float`, and a new optional `description: str | None = None` (a per-grade human-readable
  note that may stay unset). Open/flexible fields: `grade_breakdown: dict | None = None`,
  `reasoning: str | None = None`. `grade_breakdown` is the **one intentional escape hatch** from
  `extra="forbid"` — do NOT model it as a strict sub-schema.
- `Grading`: `entries: list[GradingEntry] = Field(default_factory=list)`, `enabled: bool = True`,
  `graded_at: str | None = None`.
- **Delete** the hand-written `to_dict`/`from_dict` on both classes (base provides them).
- Leave `_METHOD_REASONING` and `build_grading()` logic **unchanged** — they construct
  `GradingEntry(...)` the same way (they do not set `description`, so entries get `description=None`);
  only the base class changed.

**Acceptance criteria:**
- `Grading()` → `to_dict()` == `{"entries": [], "enabled": True, "graded_at": None}`.
- `Grading.from_dict(g.to_dict()) == g` for a populated instance.
- A `GradingEntry` round-trips with `description` set and with `description` unset (None).
- `build_grading(before, before_text, after, after_text)` still returns 14 entries with the same
  names/targets as SP3 (regression guard); each entry carries `description=None`.
- `GradingEntry` with an unknown kwarg raises `ValidationError`; `grade_breakdown` accepts arbitrary
  nested keys (open).

**Depends on:** Task 1.

---

### Task 4 — `models/input.py` & `models/metrics.py`: Pydantic, same fields

**Files:** `backend/models/input.py`, `backend/models/metrics.py`

- Module-level constant `INPUT_VERSION = "1.0"` in `models/input.py` (PRD §4.5, §9.8) — imported by
  SP4 for the `input_version` log dimension.
- `InputFile`, `Input` → `JsonModel` subclasses; same fields and defaults as today
  (`files: list[InputFile] = Field(default_factory=list)`, etc.).
- Keep all classmethod constructors: `Input.from_text`, `from_doc_id`, `from_file_uploads`,
  `from_batch_dataset` (logic unchanged — they still read werkzeug streams).
- **Delete** the hand-written `Input.from_dict` (base handles nested `InputFile` reconstruction;
  verify a dict with a `files` list of dicts validates into `InputFile` objects).
- `Metrics` → `JsonModel`; keep `Metrics.start(...)` classmethod. **Drop the `step_durations_ms`
  field** (PRD §4.5, §9.9 — SP4 emits per-step durations via the code marker instead). `Metrics`
  retains its request-level fields (e.g. `total_duration_ms`, `saved_id`, version/input metadata).
  Ensure mutability: the route still does `metrics.total_duration_ms = ...`, `metrics.saved_id = ...`
  — Pydantic models are mutable by default, so leave `model_config` as the inherited strict one
  (do NOT set `frozen=True`).

**Acceptance criteria:**
- `Input.from_dict(input.to_dict()) == input` incl. nested `InputFile`.
- `Input.from_text/from_doc_id/from_file_uploads` produce dicts identical to today's output (compare
  against a captured fixture).
- `Metrics.start(...)`, then mutate `total_duration_ms` / `saved_id`, then `to_dict()` reflects the
  mutations. `Metrics` has **no** `step_durations_ms` field (`metrics.to_dict()` does not contain that key).
- Extra kwargs on either model raise `ValidationError`.

**Depends on:** Task 1.

---

### Task 5 — `models/envelope.py`: rename to `CarePlanInternal`, flip wire key to `care_plan`

**File:** `backend/models/envelope.py` (edit)

- Define `CarePlanInternal(JsonModel)` per PRD.md §4.6 with fields `metrics: Metrics`, `input: Input`,
  `grading: Grading`, `care_plan: CarePlan`, plus the **internal-only** optional scores
  `before_score: dict | None = None` and `after_score: dict | None = None`.
- **Hard-flip the wire key to `care_plan`.** The Python attribute AND the serialized/persisted JSON
  key are both `care_plan`. There is **NO `simplified_care_plan` alias** — do NOT add
  `serialization_alias`, `validation_alias`/`AliasChoices`, or `populate_by_name`. Just:
  ```python
  from pydantic import ConfigDict
  care_plan: CarePlan
  model_config = ConfigDict(extra="forbid")   # inherited; no alias config
  ```
  `to_dict()` emits `care_plan` directly via the inherited `model_dump(mode="json")` — no `by_alias`
  override needed.
- **Do NOT** add `SimplifyOutput = CarePlanInternal`. There is no transitional alias (nothing is in
  production). Call-sites use `CarePlanInternal` directly (Task 10 swaps them).
- Keep `is_legacy_shape(data)`; update its docstring **and check** to look for the `care_plan` key.

**Acceptance criteria:**
- `CarePlanInternal(...).to_dict()` top-level keys are exactly
  `{"metrics","input","grading","care_plan","before_score","after_score"}` (scores present as `null`
  when unset; the nested `care_plan` dict contains **no** `before_score`/`after_score`).
- `CarePlanInternal.from_dict(d)` requires the `care_plan` key; a dict using `simplified_care_plan`
  is rejected (`ValidationError`) — there is no alias.
- `before_score`/`after_score` round-trip on the composite.
- `from models.envelope import SimplifyOutput` **fails** (alias intentionally removed); only
  `CarePlanInternal` is exported.
- `is_legacy_shape({"care_plan": {...}})` is False; `is_legacy_shape({})` is True.

**Depends on:** Tasks 2, 3, 4.

---

### Task 6 — `models/__init__.py`: exports (no transitional aliases)

**File:** `backend/models/__init__.py` (edit)

Export per PRD.md §4.7 — new names **only**, no transitional aliases: `JsonModel, VersionedModel,
CarePlan, CarePlanV1_2, CarePlanV1_2StructuredLLM, CarePlanInternal, is_legacy_shape, Grading,
GradingEntry, build_grading, Input, InputFile, Metrics`. Do **NOT** export `SimplifyOutput` or
`SimplifiedCarePlan` (both aliases are removed). Update `__all__` accordingly.

**Acceptance criteria:** `import models` succeeds; `from models import CarePlanV1_2, CarePlanInternal,
CarePlan, GradingEntry` all resolve; `from models import SimplifyOutput` and
`from models import SimplifiedCarePlan` both raise `ImportError` (aliases intentionally gone).

**Depends on:** Tasks 1–5.

---

### Task 7 — Stop stripping `raw` on save

**File:** `backend/utils/save_output.py` (edit)

- Remove the `_without_raw()` function and change `save_simplify_output` to persist `output_data`
  **as-is** (with `raw`). Replace `"output_data": _without_raw(output_data)` with
  `"output_data": output_data`.
- ⚠️ Per PRD.md §8.2 this is gated on human confirmation (PHI/retention). Implement it, but call it
  out in the PR description as the one change that alters persisted data.

**Acceptance criteria:** A doc saved via `save_simplify_output` has
`output_data["care_plan"]["raw"]` present (the inner key is `care_plan` after the hard flip). No
reference to `_without_raw` remains.

**Depends on:** none functionally, but land with this set.

---

### Task 8 — Generate the LLM structuring schema from Pydantic; `run()` returns the model; delete the JSON file

**File:** `backend/simplify/v1_2/pipeline.py` (edit); delete `appointment.schema.json`

1. Replace the module-level schema load:
   ```python
   _STRUCTURING_SCHEMA_PATH = Path(__file__).with_name("appointment.schema.json")
   _STRUCTURING_SCHEMA = json.dumps(json.loads(_STRUCTURING_SCHEMA_PATH.read_text(...)), indent=2)
   ```
   with:
   ```python
   from models.care_plan import CarePlanV1_2StructuredLLM
   _STRUCTURING_SCHEMA = json.dumps(CarePlanV1_2StructuredLLM.model_json_schema(), indent=2)
   ```
2. In `structure_appointment_note`, after `_generate_json(...)`, **validate** the LLM output through
   the model instead of the manual backfill block (lines ~238-261):
   ```python
   from pydantic import ValidationError
   try:
       model = CarePlanV1_2StructuredLLM.model_validate(raw)
   except ValidationError as e:
       raise ValueError(f"LLM structure output failed validation: {e}") from e
   structured = model.model_dump(mode="json")
   # doc_type/version are pinned by the model defaults/Literals; no manual forcing needed
   return structured
   ```
   Delete the `defaults = {...}` backfill dict and the two `raw[...] = ...` forced assignments — the
   model defaults + `Literal` pins cover them.
3. **`run()` returns the typed model (RESOLVED — use `pipeline.run()`).** Change
   `V1_2Pipeline.run(text)` to return a `CarePlanV1_2`, **not** a dict, built via
   `CarePlan.from_pipeline_result("1.2", {**structured, "terms": terms_glossary, "raw": {...}})`
   (this validates, raising on drift). Update the signature/return type to `CarePlanV1_2`.
   **Stop folding scores into the care plan:** remove the
   `if before_score is not None: result["before_score"] = ...` / `after_score` block
   (`pipeline.py:305-308`). `before_score`/`after_score` are internal-only and belong on
   `CarePlanInternal` (PRD §4.6), not on the care plan. If `run()`'s caller needs the scores, return
   them separately or set them on the composite — but `run()`'s care-plan return is score-free.
4. Delete `backend/simplify/v1_2/appointment.schema.json`.

> The `ValueError` raised on validation failure flows into the existing SSE error path in the route
> (`simplify_v1_2.py:401-406`), so no route change is required for error handling.

**Acceptance criteria:**
- `appointment.schema.json` no longer exists; no code references it (`grep -rn appointment.schema`
  is empty).
- `_STRUCTURING_SCHEMA` is non-empty JSON containing the structured field names.
- A unit test feeding a valid structured dict to `structure_appointment_note`'s validation logic
  passes; feeding a dict with an extra key raises `ValueError`.
- `V1_2Pipeline.run(text)` returns a `CarePlanV1_2` instance whose `model_dump()` contains **no**
  `before_score`/`after_score` keys.

**Depends on:** Task 2.

> Note: This task edits a pipeline file. Per the global rule, the dev agent does the edit; SP1's
> scope explicitly includes "generate LLM schema from Pydantic" so this belongs here, not SP2.
> SP2 still owns building the care plan in the *route* via the new model (see Task 10 note).

---

### Task 9 — Unit tests for all models (specs; SP6 wires CI)

**Files:** `backend/tests/test_models_*.py` (new; mirror existing test layout if one exists)

Implement every spec in PRD.md §7. Concretely, at minimum:
- `test_models_base.py`: extra-field reject; version dispatch; unknown/missing version errors.
- `test_models_care_plan.py`: full round-trip; strict reject (top-level + nested); defaults;
  `raw` survives; `from_pipeline_result` returns `CarePlanV1_2`; structured-LLM schema property set.
- `test_models_grading.py`: `Grading()` default dict; round-trip (incl. an entry with `description`
  set and one with it unset); `build_grading` 14-entry guard (each entry `description=None`);
  `grade_breakdown` accepts arbitrary nested keys.
- `test_models_input_metrics.py`: nested `InputFile` round-trip; constructor parity vs fixtures;
  `Metrics` mutability.
- `test_models_envelope.py`: `to_dict` emits **`care_plan`** (NOT `simplified_care_plan`); a dict
  keyed `simplified_care_plan` is **rejected** (no alias); `before_score`/`after_score` round-trip on
  the composite and are absent from the nested `care_plan`; `from models.envelope import
  SimplifyOutput` raises `ImportError`.
- `test_models_readpath_tolerance.py`: a care-plan dict **without `raw`** validates (Optional `raw`).
  Add a comment noting PRD §9-1: no migration / legacy-handling code — reads are tolerant only
  because it is free.

Build the full v1.2 fixture by capturing a real route output (or hand-write from the schema). Put it
in `backend/tests/fixtures/care_plan_v1_2.json`.

**Acceptance criteria:** All specs pass under `pytest backend/tests/test_models_*.py`.

**Depends on:** Tasks 1–6.

---

### Task 10 — Keep model-consuming routes importing/running (mechanical call-site swaps only)

**Files:** `backend/routes/simplify_v1_2.py`, `backend/routes/simplify_v1_1.py`,
`backend/routes/grading.py`, `backend/routes/batch.py`, `backend/routes/saved_outputs.py`

SP1 does **not** rewrite route logic or rename routes/blueprints (SP2 does). BUT because SP1 ships
**no** `SimplifyOutput`/`SimplifiedCarePlan` aliases and flips the key to `care_plan`, the existing
call-sites won't resolve as-is. Make only the **mechanical** swaps needed to keep them importing and
constructing correctly — no logic/behavior change:
- `simplify_v1_2.py`: `from models.care_plan import SimplifiedCarePlan` →
  `from models.care_plan import CarePlan` (and use `CarePlan.from_pipeline_result("1.2", {...})` at
  line ~423; it returns a validated `CarePlanV1_2`). Replace the `SimplifyOutput(...)` construction
  (line ~444) with `CarePlanInternal(...)`, and change the kwarg `simplified_care_plan=` →
  `care_plan=` (the only accepted key now; there is no alias). `to_dict()` then emits the
  `care_plan` wire key.
- `simplify_v1_1.py`: same mechanical swaps — `SimplifiedCarePlan` import →
  `CarePlan.from_pipeline_result("1.1", ...)`, and `SimplifyOutput(simplified_care_plan=...)` →
  `CarePlanInternal(care_plan=...)`. (v1_1 logic otherwise untouched.)
- `grading.py` / `batch.py` / `saved_outputs.py`: use only `Grading`, `Input`, `Metrics`, and raw
  dicts — confirm imports resolve; swap any `SimplifyOutput`/`SimplifiedCarePlan`/`simplified_care_plan`
  references if present.

> These are pure name/key swaps forced by removing the aliases — they are NOT the SP2 route
> rename. If `before_score`/`after_score` are available at the v1_2 call-site, pass them to
> `CarePlanInternal(before_score=..., after_score=...)`; otherwise leave them unset (default None).

**Acceptance criteria:**
- `python -c "import routes.simplify_v1_2, routes.simplify_v1_1, routes.grading, routes.batch, routes.saved_outputs"`
  succeeds.
- `grep -rn "SimplifiedCarePlan\|SimplifyOutput\|simplified_care_plan" backend/routes/` returns
  nothing (all swapped to `CarePlan`/`CarePlanInternal`/`care_plan`).
- A construction smoke test builds a `CarePlanInternal` via the exact kwargs the v1-2 route now uses
  (`care_plan=CarePlanV1_2(...)`) and `to_dict()` yields the `care_plan` key.

**Depends on:** Tasks 1–8.

---

## Summary of what requires you (not a dev agent)

1. **Pin `pydantic>=2.7,<3` in `backend/requirements.txt`** — it's currently only a transitive dep.
   (Dependency-contract change.)
2. **Approve removing `_without_raw()`** (Task 7) so `raw` (including the original source text) is
   persisted to Firestore. Confirm no PHI/retention policy forbids storing `raw.text`. **This is the
   key blocking confirmation** — if denied, Task 7 is dropped and the saved-id re-grade path stays
   non-functional for persisted docs. (`raw` kept + saved is otherwise LOCKED.)

> Previously listed here, now RESOLVED by the owner — no action needed:
> - **Read-path migration / legacy handling:** none. Nothing is in production and there is barely any
>   data; reads stay tolerant (Optional `raw`) at zero cost, with no migration runner or backfill.
> - **Wire-key rename:** decided. The inner key is hard-flipped to `care_plan` now (no
>   `simplified_care_plan` alias, no staged window); SP2 (routes) and SP5 (frontend) follow the one
>   decided key.
