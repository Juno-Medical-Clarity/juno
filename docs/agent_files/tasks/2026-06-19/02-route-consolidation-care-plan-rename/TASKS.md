# Tasks: Route Consolidation & `care_plan` Rename

Read `PRD.md` in this folder first. **This sub-project lands AFTER SP1** (typed models). Before
starting, confirm SP1's final names for the envelope (`CarePlanInternal`), `SimplifiedCarePlan`,
`Grading`, `Input`, `Metrics` and adjust imports if they differ (PRD §4.1, §9.6).

All paths are relative to `/root/projects/juno/backend` unless stated otherwise.

Recommended order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11.

---

### Task 1 — Create `routes/care_plan.py` from `simplify_v1_2.py` (the single route module)

**Create:** `routes/care_plan.py` by moving the body of `routes/simplify_v1_2.py` and applying renames.

Steps:
1. Copy `routes/simplify_v1_2.py` → `routes/care_plan.py`.
2. Rename the blueprint: `simplify_v1_2_bp = Blueprint("simplify_v1_2", __name__)` →
   `care_plan_bp = Blueprint("care_plan", __name__)`.
3. Rename `run_v1_2_pipeline` → `run_care_plan_pipeline` (keep signature
   `(text, metrics, grading_enabled)`).
4. Rename `_generate_stream(user_id)` → `_care_plan_stream(user_id)`.
5. Rename the public view `simplify_v1_2()` into the new entry point `create_care_plan` (see Task 2 —
   the entry point gains the `version` validation that used to live in `simplify.py`).
6. Update import `from simplify.v1_2.pipeline import V1_2Pipeline` (unchanged).
7. Update import `from utils.save_output import save_simplify_output, upload_combined_pdf` →
   `from utils.save_output import save_care_plan_output, upload_combined_pdf` (rename done in Task 8).
8. Update the envelope import: `from models.envelope import SimplifyOutput` →
   `from models.envelope import CarePlanInternal` (SP1 name — confirm).
9. Rename all `simplify_v1_2:` log prefixes and `JunoLogger(api_version="v1-2")` stays `"v1-2"`;
   change log strings to `care_plan:` prefix. Metric call sites:
   `record_counter("simplify_request", ...)` → `record_counter("care_plan_request", ...)`;
   `record_latency("simplify_pipeline", ...)` → `record_latency("care_plan_pipeline", ...)`;
   `record_error(..., "simplify_pipeline", ...)` → `... "care_plan_pipeline" ...`.
10. Update SSE docstring header (`POST /simplify with version=v1-2` → `POST /care_plan`).

**Acceptance:** `routes/care_plan.py` imports cleanly; `care_plan_bp` exists; no symbol named
`simplify_v1_2` remains in the file; pipeline still runs the 5 v1_2 steps.

**Depends on:** SP1 (models). Tasks 2–4 refine this file.

---

### Task 2 — Fold the dispatcher + version validation into `create_care_plan`; delete dispatch

**Edit:** `routes/care_plan.py`.

The old `routes/simplify.py::simplify_document()` read `version`, validated against
`ALLOWED_VERSIONS`, and dispatched. There is now only one pipeline. Implement:

```python
from config import CARE_PLAN_DEFAULT_VERSION

ALLOWED_VERSIONS = {"v1-2"}

@care_plan_bp.route("/care_plan", methods=["POST"])
@verify_firebase_token
def create_care_plan(user_id: str):
    json_body = request.get_json(silent=True) or {}
    if "version" in request.form:
        version = request.form.get("version")
    elif isinstance(json_body, dict) and "version" in json_body:
        version = json_body.get("version")
    else:
        version = CARE_PLAN_DEFAULT_VERSION
    if not isinstance(version, str) or version not in ALLOWED_VERSIONS:
        return {"error": f"Unknown version '{version}'"}, 400
    return Response(
        stream_with_context(_care_plan_stream(getattr(g, "user_id", user_id))),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
```

