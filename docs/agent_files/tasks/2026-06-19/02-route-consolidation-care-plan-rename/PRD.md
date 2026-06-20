# PRD: Route Consolidation & `care_plan` Rename

Sub-project 2 (SP2) of the Juno backend refactor. **Phase 1. Lands AFTER SP1** (Pydantic v2 typed
models). Coordinates with **SP3** (utils consolidation — import paths), **SP4** (observability —
`session_id`/logging semantics), **SP5** (frontend — consumes the new paths), **SP6** (testing/CI).

---

## 1. Problem

The simplify surface is three parallel route modules behind one dispatcher:

- `routes/simplify.py` — the `POST /simplify` entry point. It reads the requested `version`, validates
  it against `ALLOWED_VERSIONS = {"v1", "v1-1", "v1-2"}`, and dispatches: `v1-2` → `simplify_v1_2()`,
  `v1-1` → `simplify_v1_1()`, else the inline `_simplify_document_v1()` (the original V1 SSE pipeline).
- `routes/simplify_v1_1.py` — the V1.1 handler + `run_v1_1_pipeline()`.
- `routes/simplify_v1_2.py` — the **real, current** handler: SSE stream, multi-file resolve, GCS
  `doc_id` fetch, pipeline run, save-to-Firestore, and final `SimplifyOutput` composition.

This causes several problems:

1. **Three pipelines, two of them dead.** Only `v1_2` is the live product path. `v1` (scispaCy NER +
   document classification + parenthetical definitions) and `v1_1` (no question generation) are legacy.
   They carry their own LLM prompt code, schema files, and bespoke error handling, and every route/
   dependent file (`batch.py`, `__init__.py`, `config.py`) keeps branching to support all three.

2. **Composition is split between the pipeline and the route.** In `simplify_v1_2.py` the pipeline
   builds a `SimplifyOutput` and emits `output.to_dict()`, then the route's `_generate_stream()`
   **patches the dict after the fact**: `result_data["input"] = input_model.to_dict()` and
   `result_data["metrics"] = metrics.to_dict()`. So the "envelope" is assembled in two places, the
   pipeline composes an `Input.from_text(text)` that the route immediately overwrites, and the final
   JSON is serialized, mutated, re-serialized. There is no single composer and no single serialization
   point.

3. **The name `simplify` is everywhere** — route paths, blueprint names, file/module names, config
   vars, log/metric operation names, the Firestore collection, and the frontend API paths — even
   though the product concept is a **care plan**. SP1 already renamed the output model to
   `CarePlanInternal` (assumed; see §4), but the routes still speak "simplify".

4. **Dead `appointment_id` plumbing in `app.py`.** `before_request` derives `session_id` from
   `request.view_args["appointment_id"]`, but **no `/appointments/<appointment_id>` route exists** in
   this service. The `/` root endpoint also advertises ~13 `/appointments/*` endpoints that do not
   exist. Both are stale carryover and mislead anyone reading the service.

This sub-project consolidates to ONE route module (`care_plan`), deletes the v1/v1_1 pipelines, makes
the route the single composer + single serializer, renames `simplify` → `care_plan` everywhere, and
removes the dead appointment plumbing.

---

## 2. Goals

1. **One route module.** Replace `routes/simplify.py` + `routes/simplify_v1_1.py` +
   `routes/simplify_v1_2.py` with a single `routes/care_plan.py` exposing `POST /care_plan`. The
   v1/v1_1 dispatch branches disappear; `v1_2` is the only pipeline and stays **named `v1_2`**.
2. **Route is the single composer + single serializer.** The route calls the three layers
   (input → pipeline → grading), composes exactly one `CarePlanInternal`, and serializes it **once**
   at the SSE `result` step. No post-hoc dict patching of `input`/`metrics`.
3. **Delete dead pipelines.** Remove `simplify/v1/` and `simplify/v1_1/` and all v1/v1_1-only code.
   Keep `simplify/v1_2/` (still `v1_2`). Update `simplify/interface.py` / `simplify/__init__.py`.
4. **Rename `simplify` → `care_plan` everywhere in the backend** — paths, blueprints, modules, config
   var (`SIMPLIFY_DEFAULT_VERSION` → `CARE_PLAN_DEFAULT_VERSION`), `ALLOWED_VERSIONS`, log/metric
   operation names, and the saved-output API surface. Full rename map in §4.
