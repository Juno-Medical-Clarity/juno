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
- **Not renaming the Firestore collection data already in production.** The *code constant* may be
  renamed but the on-disk collection name must stay stable unless a migration is scheduled (see §8/§9).
- **Not implementing the frontend changes.** SP2 defines the contract; SP5 implements it.

---

## 4. Architecture Decisions

### 4.1 Assumed SP1 typed interface (state explicitly; verify before landing)

SP2 lands after SP1 and assumes the following typed surface exists. If SP1 names differ, adjust at
landing:

```python
# models/care_plan.py (SP1)
class CarePlan(VersionedJsonModel): ...          # pipeline-produced care plan (was SimplifiedCarePlan)
class SimplifiedCarePlan(VersionedJsonModel): ...  # name SP1 keeps for the v1_2 structured result
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
    simplified_care_plan: SimplifiedCarePlan    # field name retained for response stability
    def to_dict(self) -> dict
```

> **NOTE on the locked decision "`SimplifyOutput → CarePlanInternal`."** Today the envelope class is
> `SimplifyOutput` in `models/envelope.py`. SP1 renames it to `CarePlanInternal`. SP2 imports and
> composes `CarePlanInternal`. The **envelope's `to_dict()` JSON keys are unchanged**
> (`metrics`/`input`/`grading`/`simplified_care_plan`) so the wire shape is stable for SP5. See §9 for
> the open question on whether the inner `simplified_care_plan` key should also become `care_plan`.

### 4.2 Consolidated route design

`routes/care_plan.py` contains a single blueprint `care_plan_bp` and one public endpoint
`POST /care_plan`, plus the existing helper functions migrated verbatim from `simplify_v1_2.py`
(`_resolve_input`, `_resolve_uploaded_files`, `_fetch_from_gcs`, `_extract_text_from_bytes`,
`_input_model_from_resolved`, `_grading_enabled_from_request`, `_derive_output_name`, `_sse`,
`run_care_plan_pipeline` [renamed from `run_v1_2_pipeline`], `ResolvedInput`).

The `version` form/JSON field is still accepted for forward compatibility, but `ALLOWED_VERSIONS`
collapses to `{"v1-2"}` and the default is `CARE_PLAN_DEFAULT_VERSION` (default `"v1-2"`). Unknown
versions → `400`. There is **no dispatch** — v1/v1_1 are gone.

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

_care_plan_stream(user_id):                   # the ONLY composer + serializer
    resolved   = _resolve_input()             # input layer
    input_mdl  = _input_model_from_resolved(resolved)        # input layer -> Input
    metrics    = Metrics.start(session_id=..., pipeline_version="v1-2", input_type=resolved.source_kind)
    # drive pipeline, forward step SSE events
    care_plan, grading, raw_text, clarified = run pipeline (typed outputs)
    if resolved.source_kind != "doc_id":
        metrics.saved_id = save_care_plan_output(... output_data=<serialized once below or pre-save>)
    envelope = CarePlanInternal(metrics=metrics, input=input_mdl, grading=grading,
                                simplified_care_plan=care_plan)   # COMPOSE ONCE
    yield _sse({"step": "result", "data": envelope.to_dict()})    # SERIALIZE ONCE
