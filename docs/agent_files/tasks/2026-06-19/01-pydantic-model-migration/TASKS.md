# Tasks: Pydantic Model Migration (SP1)

Read `PRD.md` in this folder first. This is the foundation sub-project; land it before SP2–SP6.

**Ground rules for the dev agent:**
- Pydantic v2 only. Every model subclasses `JsonModel` (which sets `extra="forbid"`).
- Do **not** rename routes, blueprints, or the wire JSON key `simplified_care_plan` — that is SP2.
- Do **not** touch the `v1`/`v1_1` pipelines or routes — that is SP2/SP3.
- Keep `to_dict()` / `from_dict()` working everywhere they are called today (the base provides them).
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
3. `CarePlanV1_2(CarePlan)` with `version_value = "1.2"` and all structured fields + `terms` +
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
- Minimal `{"version":"1.2","doc_type":"appointment_note"}` validates; lists default to `[]`,
  `diagnosis` to its default, `raw` to `None`.
- `CarePlan.from_dict({"version":"1.2", **structured})` returns a `CarePlanV1_2` instance.
- `CarePlanV1_2StructuredLLM.model_json_schema()` returns a dict whose `properties` keys equal the
  structured field set of `CarePlanV1_2` minus `{"terms","raw"}`.

**Depends on:** Task 1.

---

### Task 3 — `models/grading.py`: re-express in Pydantic (no behavior change)

**File:** `backend/models/grading.py` (edit model classes; keep `build_grading` + `_METHOD_REASONING`)

- Convert `GradingEntry` and `Grading` to `JsonModel` subclasses exactly per PRD.md §4.4.
- `target: Literal["before","after"]`, `grade_breakdown: dict | None = None`,
  `entries: list[GradingEntry] = Field(default_factory=list)`.
- **Delete** the hand-written `to_dict`/`from_dict` on both classes (base provides them).
- Leave `_METHOD_REASONING` and `build_grading()` logic **unchanged** — they construct
  `GradingEntry(...)` the same way; only the base class changed.

**Acceptance criteria:**
- `Grading()` → `to_dict()` == `{"entries": [], "enabled": True, "graded_at": None}`.
- `Grading.from_dict(g.to_dict()) == g` for a populated instance.
- `build_grading(before, before_text, after, after_text)` still returns 14 entries with the same
  names/targets as SP3 (regression guard).
- `GradingEntry` with an unknown kwarg raises `ValidationError`.

**Depends on:** Task 1.

---

### Task 4 — `models/input.py` & `models/metrics.py`: Pydantic, same fields

**Files:** `backend/models/input.py`, `backend/models/metrics.py`

- `InputFile`, `Input` → `JsonModel` subclasses; same fields and defaults as today
  (`files: list[InputFile] = Field(default_factory=list)`, etc.).
- Keep all classmethod constructors: `Input.from_text`, `from_doc_id`, `from_file_uploads`,
  `from_batch_dataset` (logic unchanged — they still read werkzeug streams).
- **Delete** the hand-written `Input.from_dict` (base handles nested `InputFile` reconstruction;
  verify a dict with a `files` list of dicts validates into `InputFile` objects).
- `Metrics` → `JsonModel`; keep `Metrics.start(...)` classmethod. Ensure mutability: the route does
  `metrics.step_durations_ms[k] = v`, `metrics.total_duration_ms = ...`, `metrics.saved_id = ...` —
  Pydantic models are mutable by default, so leave `model_config` as the inherited strict one
  (do NOT set `frozen=True`).

**Acceptance criteria:**
- `Input.from_dict(input.to_dict()) == input` incl. nested `InputFile`.
- `Input.from_text/from_doc_id/from_file_uploads` produce dicts identical to today's output (compare
  against a captured fixture).
- `Metrics.start(...)`, then mutate the three fields, then `to_dict()` reflects the mutations.
- Extra kwargs on either model raise `ValidationError`.

**Depends on:** Task 1.

---

### Task 5 — `models/envelope.py`: rename to `CarePlanInternal`, alias the wire key

**File:** `backend/models/envelope.py` (edit)

- Define `CarePlanInternal(JsonModel)` with fields `metrics: Metrics`, `input: Input`,
  `grading: Grading`, and `care_plan: CarePlan` per PRD.md §4.6.
- Apply the field aliases so the **wire key stays `simplified_care_plan`** while the Python
  attribute is `care_plan`:
  ```python
  from pydantic import Field, AliasChoices, ConfigDict
  care_plan: CarePlan = Field(
      serialization_alias="simplified_care_plan",
      validation_alias=AliasChoices("care_plan", "simplified_care_plan"),
  )
  model_config = ConfigDict(extra="forbid", populate_by_name=True)
  ```
  `to_dict()` must therefore emit `simplified_care_plan` (use `model_dump(mode="json", by_alias=True)`
  — override `to_dict` on this model to pass `by_alias=True`, or set it as the default).
- Add `SimplifyOutput = CarePlanInternal` (back-compat alias for SP2 transition).
- Keep `is_legacy_shape(data)`; update its docstring (still checks for `simplified_care_plan` key).

⚠️ Because the wire key must remain `simplified_care_plan`, make sure `CarePlanInternal.to_dict()`
serializes with `by_alias=True`. Add a focused test (Task 9) asserting the output key.

**Acceptance criteria:**
- `CarePlanInternal(...).to_dict()` has top-level keys exactly
  `{"metrics","input","grading","simplified_care_plan"}`.
- `CarePlanInternal.from_dict(d)` accepts either `care_plan` or `simplified_care_plan` in `d`.
- `from models.envelope import SimplifyOutput` still works and is `CarePlanInternal`.