5. **Update dependents** — `batch.py`, `grading.py`, `saved_outputs.py`, `datasets.py` — to the
   consolidated path and the v1_2 pipeline.
6. **Remove dead appointment plumbing** in `app.py` (`before_request` branch + root-endpoint docs).
7. **Define the new backend paths the frontend must adopt** (SP5 implements the frontend changes).
8. **Specify route/integration tests** to add (SP6 owns the test reorg + CI wiring).

---

## 3. Non-Goals

- **Not rewriting the v1_2 pipeline logic.** The 5 LLM/term steps in `simplify/v1_2/pipeline.py` are
  unchanged. Only the *route* that drives them and *composes their output* changes.
- **Not changing the grading algorithm.** That is SP3-grading-rework's concern; SP2 only re-wires the
  `Grading` model into the consolidated route.
- **Not renaming the SP1 models.** `CarePlanInternal` / `SimplifiedCarePlan` / `Grading` / `Input`
  come from SP1. SP2 *uses* them.
- **Not changing logging/`session_id` semantics.** SP4 owns observability. SP2 only removes the dead
  route-name (`appointment_id`) plumbing; SP4 owns the correct `session_id` fallback. (Boundary in §8.)
- **Not implementing the frontend changes.** SP2 defines the contract; SP5 implements it.

> **Owner note (2026-06-20):** "Not renaming the Firestore collection" is **withdrawn**. Nothing is in
> production and there is no data to migrate, so SP2 renames the collection literal
> `"simplify_outputs"` → `"care_plan_outputs"` directly (see §4.4, §8). No migration, no dual-read.

---

## 4. Architecture Decisions

### 4.1 Assumed SP1 typed interface (state explicitly; verify before landing)

SP2 lands after SP1 and assumes the following typed surface exists. If SP1 names differ, adjust at
landing:

```python
# models/care_plan.py (SP1)
class SimplifiedCarePlan(VersionedJsonModel): ...  # name SP1 keeps for the v1_2 structured result type
    @classmethod
    def from_pipeline_result(cls, version: str, data: dict) -> "SimplifiedCarePlan"
    def to_dict(self) -> dict                      # {"version": ..., **data}

# models/grading.py (SP1 + SP3)
class Grading(JsonModel): ...
def build_grading(before_score, before_text, after_score, after_text) -> Grading

# models/input.py (SP1)
class Input(JsonModel):
    @classmethod def from_text(cls, text) -> "Input"
    @classmethod def from_file_uploads(cls, uploads) -> "Input"
    @classmethod def from_doc_id(cls, doc_id) -> "Input"
    @classmethod def from_batch_dataset(cls, ...) -> "Input"

# models/metrics.py (SP1)
class Metrics(JsonModel): @classmethod def start(cls, session_id, pipeline_version, input_type)

# models/envelope.py (SP1) — the top-level envelope, RENAMED by SP1
class CarePlanInternal(JsonModel):              # was SimplifyOutput
    metrics: Metrics
    input: Input
    grading: Grading
    care_plan: SimplifiedCarePlan               # inner wire key is `care_plan` (hard-flipped, see below)
    def to_dict(self) -> dict
```

> **NOTE on the locked decision "`SimplifyOutput → CarePlanInternal`."** Today the envelope class is
> `SimplifyOutput` in `models/envelope.py`. SP1 renames it to `CarePlanInternal`. SP2 imports and
> composes `CarePlanInternal`.
>
> **CROSS-CUTTING DECISION (2026-06-20): inner wire key is `care_plan`.** The envelope's inner key for
> the care-plan content is **`care_plan`**, not `simplified_care_plan`. This is a HARD FLIP applied NOW
> across SP1/SP2/SP5 — there is **no `simplified_care_plan` alias**, one decided key only. The
> envelope's `to_dict()` JSON keys are therefore `metrics`/`input`/`grading`/`care_plan`. Because
> nothing is in production, the previous "keep `simplified_care_plan` for wire stability" stance is
> overridden. SP1 owns the field name on the model; SP2 composes it; SP5 reads `care_plan`.

