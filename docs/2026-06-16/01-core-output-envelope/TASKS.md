# Tasks: Core Output Envelope Refactor

Read `PRD.md` in this folder first — it explains the *why* behind every decision referenced below.
Tasks are numbered in dependency order; do them in order unless a task says otherwise.

---

### Task 1 — Create `JsonModel` / `VersionedJsonModel` base classes

**File (new):** `backend/models/__init__.py`, `backend/models/base.py`

Create `backend/models/` as a Python package (just `__init__.py`, can be empty or re-export the
model classes — your call, keep it minimal).

In `base.py`:
- `JsonModel`: a base class (use `@dataclass` on subclasses) with two methods:
  - `to_dict(self) -> dict` — default implementation: `dataclasses.asdict(self)`. Subclasses override
    when they need custom flattening (see `SimplifiedCarePlan` in Task 5).
  - `from_dict(cls, data: dict)` — classmethod, default implementation: `cls(**data)`. Subclasses
    override when needed.
- `VersionedJsonModel(JsonModel)`: adds a `version: str` field expectation and a registry:
  - A class-level dict mapping version string → subclass, e.g. `_registry: dict[str, type] = {}`
    (define per concrete base, not shared globally — see note in Task 5).
  - A classmethod decorator `register(version: str)` that subclasses use to register themselves.
  - A classmethod `from_dict(cls, data: dict)` that reads `data["version"]`, looks up the registered
    subclass, and constructs it. Raise a clear `ValueError` if the version isn't registered.

**Acceptance criteria:**
- `JsonModel`/`VersionedJsonModel` have no Flask/Firestore imports — pure Python, easily unit-testable.
- A throwaway dataclass subclassing `JsonModel` round-trips through `to_dict()` → `from_dict()` and
  equals the original.

**Depends on:** nothing.

---

### Task 2 — `Metrics` model

**File (new):** `backend/models/metrics.py`

Implement the `Metrics` dataclass exactly as specified in PRD.md §4 ("`Metrics` (not versioned,
always latest shape)"). Fields: `session_id`, `pipeline_version`, `input_type`, `created_at`,
`total_duration_ms` (default `None`), `step_durations_ms` (default `{}`), `saved_id` (default `None`).