Remove any reference to `simplify_v1_1`, `_simplify_document_v1`, `V1Pipeline`. There is no `if
version == "v1-2"` branch — there is only one path.

**Acceptance:** `POST /care_plan` with `version` omitted or `v1-2` → 200 SSE; `version=v1` or `v1-1` →
`400`. No import of `routes.simplify_v1_1` or `simplify.v1.pipeline` anywhere in the file.

**Depends on:** Task 1.

---

### Task 3 — Make the route the single composer + single serializer

**Edit:** `routes/care_plan.py`.

Today (in `run_v1_2_pipeline` + `_generate_stream`) the envelope is built in the pipeline function and
then the route patches `result_data["input"]` and `result_data["metrics"]` after serialization
(PRD §4.3). Refactor so composition + serialization happen exactly once, in the stream function.

1. In `run_care_plan_pipeline`, stop constructing `SimplifyOutput`/`CarePlanInternal` and stop calling
   `output.to_dict()`. Instead, after building `care_plan = SimplifiedCarePlan.from_pipeline_result(
   "1.2", {...})` and `grading = build_grading(...) | Grading(enabled=False)`, hand the **typed
   objects** back to the stream function. Two acceptable mechanics (pick one, document it):
   - (a) Yield a non-SSE sentinel the stream intercepts, e.g.
     `yield ("__result__", care_plan, grading, text, clarified)` and have the stream check
     `isinstance(chunk, tuple)`; or
   - (b) Pass a mutable holder/`ResolvedPipelineResult` dataclass into the generator that the stream
     reads after the loop.
   Do **not** emit `output.to_dict()` from the pipeline.
2. In `_care_plan_stream`, after the pipeline loop:
   - For non-`doc_id` sources, call `save_care_plan_output(...)` and set `metrics.saved_id`. The
     `output_data` argument should be the dict to persist (serialize the care-plan/grading/input/
     metrics-so-far portion needed for storage; `_without_raw` still strips `raw`). Persistence is
     allowed to serialize separately (PRD §4.3 / §9.5).
   - Compose **once**: `envelope = CarePlanInternal(metrics=metrics, input=input_model,
     grading=grading, simplified_care_plan=care_plan)`.
   - Serialize **once**: `yield _sse({"step": "result", "data": envelope.to_dict()})`.
3. Delete the post-hoc patches `result_data["input"] = input_model.to_dict()` and
   `result_data["metrics"] = metrics.to_dict()`. The `input` now comes from the real
   `_input_model_from_resolved(resolved)` passed into the composer — remove the throwaway
   `Input.from_text(text)` that used to be passed to the envelope inside the pipeline.

**Acceptance:**
- The final `result.data` has `input` reflecting the resolved input (text/file/doc_id), not a
  throwaway text input.
- For a saved run, `result.data.metrics.saved_id` is populated (set before the single serialize).
- `grep "to_dict()" routes/care_plan.py` shows the envelope serialized in exactly one place in the
  response path; no `result_data["input"]`/`result_data["metrics"]` assignment remains.

**Depends on:** Tasks 1, 2; SP1 (`CarePlanInternal`).

---

### Task 4 — Delete the old route modules

**Delete:** `routes/simplify.py`, `routes/simplify_v1_1.py`, `routes/simplify_v1_2.py`.

Before deleting, confirm nothing else imports them except `routes/__init__.py` and `routes/batch.py`
(handled in Tasks 5, 6):
```
grep -rn "routes.simplify\b\|routes.simplify_v1_1\|routes.simplify_v1_2\|from routes.simplify import" backend --include="*.py"
```

**Acceptance:** the three files are gone; `grep` above returns only references you are updating in
Tasks 5/6 (or none).

**Depends on:** Tasks 1–3 (new module must exist first).

---

### Task 5 — Delete v1 & v1_1 pipelines; update `interface.py` / `simplify/__init__.py`

**Delete:** directories `simplify/v1/` and `simplify/v1_1/` entirely (including
`appointment.schema.json`, `__init__.py`, `pipeline.py`, and `__pycache__`).