### 4.2 Consolidated route design

`routes/care_plan.py` contains a single blueprint `care_plan_bp` and one public endpoint
`POST /care_plan`, plus the existing helper functions migrated verbatim from `simplify_v1_2.py`
(`_resolve_input`, `_resolve_uploaded_files`, `_fetch_from_gcs`, `_extract_text_from_bytes`,
`_input_model_from_resolved`, `_grading_enabled_from_request`, `_derive_output_name`, `_sse`,
`run_care_plan_pipeline` [renamed from `run_v1_2_pipeline`], `ResolvedInput`).

The `version` field is **read from the request body** (form field or JSON key `version`) and selects
how the care plan is serialized/produced. Today `ALLOWED_VERSIONS` collapses to `{"v1-2"}` and the
default is `CARE_PLAN_DEFAULT_VERSION` (default `"v1-2"`). Unknown versions → `400`.

**Extensibility (owner decision, 2026-06-20):** v1 and v1_1 are deleted, but the owner WILL add more
versions/layers later (e.g. `v1-3`). The route must be built so adding the next version is a small,
local change — NOT a re-architecture. Concretely:

- The version comes from the **request body** (the frontend supplies it), validated against
  `ALLOWED_VERSIONS`.
- Selection of pipeline + serialization is driven by a single explicit mapping keyed by version, e.g.
  a `PIPELINES = {"v1-2": run_care_plan_pipeline}` (or equivalent registry). Adding `v1-3` means: add
  the new pipeline callable, add `"v1-3"` to `ALLOWED_VERSIONS`, add one entry to the mapping. No
  branching `if version == ...` chains.
- This is a **registry of one** today — deliberately. It is NOT the multi-module dispatcher of the old
  `routes/simplify.py`; there is one route module (`routes/care_plan.py`) and one consolidated stream
  function. Do **not** resurrect v1/v1_1-style separate route files for new versions; new versions add
  a pipeline + a registry entry, not a new blueprint.

### 4.3 Composition flow (route = single composer + single serializer)

This is the core structural change. Today composition is split:

```
# BEFORE (simplify_v1_2.py)
run_v1_2_pipeline(...):                      # pipeline layer + route layer entangled
    ... runs steps ...
    care_plan = SimplifiedCarePlan.from_pipeline_result("1.2", {...})
    grading   = build_grading(...) or Grading(enabled=False)
    output    = SimplifyOutput(metrics, Input.from_text(text), grading, care_plan)  # composes Input here
    yield _sse({"step": "result", "data": output.to_dict()})                        # serializes #1

_generate_stream(...):                        # route layer patches the already-serialized dict
    result_data = payload["data"]
    result_data["input"]   = input_model.to_dict()    # OVERWRITES the Input the pipeline composed
    ... save_simplify_output(...) ...
    result_data["metrics"] = metrics.to_dict()         # patches metrics post-hoc
    yield _sse({"step": "result", "data": result_data})  # serializes #2
```

The pipeline composes an `Input.from_text(text)` that is immediately thrown away, and the dict is
serialized twice with a mutation in between.

```
# AFTER (routes/care_plan.py)
run_care_plan_pipeline(text, metrics, grading_enabled) -> yields typed layer outputs, NOT an envelope.
    It yields SSE step events, and a final sentinel carrying the *typed* pieces the route needs:
      { "step": "_pipeline_done",
        "care_plan": SimplifiedCarePlan,    # pipeline layer output (typed)
        "grading":   Grading,               # grading layer output (typed)
        "raw_text":  text, "clarified_text": clarified }   # for save + grade re-run
    (Implementation note: because SSE chunks are strings, the pipeline generator instead returns the
     typed objects via a small closure/holder or yields a non-SSE marker the route intercepts — the
     route, not the pipeline, builds CarePlanInternal. Keep the pipeline free of envelope/serialize.)

_care_plan_stream(user_id, version):          # the ONLY composer + serializer
    resolved   = _resolve_input()             # input layer
    input_mdl  = _input_model_from_resolved(resolved)        # input layer -> Input
    session_id = g.session_id                  # SP4 boundary: session_id only, never user_id fallback
    metrics    = Metrics.start(session_id=session_id, pipeline_version=version,
                               input_type=resolved.source_kind)
    pipeline   = PIPELINES[version]             # registry lookup (extensibility, §4.2)
    # drive pipeline, forward step SSE events
    care_plan, grading, raw_text, clarified = run pipeline (typed outputs)
    envelope = CarePlanInternal(metrics=metrics, input=input_mdl, grading=grading,
                                care_plan=care_plan)          # COMPOSE ONCE (inner key `care_plan`)
    if resolved.source_kind != "doc_id":
        payload = envelope.to_dict()                          # SERIALIZE ONCE
        metrics.saved_id = save_care_plan_output(... output_data=payload)  # persist from the SAME dict
        payload["metrics"]["saved_id"] = metrics.saved_id     # reflect saved_id into the one payload
        yield _sse({"step": "result", "data": payload})
    else:
        yield _sse({"step": "result", "data": envelope.to_dict()})   # doc_id path: not persisted
```