Add a small helper classmethod `Metrics.start(session_id, pipeline_version, input_type) -> Metrics`
that sets `created_at = datetime.now(timezone.utc).isoformat()` and leaves duration/saved_id at
defaults — routes will mutate `total_duration_ms`, `step_durations_ms`, and `saved_id` onto the
instance as the pipeline runs (it's a plain mutable dataclass, not frozen).

**Acceptance criteria:** `Metrics.start(...).to_dict()` produces the exact shape shown in PRD.md §5.

**Depends on:** Task 1.

---

### Task 3 — `Input` model

**File (new):** `backend/models/input.py`

⚠️ **Do not start this task until you (the user) have confirmed the PRD.md §8 checkpoint** — whether
`Input.files` stores metadata only (filename/content_type/size_bytes) or needs raw bytes. This task
assumes metadata-only per the PRD's default recommendation.

Implement `InputFile` (filename, content_type, size_bytes) and `Input` (mode, text, doc_id, files)
exactly as specified in PRD.md §4. Add a constructor helper:
```python
Input.from_file_uploads(uploads: list) -> Input   # uploads = list of werkzeug FileStorage
Input.from_text(text: str) -> Input
Input.from_doc_id(doc_id: str) -> Input
```
where `from_file_uploads` reads `.filename`, `.content_type`, and `len(.read())` off each
`FileStorage` (careful: reading consumes the stream — use `upload.seek(0)` after, or read length via
`request.content_length` per-part if simpler; check how `resolved.source_filename` etc. are currently
computed in `simplify_v1_2.py`'s input-resolution code around line 184 for the existing pattern of
handling these uploads without breaking the existing PDF-merge logic that also reads them).

**Acceptance criteria:** Round-trips via `to_dict()`/`from_dict()`. Does not consume/break the existing
file-reading code path used for PDF merging (run the existing v1-2 file-upload integration test after
wiring this in, in Task 7).

**Depends on:** Task 1.

---

### Task 4 — `Grading` stub model

**File (new):** `backend/models/grading.py`

Implement the stub exactly as PRD.md §4 shows: `entries: list[dict] = field(default_factory=list)`.
No other logic. (Sub-project 3 replaces the contents of this file with the real schema — this task
just needs the envelope to have somewhere to put an empty list.)

**Acceptance criteria:** `Grading().to_dict() == {"entries": []}`.

**Depends on:** Task 1.

---

### Task 5 — `SimplifiedCarePlan` versioned model

**File (new):** `backend/models/care_plan.py`

Implement per PRD.md §4. Use `VersionedJsonModel` from Task 1, registering three versions: `"1.0"`
(maps to today's v1/legacy shape — no `version` key existed before, so when constructing from a v1
pipeline result, pass `version="1.0"` explicitly rather than reading it from the data), `"1.1"`,
`"1.2"`. All three can share one concrete class (`SimplifiedCarePlan`) registered three times if the
packaging logic is identical across versions (it is — the model doesn't validate per-version fields,
it just carries the dict) — i.e. you don't need three separate Python classes, just register the same
class for "1.0", "1.1", and "1.2" in the registry built in Task 1.

Override `to_dict()` to flatten as shown in PRD.md §4 (`{"version": self.version, **self.data}`), and
override `from_dict()` to split incoming dict back into `version` + everything else as `data`.

**Acceptance criteria:** Given a sample v1-2 pipeline result dict (use a real example from
`backend/tests/` fixtures if one exists, otherwise construct a minimal one with `doc_type`,
`diagnosis`, `terms`), `SimplifiedCarePlan.from_pipeline_result("1.2", sample).to_dict()` reproduces
`{"version": "1.2", **sample}` exactly.

**Depends on:** Task 1.

---

### Task 6 — `SimplifyOutput` envelope + legacy-shape detector

**File (new):** `backend/models/envelope.py`

Implement `SimplifyOutput` per PRD.md §4. Add one module-level function:
```python
def is_legacy_shape(data: dict) -> bool:
    return "simplified_care_plan" not in data
```
(used by the frontend's mirror of this logic, and useful if any backend code ever needs to branch on
stored-output shape — e.g. sub-project 5's history grouping).

**Acceptance criteria:** `SimplifyOutput(metrics=..., input=..., grading=..., simplified_care_plan=...).to_dict()`
produces exactly the shape in PRD.md §5 "After".

**Depends on:** Tasks 2, 3, 4, 5.

---

### Task 7 — Wire the envelope into the v1-2 route

**File:** `backend/routes/simplify_v1_2.py`

This is the main behavior change. In `_generate_stream` (around current lines 184–481):
1. At request start, after `session_id`/`api_version` are known, build `metrics = Metrics.start(session_id=g.session_id, pipeline_version="v1-2", input_type=resolved.source_kind)`.
2. As each `juno_logger.log_step(name, "done", duration_ms=...)` call happens, also do
   `metrics.step_durations_ms[name] = duration_ms`.
3. Build `input_model` from `resolved` using the Task 3 helpers (`Input.from_text`, `from_file_uploads`,
   `from_doc_id` based on `resolved.source_kind`).
4. Where `result = {**structured, "terms": ..., "raw": ..., ...}` is currently assembled (around line
   399), instead build:
   ```python
   care_plan = SimplifiedCarePlan.from_pipeline_result("1.2", {
       **structured, "terms": terms_glossary, "raw": {...},
       **({"before_score": before_score} if before_score is not None else {}),
       **({"after_score": after_score} if after_score is not None else {}),
   })
   grading = Grading()  # empty stub this sub-project
   ```
5. After the `save_simplify_output(...)` call currently sets `result["saved_id"] = saved_id` (around
   line 437), instead set `metrics.saved_id = saved_id`.
6. Set `metrics.total_duration_ms = monotonic_ms() - pipeline_start` right before emitting.
7. Replace every `yield _sse({"step": "result", "data": result})` with:
   ```python
   output = SimplifyOutput(metrics=metrics, input=input_model, grading=grading, simplified_care_plan=care_plan)
   yield _sse({"step": "result", "data": output.to_dict()})
   ```
8. Pass `output_data=output.to_dict()` into `save_simplify_output(...)` instead of the old flat `result`
   dict (the call happens *before* `saved_id` is known, so do step 5's `metrics.saved_id` assignment,
   then re-emit `output.to_dict()` at the final yield — the version saved to Firestore in step 4 won't
   have `saved_id` yet, which is fine and matches today's behavior where `saved_id` is also only added
   to the in-memory `result` after the save call, not persisted inside itself).

**Acceptance criteria:** Existing v1-2 integration/route tests pass after updating their assertions to
the new nested shape (see Task 9). Manually trigger the route locally and confirm the SSE `result`
event matches PRD.md §5 "After".

**Depends on:** Tasks 2–6.

---

### Task 8 — Wire the envelope into v1 and v1-1 routes

**Files:** `backend/routes/simplify.py` (the `_simplify_document_v1` function), `backend/routes/simplify_v1_1.py`

Same pattern as Task 7, adapted to each route's existing structure:
- v1 (`simplify.py`): `pipeline_version="v1"`, `SimplifiedCarePlan.from_pipeline_result("1.0", result_payload)` where `result_payload` is the dict currently built at line 219. No `saved_id`/Firestore save exists for v1 today (file held in memory only per the module docstring) — leave `metrics.saved_id = None`.
- v1-1 (`simplify_v1_1.py`): mirror Task 7 exactly but with `pipeline_version="v1-1"` and
  `SimplifiedCarePlan.from_pipeline_result("1.1", ...)`.

**Acceptance criteria:** Same as Task 7, for each route.

**Depends on:** Tasks 2–6. Independent of Task 7 (can be done in parallel by a different agent).

---

### Task 9 — Update backend tests

**Files:** `backend/tests/test_models.py` (new), existing route test files under `backend/tests/`
(find via `grep -rl "simplify_v1_2\|/simplify/v1-2" backend/tests/`)

- `test_models.py`: round-trip tests for every model in Tasks 2–6 (one test per model, plus one for
  `SimplifyOutput.to_dict()` matching PRD.md §5 exactly given fixed inputs).
- Existing route tests: update any assertion that reads `response_json["diagnosis"]` etc. directly to
  instead read `response_json["simplified_care_plan"]["diagnosis"]`, and add an assertion that
  `response_json["metrics"]["session_id"]` is present and non-empty.

**Acceptance criteria:** `pytest backend/tests/` passes.

**Depends on:** Tasks 7, 8.

---

### Task 10 — Frontend types

**File (new):** `frontend/src/types/envelope.ts`

Define TypeScript interfaces mirroring the backend models 1:1: `Metrics`, `InputFile`, `Input`,
`Grading` (just `{ entries: unknown[] }` for now), `SimplifiedCarePlan` (reuse/extend the existing
`AppointmentNote` type from `frontend/src/types/simplify.ts` — `SimplifiedCarePlan` is
`{ version: string } & AppointmentNote`), and `SimplifyOutput` (`{ metrics, input, grading,
simplified_care_plan }`).

**Acceptance criteria:** Types compile (`npm run typecheck` or equivalent in `frontend/`).

**Depends on:** nothing (can be done in parallel with backend tasks once PRD.md is read).

---

### Task 11 — `normalizeSimplifyOutput` adapter

**File (new):** `frontend/src/utils/normalizeOutput.ts`

```ts
export function isLegacyShape(data: any): boolean {
  return !('simplified_care_plan' in data);
}

export function normalizeSimplifyOutput(raw: any): SimplifyOutput {
  if (!isLegacyShape(raw)) return raw as SimplifyOutput;
  // Legacy flat shape: everything except saved_id is the care plan itself.
  const { saved_id, ...rest } = raw;
  return {
    metrics: { session_id: '', pipeline_version: rest.version ?? 'v1', input_type: 'file', created_at: '', saved_id: saved_id ?? null, step_durations_ms: {} },
    input: { mode: 'file', files: [] },
    grading: { entries: [] },
    simplified_care_plan: { version: rest.version ?? '1.0', ...rest },
  };
}
```
(Adjust placeholder defaults for legacy `metrics`/`input` as needed — the point is legacy records have
no real metrics/input data, so empty/placeholder values are correct and expected; don't fabricate
fake session IDs.)

**Acceptance criteria:** Given a sample legacy flat JSON fixture and a sample new-envelope JSON
fixture, both produce a `SimplifyOutput`-shaped object from this function.

**Depends on:** Task 10.

---

### Task 12 — Update frontend consumers

**Files:** `frontend/src/pages/v1_2/V1_2Page.tsx` (and V1/V1.1 equivalents), `frontend/src/components/AppointmentNoteV12View.tsx`, `frontend/src/components/Sidebar.tsx` (or wherever saved outputs are loaded and passed to the view — confirm exact file via `grep -rl "AppointmentNoteV12View" frontend/src`)

1. Wherever the SSE `result` event is received, and wherever a saved output is fetched and loaded for
   display, pass the raw JSON through `normalizeSimplifyOutput()` first.
2. `AppointmentNoteV12View` (and equivalents) take `simplified_care_plan` as their data prop instead of
   the whole envelope — i.e. the call site does
   `<AppointmentNoteV12View data={output.simplified_care_plan} />`, the component itself doesn't need
   internal changes if it was already taking the flat appointment-note shape as a prop.
3. Add a small, unobtrusive "Request ID: `{output.metrics.session_id}`" line to the report view (exact
   placement is a judgement call — bottom of the report, near where `saved_id`/timestamps might already
   be shown, is reasonable; don't make it prominent, it's a support/debugging aid not a headline
   feature).

**Acceptance criteria:** Manually run the app (`/run` skill or `npm run dev`), submit a file through
v1-2, confirm the report renders identically to before plus the new Request ID line. Then manually open
a saved output that pre-dates this change (if one exists in your Firestore) and confirm it still
renders correctly — **this specific check is the manual verification noted in PRD.md §8 and only you
can do it against real data.**

**Depends on:** Tasks 7, 8, 11.

---

## Summary of what requires you (not a dev agent)

1. **Before Task 3:** confirm whether `Input.files` should store metadata only (recommended) or raw
   file bytes.
2. **After Task 12:** manually verify one real pre-existing saved output still renders correctly
   (validates the legacy-shape path against real production data, which a dev agent can't access).