**Keep:** `simplify/v1_2/` unchanged.

**Edit `simplify/interface.py`:** rename the ABC `SimplifyPipeline` → `CarePlanPipeline` and update its
docstring (drop the "Create routes/simplify_v<X>.py" wording; mention `routes/care_plan.py`).

**Edit `simplify/v1_2/pipeline.py`:** update `from simplify.interface import SimplifyPipeline` →
`from simplify.interface import CarePlanPipeline` and `class V1_2Pipeline(SimplifyPipeline)` →
`class V1_2Pipeline(CarePlanPipeline)`. (Class name `V1_2Pipeline` stays.) Optionally tidy the
"simplify pipeline" docstrings to "care_plan pipeline" (cosmetic).

Confirm nothing imports the deleted pipelines:
```
grep -rn "simplify.v1.pipeline\|simplify.v1_1.pipeline\|V1Pipeline\|V1_1Pipeline" backend --include="*.py"
```

**Acceptance:** dirs deleted; `simplify/v1_2/pipeline.py` imports `CarePlanPipeline`; the grep above
returns nothing (outside tests you fix in Task 11).

**Depends on:** Task 4 (route deletions remove the importers).

---

### Task 6 — Update `routes/__init__.py`, `routes/batch.py`, `routes/grading.py`, `routes/datasets.py`

**`routes/__init__.py`:**
```python
from routes.care_plan import care_plan_bp
from routes.saved_outputs import saved_outputs_bp
from routes.datasets import datasets_bp
from routes.batch import batch_bp
from routes.grading import grading_bp

all_blueprints = [care_plan_bp, saved_outputs_bp, datasets_bp, batch_bp, grading_bp]
```

**`routes/batch.py`:**
- Imports: replace
  ```python
  from config import SIMPLIFY_DEFAULT_VERSION
  from routes.simplify import ALLOWED_VERSIONS, run_v1_pipeline
  from routes.simplify_v1_1 import run_v1_1_pipeline
  from routes.simplify_v1_2 import _extract_text_from_bytes, run_v1_2_pipeline
  from utils.save_output import save_simplify_output
  ```
  with
  ```python
  from config import CARE_PLAN_DEFAULT_VERSION
  from routes.care_plan import ALLOWED_VERSIONS, _extract_text_from_bytes, run_care_plan_pipeline
  from utils.save_output import save_care_plan_output
  ```
- `_pipeline_for_version`: collapse to a single supported version:
  ```python
  def _pipeline_for_version(version: str):
      if version == "v1-2":
          return run_care_plan_pipeline
      raise ValueError(f"Unknown version '{version}'")
  ```
- Default version: `version = body.get("version", CARE_PLAN_DEFAULT_VERSION)`.
- Route path: `@batch_bp.route("/care_plan/batch", methods=["POST"])`; rename view
  `simplify_batch` → `create_care_plan_batch`.
- `save_simplify_output(...)` call → `save_care_plan_output(...)`.

**`routes/grading.py`:**
- Route path: `@grading_bp.route("/care_plan/grade", methods=["POST"])`.
- Optionally rename view `run_grading` → `run_care_plan_grading`.
- Collection literal `db.collection("simplify_outputs")` — **leave unchanged** (PRD §8.4).
- The `_get_doc_or_403` helper here duplicates the one in `saved_outputs.py`. Out of scope to merge
  (SP3 owns utils consolidation) — leave as-is, or note for SP3.

**`routes/datasets.py`:**
- Import: `from routes.simplify_v1_2 import _extract_text_from_bytes` →
  `from routes.care_plan import _extract_text_from_bytes`.
- Route paths: `/simplify/datasets` → `/care_plan/datasets`; the file route
  `/simplify/datasets/<group>/<input_id>/<string:filename>` → `/care_plan/datasets/...`.