Key rules enforced by this design:
- The **pipeline returns its own typed model** (`SimplifiedCarePlan`) and the **grading layer returns
  `Grading`** and the **input layer returns `Input`**. The route does **not** build dicts by hand.
- `CarePlanInternal` is constructed in exactly one place, with the real `Input` (no throwaway
  `Input.from_text`), the real `Metrics`, the real `Grading`. The inner wire key is **`care_plan`**.
- **Single-serialize including persistence (owner decision, 2026-06-20):** there is **one**
  `to_dict()` call. The persisted Firestore payload is derived from the *same* dict produced for the
  response — store-then-respond from one dict. `save_care_plan_output()` returns the `saved_id`, which
  is written back into that single payload's `metrics` before the `result` event is yielded. No
  separate serialization for persistence, no post-hoc `result_data["input"]`/`result_data["metrics"]`
  rebuild. `save_output.py`'s `_without_raw` still strips `raw` from what it stores (it receives the
  full payload and strips for storage only — the response keeps `raw`).
- **Save ordering:** because `saved_id` must appear in the response `metrics`, the sequence is
  compose → serialize once → save (passing the dict) → write the returned `saved_id` back into that
  same dict → emit `result`. The `doc_id` source is the early-exit: no save, just serialize once.

### 4.4 Full rename map (old → new)

**Files / modules (move + rename):**

| Old | New |
|-----|-----|
| `routes/simplify.py` (dispatcher + V1 inline pipeline) | merged into `routes/care_plan.py` (V1 inline pipeline DELETED) |
| `routes/simplify_v1_1.py` | **deleted** |
| `routes/simplify_v1_2.py` | becomes the body of `routes/care_plan.py` |
| `simplify/v1/` (dir: `__init__.py`, `pipeline.py`) | **deleted** |
| `simplify/v1_1/` (dir: `__init__.py`, `pipeline.py`, `appointment.schema.json`) | **deleted** |
| `simplify/v1_2/` | **kept, unchanged** (still `v1_2`) |
| `simplify/interface.py` | kept; class `SimplifyPipeline` → `CarePlanPipeline` (see symbols) |
| `simplify/__init__.py` | kept (empty) |
| `utils/save_output.py` | kept; function `save_simplify_output` → `save_care_plan_output` (see symbols) |

**Blueprints:**

| Old | New |
|-----|-----|
| `simplify_bp = Blueprint("simplify", ...)` | `care_plan_bp = Blueprint("care_plan", ...)` |
| `simplify_v1_1_bp = Blueprint("simplify_v1_1", ...)` | **deleted** |
| `simplify_v1_2_bp = Blueprint("simplify_v1_2", ...)` | **deleted** (folded into `care_plan_bp`) |
| `grading_bp` | unchanged name; route path changes (below) |
| `batch_bp`, `saved_outputs_bp`, `datasets_bp` | unchanged names; route paths change (below) |

**Route paths:**