**Depends on:** Tasks 2, 3, 4.

---

### Task 6 — `models/__init__.py`: exports + transitional aliases

**File:** `backend/models/__init__.py` (edit)

Export per PRD.md §4.7: `JsonModel, VersionedModel, CarePlan, CarePlanV1_2,
CarePlanV1_2StructuredLLM, CarePlanInternal, SimplifyOutput, is_legacy_shape, Grading, GradingEntry,
build_grading, Input, InputFile, Metrics`, plus the transitional alias
`SimplifiedCarePlan = CarePlanV1_2`. Update `__all__` accordingly.

**Acceptance criteria:** `import models` succeeds; `from models import SimplifyOutput,
SimplifiedCarePlan, CarePlanV1_2, CarePlanInternal` all resolve; `SimplifyOutput is CarePlanInternal`
and `SimplifiedCarePlan is CarePlanV1_2`.

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
`output_data["simplified_care_plan"]["raw"]` present. No reference to `_without_raw` remains.

**Depends on:** none functionally, but land with this set.

---

### Task 8 — Generate the LLM structuring schema from Pydantic; delete the JSON file

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
3. Delete `backend/simplify/v1_2/appointment.schema.json`.

> The `ValueError` raised on validation failure flows into the existing SSE error path in the route
> (`simplify_v1_2.py:401-406`), so no route change is required for error handling.

**Acceptance criteria:**
- `appointment.schema.json` no longer exists; no code references it (`grep -rn appointment.schema`
  is empty).
- `_STRUCTURING_SCHEMA` is non-empty JSON containing the structured field names.
- A unit test feeding a valid structured dict to `structure_appointment_note`'s validation logic
  passes; feeding a dict with an extra key raises `ValueError`.

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
- `test_models_grading.py`: `Grading()` default dict; round-trip; `build_grading` 14-entry guard.
- `test_models_input_metrics.py`: nested `InputFile` round-trip; constructor parity vs fixtures;
  `Metrics` mutability.
- `test_models_envelope.py`: `to_dict` emits `simplified_care_plan`; AliasChoices accepts both;
  `SimplifyOutput is CarePlanInternal`.
- `test_models_readpath_backcompat.py`: a legacy care-plan dict **without `raw`** validates
  (Optional `raw`); document the §9-(A) tolerant-read decision in a comment.

Build the full v1.2 fixture by capturing a real route output (or hand-write from the schema). Put it
in `backend/tests/fixtures/care_plan_v1_2.json`.

**Acceptance criteria:** All specs pass under `pytest backend/tests/test_models_*.py`.

**Depends on:** Tasks 1–6.

---

### Task 10 — Compile/smoke check the model-consuming routes (no functional rename)

**Files (read/verify, minimal edits only):** `backend/routes/simplify_v1_2.py`,
`backend/routes/grading.py`, `backend/routes/batch.py`, `backend/routes/saved_outputs.py`

SP1 does **not** rewrite these routes (SP2 does). But after the model changes they must still
import and run. Verify and make only the **mechanical** fixes needed to keep them working:
- `simplify_v1_2.py` constructs `SimplifiedCarePlan.from_pipeline_result("1.2", {...})`
  (line ~423) and `SimplifyOutput(...)` with `simplified_care_plan=...` (line ~444). With the
  transitional aliases (`SimplifiedCarePlan = CarePlanV1_2`, `SimplifyOutput = CarePlanInternal`,
  and `CarePlanInternal` accepting `simplified_care_plan=` via AliasChoices/`populate_by_name`),
  these should keep working **unchanged**. Confirm by import + a unit construction test. If
  `SimplifiedCarePlan.from_pipeline_result` is called on the alias (now `CarePlanV1_2`), ensure
  `CarePlanV1_2.from_pipeline_result` resolves — it's inherited from `CarePlan`; verify it returns a
  `CarePlanV1_2`. If anything doesn't resolve, fix the **alias/export**, not the route.
- `grading.py` / `batch.py` / `saved_outputs.py` only use `Grading`, `Input`, `Metrics`, and raw
  dicts — should be unaffected. Confirm imports resolve.

⚠️ Do NOT rename `simplified_care_plan=` kwargs or wire keys in routes here. That's SP2.

**Acceptance criteria:**
- `python -c "import routes.simplify_v1_2, routes.grading, routes.batch, routes.saved_outputs"`
  succeeds.
- A construction smoke test builds a `CarePlanInternal` via the exact kwargs the v1-2 route uses
  (`simplified_care_plan=CarePlanV1_2(...)`) and `to_dict()` yields the `simplified_care_plan` key.

**Depends on:** Tasks 1–8.

---

## Summary of what requires you (not a dev agent)

1. **Pin `pydantic>=2.7,<3` in `backend/requirements.txt`** — it's currently only a transitive dep.
   (Dependency-contract change.)
2. **Approve removing `_without_raw()`** (Task 7) so `raw` (including the original source text) is
   persisted to Firestore. Confirm no PHI/retention policy forbids storing `raw.text`. **This is the
   key blocking confirmation** — if denied, Task 7 is dropped and the saved-id re-grade path stays
   non-functional for persisted docs.
3. **Confirm the read-path migration strategy** for already-saved (old flat / no-`raw`) Firestore
   docs: default is **tolerant reads, no migration** (PRD.md §9-A). Approve, or request a one-time
   backfill spec (separate, manual).
4. **Confirm the staged rename**: SP1 keeps the wire key `simplified_care_plan` (only the Python
   attribute becomes `care_plan`); SP2 + SP5 flip the wire key + frontend together. Approve, or ask
   to do the wire rename now (requires SP1+SP5 to land together).