**Acceptance:** `python -c "import routes"` (or app import) succeeds; all blueprints register;
no remaining import of `routes.simplify*` or `run_v1_pipeline`/`run_v1_1_pipeline`/`save_simplify_output`.

**Depends on:** Tasks 1–5; Task 7 (config var); Task 8 (save rename).

---

### Task 7 — Rename config var `SIMPLIFY_DEFAULT_VERSION` → `CARE_PLAN_DEFAULT_VERSION`

**Edit `config.py`:**
```python
CARE_PLAN_DEFAULT_VERSION = os.getenv('CARE_PLAN_DEFAULT_VERSION', 'v1-2')
```
Remove the old `SIMPLIFY_DEFAULT_VERSION` line.

Confirm all importers updated (Tasks 2, 6):
```
grep -rn "SIMPLIFY_DEFAULT_VERSION" backend --include="*.py"
```
should return nothing after Tasks 2/6.

**Acceptance:** no `SIMPLIFY_DEFAULT_VERSION` references remain in code. **Deploy note (you, not the
dev):** the env var must be renamed in Cloud Run/deploy config (PRD §8.2).

**Depends on:** none (do alongside Task 6).

---

### Task 8 — Rename `save_simplify_output` → `save_care_plan_output`

**Edit `utils/save_output.py`:** rename the function `save_simplify_output` → `save_care_plan_output`.
Keep the `simplify/{user_id}/inputs/...` GCS blob prefix and the `"simplify_outputs"` Firestore
collection literal **unchanged** (PRD §8.4 — no data migration).

Update all call sites (`routes/care_plan.py`, `routes/batch.py`) — done in Tasks 1/6.
```
grep -rn "save_simplify_output" backend --include="*.py"
```
should return only tests (fixed in Task 11) after Tasks 1/6.

**Acceptance:** function renamed; collection/blob literals unchanged; no non-test references to the old
name.

**Depends on:** none (do alongside Tasks 1/6).

---

### Task 9 — Remove dead `appointment_id` plumbing in `app.py`

**Edit `app.py`:**

1. In `before_request` (`extract_session_id`), remove the `appointment_id` branch. Replace lines
   ~64–73 with:
   ```python
   session_id = request.headers.get("X-Session-Id", "") or str(uuid.uuid4())
   g.session_id = session_id
   ```
   and remove the now-stale comment block about appointment_id grouping (lines ~54–66).
   **SP4 boundary:** do not add new session_id semantics — SP4 owns the fallback. This task only
   *removes the dead route-name lookup* (PRD §8.5).
2. In the `/` root endpoint, delete the entire `'endpoints'` dict of `/appointments/*` entries (lines
   ~144–159). Replace with the real, current surface:
   ```python
   'endpoints': {
       'POST /care_plan': 'Simplify a medical document into a care plan (SSE)',
       'POST /care_plan/grade': 'Re-run grading on a saved or ephemeral care plan',
       'POST /care_plan/batch': 'Batch-simplify dataset selections (SSE)',
       'GET /care_plan/datasets': 'List preset datasets',
       'GET /care_plan/saved': "List the user's saved care plans",
       'GET /health': 'Health check',
   }
   ```
   (Adjust copy as desired — the load-bearing change is removing the non-existent `/appointments/*`.)

**Acceptance:** no `appointment_id` reference in `app.py`; root `/` JSON contains no `/appointments/*`
key; a request with no `X-Session-Id` header still gets a generated `session_id`.

**Depends on:** none. **Coordinate with SP4** before landing (PRD §8.5).

---

### Task 10 — (Open-question gated) Backward-compat aliases for `/simplify*`

**Only if PRD §9.1 is answered "keep aliases for one release."** Otherwise skip (hard cut).

If aliasing: on each blueprint, register the old path as a second rule on the same view, e.g.
```python
@care_plan_bp.route("/care_plan", methods=["POST"])
@care_plan_bp.route("/simplify", methods=["POST"])   # deprecated alias; remove next release
@verify_firebase_token
def create_care_plan(user_id: str): ...
```
Do the same for `/simplify/grade`, `/simplify/batch`, `/simplify/datasets...`, `/simplify/saved...`.
Gate behind a `CARE_PLAN_LEGACY_ALIASES` env flag if you want runtime control.