| Old | New |
|-----|-----|
| `POST /simplify` | `POST /care_plan` |
| `POST /simplify/grade` | `POST /care_plan/grade` |
| `POST /simplify/batch` | `POST /care_plan/batch` |
| `GET  /simplify/datasets` | `GET  /care_plan/datasets` |
| `GET  /simplify/datasets/<group>/<input_id>/<filename>` | `GET  /care_plan/datasets/<group>/<input_id>/<filename>` |
| `GET  /simplify/saved` | `GET  /care_plan/saved` |
| `GET  /simplify/saved/<doc_id>` | `GET  /care_plan/saved/<doc_id>` |
| `PATCH /simplify/saved/<doc_id>` | `PATCH /care_plan/saved/<doc_id>` |
| `DELETE /simplify/saved/<doc_id>` | `DELETE /care_plan/saved/<doc_id>` |
| `GET  /simplify/saved/<doc_id>/input-pdf-url` | `GET  /care_plan/saved/<doc_id>/input-pdf-url` |

**Config / constants:**

| Old | New |
|-----|-----|
| `config.SIMPLIFY_DEFAULT_VERSION` (env `SIMPLIFY_DEFAULT_VERSION`) | `config.CARE_PLAN_DEFAULT_VERSION` (env `CARE_PLAN_DEFAULT_VERSION`) |
| `ALLOWED_VERSIONS = {"v1","v1-1","v1-2"}` | `ALLOWED_VERSIONS = {"v1-2"}` |

**Symbols / functions (Python):**

| Old | New |
|-----|-----|
| `simplify_document()` (view) | `create_care_plan()` |
| `simplify_v1_1()`, `simplify_v1_2()`, `_simplify_document_v1()` | **deleted** (one `create_care_plan` view) |
| `run_v1_pipeline`, `run_v1_1_pipeline` | **deleted** |
| `run_v1_2_pipeline` | `run_care_plan_pipeline` |
| `_generate_stream(user_id)` | `_care_plan_stream(user_id)` |
| `SimplifyPipeline` (ABC in `interface.py`) | `CarePlanPipeline` |
| `V1_2Pipeline(SimplifyPipeline)` | `V1_2Pipeline(CarePlanPipeline)` (class name kept; base renamed) |
| `save_simplify_output` | `save_care_plan_output` |
| `simplify_batch()` (view) | `create_care_plan_batch()` |
| `run_grading()` (view in grading.py) | `run_care_plan_grading()` (optional; path change is the load-bearing part) |

**Log / metric operation strings (coordinate with SP4 — SP4 owns logging semantics):**

| Old | New |
|-----|-----|
| `JunoLogger(api_version="v1-1" / "v1-2")` | `JunoLogger(api_version="v1-2")` (v1-1 gone) |
| metric `"simplify_request"` | `"care_plan_request"` |
| metric/operation `"simplify_pipeline"` | `"care_plan_pipeline"` |
| log prefixes `"simplify_v1_2: ..."`, `"simplify: ..."` | `"care_plan: ..."` |
| docstring examples `path="/simplify/v1-2"` in `juno_logger.py`/`juno_metrics.py` | `path="/care_plan"` |

> **Metric/operation string renames (owner decision, 2026-06-20):** create the NEW names; do **not**
> preserve the old `simplify_*` series. The route-level call sites
> (`record_counter("care_plan_request")`, `record_latency("care_plan_pipeline")`,
> `record_error(..., "care_plan_pipeline", ...)`) are renamed by SP2. The docstring examples in
> `utils/juno_metrics.py` / `utils/juno_logger.py` are coordinated with SP4 (which owns those module
> internals); if SP4 has not restructured them by landing, SP2 updates the docstrings too. There is no
> dual-emit and no old-name retention.

**Term-detection / pipeline docstrings:** `utils/term_detection.py` line 2 and the v1_2 pipeline
docstrings say "simplify pipeline" — cosmetic; rename to "care_plan pipeline" for consistency
(non-load-bearing, low priority).

**Firestore collection (owner decision, 2026-06-20 — rename HERE):** code references
`db.collection("simplify_outputs")` in `save_output.py`, `grading.py`, `saved_outputs.py`. Rename the
literal to **`"care_plan_outputs"`** in all three. Nothing is in production and there is no data, so
there is **no migration, no dual-read, no data copy** — just change the string. (This overrides the
earlier "leave unchanged" stance.)

**GCS blob prefix:** `save_output.py` uses a `simplify/{user_id}/inputs/...` blob prefix. Rename it to
`care_plan/{user_id}/inputs/...` for consistency (no objects to migrate).