```

Key rules enforced by this design:
- The **pipeline returns its own typed model** (`SimplifiedCarePlan`) and the **grading layer returns
  `Grading`** and the **input layer returns `Input`**. The route does **not** build dicts by hand.
- `CarePlanInternal` is constructed in exactly one place, with the real `Input` (no throwaway
  `Input.from_text`), the real `Metrics` (already carrying `saved_id`), the real `Grading`.
- `to_dict()` is called **once**, at the `result` step. No post-serialization patching.
- **Save ordering:** `save_care_plan_output()` needs `saved_id` to land in `metrics` *before* the
  single serialize. So the save happens before composing the envelope. The data persisted to Firestore
  is derived from the typed pieces (the route can serialize the care-plan/grading portion for storage;
  `save_output.py`'s `_without_raw` still strips `raw`). Compose-then-save-then-reserialize is the one
  case where two serializations are unavoidable — acceptable because the *response* path serializes
  once; the *persistence* path is separate. (Document this in the route; flagged in §9 if the team
  wants a stricter single-serialize including persistence.)

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

> **SP4 boundary:** the metric/operation string renames touch `utils/juno_metrics.py` and
> `utils/juno_logger.py` docstrings. SP2 proposes them in this map but **defers final wording to SP4**
> if SP4 is restructuring those modules. At minimum, the *route-level* call sites
> (`record_counter("care_plan_request")`, `record_latency("care_plan_pipeline")`) are renamed by SP2.

**Term-detection / pipeline docstrings:** `utils/term_detection.py` line 2 and the v1_2 pipeline
docstrings say "simplify pipeline" — cosmetic; rename to "care_plan pipeline" for consistency
(non-load-bearing, low priority).

**Firestore collection:** code references `db.collection("simplify_outputs")` in `save_output.py`,
`grading.py`, `saved_outputs.py`. **Leave the literal collection name `"simplify_outputs"` unchanged**
in Phase 1 (renaming it is a data migration, not a code refactor). See §8/§9.

---

## 5. API Change Summary

All changes are **path renames** of the `/simplify*` surface to `/care_plan*`; request/response
bodies are unchanged except where noted. SSE shapes are byte-identical (same step events, same final
`{"step":"result","data": <CarePlanInternal.to_dict()>}`).

| Endpoint (before) | Endpoint (after) | Request | Response |
|---|---|---|---|
| `POST /simplify` | `POST /care_plan` | multipart `files[]`/`file`/`text`/`doc_id`, `version` (optional, only `v1-2`), `grading_enabled` | SSE; final `data` = `CarePlanInternal.to_dict()` (keys unchanged) |
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

**Backward-compatibility for old `/simplify*` clients:** see §8 + §9 (alias vs. hard cut decision).

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

**Deploy coordination:** because the path change is a hard cut (default), the frontend must ship the
new paths **in lockstep** with the backend deploy — or the backend must keep `/simplify*` aliases for
one release (see §8/§9).

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
   `metrics`, `input`, `grading`, `simplified_care_plan`; `input` reflects the *real* resolved input
   (text mode), NOT a throwaway — i.e. assert the composer used the resolved `Input`.
2. **Single-serialize / single-compose invariant:** assert `metrics.saved_id` is present in the final
   `result.data.metrics` for a saved (non-`doc_id`) run, proving `saved_id` was set before the one
   serialize (no post-hoc `result_data["metrics"]` patch).
3. **`doc_id` path is not persisted:** a `doc_id`-sourced request yields a result with no Firestore
   write (mock `save_care_plan_output`, assert not called) — preserves the existing early-exit.
4. **Version validation:** `version=v1` and `version=v1-1` → `400`; `version=v1-2` and omitted → 200.
5. **Removed routes 404:** `POST /simplify`, `POST /simplify/grade`, `GET /simplify/saved` → 404
   (or 200 if alias kept — gate the assertion on the §9 decision).
6. **New paths reachable:** `POST /care_plan`, `POST /care_plan/grade`, `POST /care_plan/batch`,
   `GET /care_plan/datasets`, `GET /care_plan/saved` all auth-gated and routable.
7. **`app.py` cleanup:** root `/` JSON no longer contains any `/appointments/*` key; a request to a
   non-appointment route still gets a `session_id` (from `X-Session-Id` or generated UUID) — the
   `appointment_id` branch removal does not break the fallback. (Coordinate exact assertion with SP4.)
8. **Batch uses the consolidated pipeline:** `POST /care_plan/batch` imports/calls
   `run_care_plan_pipeline` (the former `run_v1_2_pipeline`) and no longer references
   `run_v1_pipeline` / `run_v1_1_pipeline`.
9. **`grade` endpoint reads from the renamed save helper / collection:** existing grading tests pass
   against the new path.

---

## 8. Manual Intervention Required From You

1. **Deployed route names / live clients.** `/simplify*` is the current production surface. Decide
   **hard cut vs. temporary alias** (default proposal: hard cut, frontend + backend deploy in
   lockstep). If any non-Juno client (scripts, Postman, partners) calls `/simplify`, you must either
   keep aliases (§9) or notify them. **You must confirm there are no external callers of `/simplify`
   before the hard cut.**
2. **Env var rename `SIMPLIFY_DEFAULT_VERSION` → `CARE_PLAN_DEFAULT_VERSION`.** This is a Cloud Run
   deploy-config change. Update the env var in the Cloud Run service / deploy manifest / `.env` /
   secrets at deploy time, or the new code falls back to the `"v1-2"` default and silently ignores the
   old var. **Action required by you in the deploy pipeline.**
3. **Frontend lockstep deploy.** SP5 ships the new `/care_plan*` paths. Backend + frontend must deploy
   together (or aliases must be live first). You coordinate the release ordering.
4. **Firestore collection name.** Code keeps `"simplify_outputs"` (no data migration in Phase 1). If
   you want the collection renamed to `care_plan_outputs`, that is a **separate, scheduled data
   migration** (copy docs + dual-read window) — out of SP2 scope; flag if desired.
5. **SP4 boundary — `session_id`.** SP2 removes the dead `appointment_id` branch in `before_request`
   and the stale root-endpoint docs. SP2 does **not** redesign the `session_id` fallback — **SP4 owns
   the correct fallback** (header → generated UUID, and any new semantics). Confirm SP4 has landed or
   will land the fallback so the removal does not regress trace grouping.
6. **Metric/operation string renames** (`simplify_pipeline` → `care_plan_pipeline`, etc.) will create
   **new metric/log series**; old dashboards/alerts querying `simplify_*` will go silent. Update Cloud
   Monitoring dashboards/alerts, or defer the metric-name half of the rename to SP4. **Your call.**

---

## 9. Open Questions

1. **Hard cut vs. alias for `/simplify*`.** Default: hard cut. Alternative: register the old paths as
   aliases (same view functions, both `/simplify` and `/care_plan` rules on the blueprint) for one
   release, then remove. Aliasing is ~5 lines per route and de-risks the frontend lockstep. **Decision
   needed** — it changes test #5 and §8.1. Recommendation: keep aliases for ONE release behind a
   `CARE_PLAN_LEGACY_ALIASES` flag, then delete.
2. **Inner key `simplified_care_plan`.** The envelope's inner key is `simplified_care_plan`. Should it
   become `care_plan` for full naming consistency? That is a **response-shape change** that ripples to
   SP5 (`AppointmentNoteV12View.tsx`, `envelope.ts`) and saved Firestore docs (read-time mapping).
   Default: **keep `simplified_care_plan`** in Phase 1 (wire stability); revisit in a later phase.
3. **Metric-name rename ownership.** Should SP2 rename `simplify_request`/`simplify_pipeline` now, or
   leave them for SP4 to avoid double-touching `juno_metrics.py`? Default: SP2 renames the **route call
   sites**; SP4 owns module internals/docstrings.
4. **`save_simplify_output` rename vs. collection name.** Renaming the function is safe; the
   *collection string* is not. Confirm we keep `"simplify_outputs"` as the collection literal (yes by
   default).
5. **Single-serialize including persistence.** §4.3 keeps persistence as a separate serialization from
   the response. Acceptable? Or do we want the persisted payload derived from the same single
   `to_dict()` call (store-then-respond from one dict)? Default: accept two (response path is single).
6. **`CarePlanInternal` exact name from SP1.** If SP1 lands the envelope as something other than
   `CarePlanInternal` (e.g. keeps `SimplifyOutput`), SP2 adjusts the import. Confirm SP1's final name
   before landing.