**Acceptance:** with aliases on, both `/simplify*` and `/care_plan*` return 200; with the flag off
(or hard cut), `/simplify*` → 404.

**Depends on:** Tasks 1–9; **decision in PRD §9.1**.

---

### Task 11 — Update tests to the new surface (SP6 owns reorg/CI; SP2 updates paths/imports)

**Edit (and rename files `test_simplify_*` → `test_care_plan_*`, confirm naming with SP6):**
- `tests/test_simplify_version_dispatch.py` — assert `v1`/`v1-1` → 400, `v1-2`/omitted → 200 against
  `POST /care_plan`; remove dispatch-to-v1/v1_1 assertions.
- `tests/test_batch_route.py` — path `/care_plan/batch`; imports of `run_care_plan_pipeline`;
  `save_care_plan_output`.
- `tests/test_dataset_routes.py` — paths `/care_plan/datasets...`.
- `tests/test_saved_outputs_route.py` — paths `/care_plan/saved...`.
- `tests/test_simplify_auth.py` — auth test against `/care_plan`.
- `tests/test_simplify_v1_2_persistence.py` — path/imports; `save_care_plan_output`.
- `tests/test_simplify_pipeline_executors.py` — import `run_care_plan_pipeline` (was `run_v1_2_pipeline`);
  drop any v1/v1_1 executor tests.
- `tests/test_save_output.py` — `save_care_plan_output`; collection literal still `simplify_outputs`.
- `tests/test_grading_model.py`, `tests/test_models.py`, `tests/test_container_startup.py` — update any
  `/simplify` path strings, `SIMPLIFY_DEFAULT_VERSION`, `SimplifyOutput`→`CarePlanInternal` references.

**Add new route tests (PRD §7):** items 1–9 in PRD §7 (composer-uses-resolved-input, saved_id present
before single serialize, doc_id not persisted, version validation, removed/aliased paths, new paths
reachable, app.py cleanup, batch uses consolidated pipeline, grade endpoint on new path).

**Acceptance:** `pytest backend/tests` green; no test references `/simplify`, `simplify_v1_1`,
`run_v1_pipeline`, `SIMPLIFY_DEFAULT_VERSION`, or `save_simplify_output` (except where an alias test
intentionally hits `/simplify`).

**Depends on:** Tasks 1–10.

---

## Summary of what requires you (not a dev agent)

1. **Decide hard cut vs. `/simplify*` alias** (PRD §9.1) — gates Tasks 10 and test #5. Recommendation:
   one-release alias behind a flag, then delete.
2. **Rename the deploy env var** `SIMPLIFY_DEFAULT_VERSION` → `CARE_PLAN_DEFAULT_VERSION` in Cloud
   Run / deploy config / secrets (PRD §8.2). Code change alone is not enough.
3. **Coordinate the frontend (SP5) lockstep deploy** of the new `/care_plan*` paths, or ensure aliases
   are live first (PRD §6, §8.3).
4. **Confirm no external clients call `/simplify`** before a hard cut (PRD §8.1).
5. **SP4 boundary:** confirm SP4 owns/has-landed the `session_id` fallback so removing the dead
   `appointment_id` branch (Task 9) does not regress trace grouping (PRD §8.5).
6. **Metric/log name renames** (`simplify_*` → `care_plan_*`) create new series; update Monitoring
   dashboards/alerts or defer the metric-name half to SP4 (PRD §8.6, §9.3).
7. **Firestore collection** stays `simplify_outputs` (no migration) unless you schedule one (PRD §8.4).
8. **Confirm SP1's final envelope class name** (`CarePlanInternal`) before landing (PRD §9.6).
9. **Decide whether the inner key `simplified_care_plan` becomes `care_plan`** (PRD §9.2) — default
   keep for wire stability.