---

## 5. API Change Summary

All changes are **path renames** of the `/simplify*` surface to `/care_plan*`; request/response
bodies are unchanged except where noted. SSE step events are unchanged, and the final event is
`{"step":"result","data": <CarePlanInternal.to_dict()>}` — but the inner content key is now
**`care_plan`** (was `simplified_care_plan`; hard flip, see §4.1). The top-level keys are
`metrics`/`input`/`grading`/`care_plan`.

| Endpoint (before) | Endpoint (after) | Request | Response |
|---|---|---|---|
| `POST /simplify` | `POST /care_plan` | multipart `files[]`/`file`/`text`/`doc_id`, `version` (from request body, default `v1-2`, only `v1-2` allowed today), `grading_enabled` | SSE; final `data` = `CarePlanInternal.to_dict()` (inner key `care_plan`) |
| `POST /simplify/grade` | `POST /care_plan/grade` | JSON `{saved_id}` or `{text, clarified_text}` | `{ "grading": Grading.to_dict() }` |
| `POST /simplify/batch` | `POST /care_plan/batch` | JSON `{version, selections, grading_enabled}` | SSE batch events |
| `GET /simplify/datasets` | `GET /care_plan/datasets` | — | `{ "datasets": [...] }` |
| `GET /simplify/datasets/<g>/<i>/<f>` | `GET /care_plan/datasets/<g>/<i>/<f>` | — | `{ filename, content }` |
| `GET /simplify/saved` | `GET /care_plan/saved` | — | `{ "outputs": [...] }` |
| `GET /simplify/saved/<id>` | `GET /care_plan/saved/<id>` | — | full output doc |
| `PATCH /simplify/saved/<id>` | `PATCH /care_plan/saved/<id>` | `{name}` | `{id, name}` |
| `DELETE /simplify/saved/<id>` | `DELETE /care_plan/saved/<id>` | — | `{deleted}` |
| `GET /simplify/saved/<id>/input-pdf-url` | `GET /care_plan/saved/<id>/input-pdf-url` | — | `{url}` |

**Removed behavior:** `version=v1` and `version=v1-1` are no longer accepted → `400 {"error":"Unknown
version 'v1'"}`. The `/` root endpoint no longer advertises non-existent `/appointments/*` routes.

**Backward-compatibility for old `/simplify*` clients:** none. **HARD CUT** (owner decision,
2026-06-20) — no one uses `/simplify`, so there is **no alias and no redirect** from `/simplify*` to
`/care_plan*`. The `/simplify*` paths simply 404 after this lands. Frontend (SP5) ships the new paths
in lockstep (§6, §8).

---

## 6. Frontend Change Summary (SP5 implements; SP2 defines)

The frontend already references these paths (verified in `frontend/src`):

| File | Old reference | New value SP5 must adopt |
|---|---|---|
| `src/config.ts` | `SIMPLIFY_API_PATH = '/simplify'` | `'/care_plan'` (rename the const to `CARE_PLAN_API_PATH`) |
| `src/components/OutputGradingCard.tsx` | `${API_URL}/simplify/grade` | `${API_URL}/care_plan/grade` |
| `src/api/datasets.ts` | `/simplify/datasets`, `/simplify/datasets/.../...`, `/simplify/batch` | `/care_plan/...` |
| `src/api/savedOutputs.ts` | `/simplify/saved`, `/simplify/saved/<id>`, `/simplify/saved/<id>/input-pdf-url` | `/care_plan/saved...` |

**Not in scope for the rename (these are TS type-module file names, not backend paths):**
`src/types/simplify.ts`, `src/types/envelope.ts`, `src/utils/grading.ts`,
`src/pages/simplify/SimplifyPage.tsx`, `src/App.tsx`'s `SimplifyPage` import. Renaming those TS
modules/symbols is SP5's call and does not affect the backend contract. SP2 only owns the **HTTP path
strings** above.

**Inner key change SP5 must adopt:** the envelope's inner content key is now **`care_plan`** (was
`simplified_care_plan`; hard flip, §4.1). Frontend consumers that read `data.simplified_care_plan`
(e.g. `AppointmentNoteV12View.tsx`, `envelope.ts`) must read `data.care_plan`. There is no alias.

**Deploy coordination (owner decision, 2026-06-20):** the path change AND the inner-key change are a
**hard cut** — no aliases. The frontend MUST ship the new `/care_plan*` paths and read the `care_plan`
inner key **in lockstep** with the backend deploy (deploy FE and BE together). There is no
one-release alias window.

---

## 7. Testing (SP6 owns the reorg/CI; SP2 specifies these route-level tests)

Existing tests that reference the old surface and MUST be updated (verified present):
`tests/test_simplify_version_dispatch.py`, `tests/test_batch_route.py`, `tests/test_dataset_routes.py`,
`tests/test_saved_outputs_route.py`, `tests/test_simplify_auth.py`,
`tests/test_simplify_v1_2_persistence.py`, `tests/test_simplify_pipeline_executors.py`,
`tests/test_container_startup.py`, `tests/test_save_output.py`, `tests/test_grading_model.py`.
Rename files `test_simplify_*` → `test_care_plan_*` (SP6 confirms naming) and update paths/imports.

New / updated route-level tests SP2 requires:

1. **`POST /care_plan` happy path (text input):** 200 SSE; final `result.data` has top-level keys
   `metrics`, `input`, `grading`, `care_plan` (the inner key is `care_plan`, NOT
   `simplified_care_plan` — assert `simplified_care_plan` is absent); `input` reflects the *real*
   resolved input (text mode), NOT a throwaway — i.e. assert the composer used the resolved `Input`.
2. **Single-serialize (incl. persistence) invariant:** assert `metrics.saved_id` is present in the
   final `result.data.metrics` for a saved (non-`doc_id`) run, and that the persisted Firestore
   payload is derived from the SAME dict (e.g. mock `save_care_plan_output`, assert it received a dict
   with the `care_plan` inner key; assert no second `to_dict()` / no `result_data["metrics"]` rebuild).
3. **`doc_id` path is not persisted:** a `doc_id`-sourced request yields a result with no Firestore
   write (mock `save_care_plan_output`, assert not called) — preserves the existing early-exit.
4. **Version validation:** `version=v1` and `version=v1-1` → `400`; `version=v1-2` and omitted → 200.
5. **Removed routes 404 (hard cut):** `POST /simplify`, `POST /simplify/grade`, `GET /simplify/saved`
   → 404. No alias exists; assert 404 unconditionally.
6. **New paths reachable:** `POST /care_plan`, `POST /care_plan/grade`, `POST /care_plan/batch`,
   `GET /care_plan/datasets`, `GET /care_plan/saved` all auth-gated and routable.
7. **`app.py` cleanup:** root `/` JSON no longer contains any `/appointments/*` key; a request still
   gets a `session_id` from `X-Session-Id` (or a generated UUID when the header is absent) — and
   **never** falls back to `user_id`. The `appointment_id` branch removal does not break the
   header→UUID fallback. (SP4 boundary, §8.5.)
8. **Batch uses the consolidated pipeline:** `POST /care_plan/batch` imports/calls
   `run_care_plan_pipeline` (the former `run_v1_2_pipeline`) and no longer references
   `run_v1_pipeline` / `run_v1_1_pipeline`.
9. **`grade` endpoint reads from the renamed save helper / collection:** existing grading tests pass
   against the new path and the renamed collection `"care_plan_outputs"`.

---

## 8. Manual Intervention Required From You

1. **Deployed route names / live clients — RESOLVED: HARD CUT.** No one uses `/simplify`, so SP2 does
   a hard cut: no alias, no redirect for `/simplify*` → `/care_plan*`. The `/simplify*` paths 404 after
   landing. No external-caller confirmation step is required (owner confirmed none).
2. **Env var rename `SIMPLIFY_DEFAULT_VERSION` → `CARE_PLAN_DEFAULT_VERSION`.** This is a Cloud Run
   deploy-config change. Update the env var in the Cloud Run service / deploy manifest / `.env` /
   secrets at deploy time, or the new code falls back to the `"v1-2"` default and silently ignores the
   old var. **Action required by you in the deploy pipeline.**
3. **Frontend lockstep deploy — RESOLVED: YES.** SP5 ships the new `/care_plan*` paths AND the
   `care_plan` inner key. Backend + frontend deploy **together** (no alias window exists). You
   coordinate the simultaneous release.
4. **Firestore collection name — RESOLVED: RENAME HERE.** Nothing is in production and there is no data
   to migrate, so SP2 changes the collection literal `"simplify_outputs"` → `"care_plan_outputs"`
   directly (and the GCS blob prefix `simplify/...` → `care_plan/...`). No migration, no dual-read, no
   data copy. Nothing for you to do here beyond the deploy itself.
5. **SP4 boundary — `session_id` — RESOLVED.** SP2 removes the dead `appointment_id` branch in
   `before_request` and the stale root-endpoint docs. `session_id` is sourced from `X-Session-Id`
   (header) → generated UUID; it **never** falls back to `user_id`. SP4 owns any further fallback
   semantics. Confirm SP4 has landed/will land its fallback so removing the dead branch does not
   regress trace grouping.
6. **Metric/operation string renames — RESOLVED: NEW names, no old retention.**
   (`simplify_request` → `care_plan_request`, `simplify_pipeline` → `care_plan_pipeline`, etc.) These
   create **new** metric/log series; the old `simplify_*` series stop entirely (no dual-emit). Old
   dashboards/alerts querying `simplify_*` will go silent — update Cloud Monitoring dashboards/alerts
   to the new names. **Action required by you in Monitoring.**

---

## 9. Open Questions & Decisions

1. **Hard cut vs. alias for `/simplify*`.** `[RESOLVED: 2026-06-20 — HARD CUT.]` No one uses
   `/simplify`. No alias, no redirect for `/simplify*` → `/care_plan*`. `/simplify*` paths 404 after
   landing. Removes the alias task and the alias-gated branch of test #5; see §5, §6, §8.1.
2. **Inner key `simplified_care_plan` → `care_plan`.** `[RESOLVED: 2026-06-20 — HARD FLIP to
   `care_plan`.]` Cross-cutting decision across SP1/SP2/SP5. The envelope's inner content key is
   `care_plan`; there is **no `simplified_care_plan` alias**, one key only. Nothing is in production so
   wire stability is not a concern. SP1 owns the model field name; SP2 composes `care_plan=...`; SP5
   reads `data.care_plan` (`AppointmentNoteV12View.tsx`, `envelope.ts`). See §4.1, §5, §6.
3. **Metric-name rename ownership.** `[RESOLVED: 2026-06-20 — create NEW names; do not preserve old.]`
   SP2 renames the route-level call sites (`care_plan_request`, `care_plan_pipeline`) and updates the
   `juno_metrics.py`/`juno_logger.py` docstrings if SP4 hasn't restructured them by landing. No
   dual-emit; old `simplify_*` series stop. SP4 owns module internals. See §4.4, §8.6.
4. **`save_simplify_output` rename + collection name.** `[RESOLVED: 2026-06-20 — rename BOTH.]`
   Function `save_simplify_output` → `save_care_plan_output`; collection literal `"simplify_outputs"` →
   `"care_plan_outputs"`; GCS blob prefix `simplify/...` → `care_plan/...`. No data to migrate. See
   §4.4, §8.4.
5. **Single-serialize including persistence.** `[RESOLVED: 2026-06-20 — single serialize INCLUDING
   persistence.]` The persisted payload is derived from the same single `to_dict()` call as the
   response (store-then-respond from one dict; `saved_id` written back into that one payload). No
   separate serialization for persistence. See §4.3.
6. **`CarePlanInternal` exact name from SP1.** `[RESOLVED: 2026-06-20 — name is exactly
   `CarePlanInternal`.]` SP2 imports `from models.envelope import CarePlanInternal`. No adjustment
   needed.
7. **Extensibility for future versions.** `[RESOLVED: 2026-06-20 — keep the design extensible.]` Even
   though v1/v1_1 are deleted, more versions/layers WILL be added later. The version is supplied by the
   frontend in the request body and selects pipeline + serialization via a single registry mapping
   (`PIPELINES = {"v1-2": ...}`). Adding `v1-3` = add the pipeline + one registry entry + one
   `ALLOWED_VERSIONS` member. Do NOT resurrect per-version route modules/blueprints. See §4.2.
