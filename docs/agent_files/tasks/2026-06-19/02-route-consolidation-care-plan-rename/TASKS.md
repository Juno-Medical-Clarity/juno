# Tasks: Route Consolidation & `care_plan` Rename

Read `PRD.md` in this folder first. **This sub-project lands AFTER SP1** (typed models). SP1's
envelope class is `CarePlanInternal` with inner field `care_plan` (PRD §4.1, §9.6 — both resolved);
`SimplifiedCarePlan`, `Grading`, `Input`, `Metrics` also come from SP1.

All paths are relative to `/root/projects/juno/backend` unless stated otherwise.

Recommended order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10.

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
   `from models.envelope import CarePlanInternal` (SP1 name — confirmed, PRD §9.6).
9. Rename all `simplify_v1_2:` log prefixes and `JunoLogger(api_version="v1-2")` stays `"v1-2"`;
   change log strings to `care_plan:` prefix. Metric call sites — create the NEW names; do NOT preserve
   the old `simplify_*` series, no dual-emit (PRD §4.4, §8.6, §9.3):
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
`ALLOWED_VERSIONS`, and dispatched across separate route modules. There is now only one route module
and one pipeline today — but the design must stay **extensible** so adding `v1-3` later is a small,
local change (PRD §4.2, §9.7). Read the `version` from the **request body** (form or JSON), validate
it, and select the pipeline via a single registry mapping — NOT an `if version == ...` chain and NOT
new per-version blueprints.

```python
from config import CARE_PLAN_DEFAULT_VERSION

# Extensibility registry: adding v1-3 = add the pipeline callable + one entry here + add to ALLOWED.
PIPELINES = {"v1-2": run_care_plan_pipeline}
ALLOWED_VERSIONS = set(PIPELINES)   # {"v1-2"} today

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
        stream_with_context(_care_plan_stream(getattr(g, "user_id", user_id), version)),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
```

Pass the validated `version` into `_care_plan_stream` so the stream can look up `PIPELINES[version]`
(Task 3) and stamp `metrics.pipeline_version=version`. Remove any reference to `simplify_v1_1`,
`_simplify_document_v1`, `V1Pipeline`. There is no `if version == "v1-2"` branch.

**Acceptance:** `POST /care_plan` with `version` omitted or `v1-2` → 200 SSE; `version=v1` or `v1-1` →
`400`. Version is read from the request body; selection goes through the `PIPELINES` registry. No
import of `routes.simplify_v1_1` or `simplify.v1.pipeline` anywhere in the file.

**Depends on:** Task 1.

---

### Task 3 — Make the route the single composer + single serializer

**Edit:** `routes/care_plan.py`.

Today (in `run_v1_2_pipeline` + `_generate_stream`) the envelope is built in the pipeline function and
then the route patches `result_data["input"]` and `result_data["metrics"]` after serialization
(PRD §4.3). Refactor so composition + serialization happen exactly once — and persistence reuses that
SAME serialized dict (single-serialize INCLUDING persistence, PRD §4.3 / §9.5).

Signature: `_care_plan_stream(user_id, version)` (version passed from `create_care_plan`, Task 2).

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
2. In `_care_plan_stream`, look up the pipeline via the registry (`pipeline = PIPELINES[version]`) and
   stamp `metrics = Metrics.start(session_id=g.session_id, pipeline_version=version, ...)`
   (`session_id` only — never `user_id`, SP4 boundary, Task 9). After the pipeline loop:
   - Compose **once**, with the inner key `care_plan` (NOT `simplified_care_plan` — hard flip,
     PRD §4.1):
     `envelope = CarePlanInternal(metrics=metrics, input=input_model, grading=grading,
     care_plan=care_plan)`.
   - Serialize **once**: `payload = envelope.to_dict()`.
   - For non-`doc_id` sources, persist from that SAME dict and write the returned id back into it:
     `metrics.saved_id = save_care_plan_output(..., output_data=payload)` then
     `payload["metrics"]["saved_id"] = metrics.saved_id`. (`save_output.py`'s `_without_raw` strips
     `raw` for storage only; the response payload keeps `raw`.) Do NOT call `to_dict()` a second time
     and do NOT build a separate persistence dict.
   - Emit: `yield _sse({"step": "result", "data": payload})`. The `doc_id` source is the early-exit:
     no save, emit `envelope.to_dict()` directly.
3. Delete the post-hoc patches `result_data["input"] = input_model.to_dict()` and
   `result_data["metrics"] = metrics.to_dict()`. The `input` now comes from the real
   `_input_model_from_resolved(resolved)` passed into the composer — remove the throwaway
   `Input.from_text(text)` that used to be passed to the envelope inside the pipeline.

**Acceptance:**
- The final `result.data` has top-level key `care_plan` (NOT `simplified_care_plan`) and `input`
  reflecting the resolved input (text/file/doc_id), not a throwaway text input.
- For a saved run, `result.data.metrics.saved_id` is populated, and `save_care_plan_output` received
  the SAME dict that is sent in the response (single serialize including persistence).
- `grep "to_dict()" routes/care_plan.py` shows the envelope serialized in exactly one place; no
  `result_data["input"]`/`result_data["metrics"]` assignment and no second serialization remains.

**Depends on:** Tasks 1, 2; SP1 (`CarePlanInternal` with inner field `care_plan`).

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
returns nothing (outside tests you fix in Task 10).

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
- Collection literal `db.collection("simplify_outputs")` → `db.collection("care_plan_outputs")`
  (PRD §4.4, §8.4 — rename, no migration).
- The `_get_doc_or_403` helper here duplicates the one in `saved_outputs.py`. Out of scope to merge
  (SP3 owns utils consolidation) — leave as-is, or note for SP3.

**`routes/datasets.py`:**
- Import: `from routes.simplify_v1_2 import _extract_text_from_bytes` →
  `from routes.care_plan import _extract_text_from_bytes`.
- Route paths: `/simplify/datasets` → `/care_plan/datasets`; the file route
  `/simplify/datasets/<group>/<input_id>/<string:filename>` → `/care_plan/datasets/...`.

**`routes/saved_outputs.py`:**
- Route paths: `/simplify/saved...` → `/care_plan/saved...` (all of `GET /saved`, `GET/PATCH/DELETE
  /saved/<id>`, `GET /saved/<id>/input-pdf-url`).
- Collection literal `db.collection("simplify_outputs")` → `db.collection("care_plan_outputs")`
  (PRD §4.4, §8.4).

**Acceptance:** `python -c "import routes"` (or app import) succeeds; all blueprints register;
no remaining import of `routes.simplify*` or `run_v1_pipeline`/`run_v1_1_pipeline`/`save_simplify_output`;
no remaining `"simplify_outputs"` collection literal.

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
Also rename (PRD §4.4, §8.4 — nothing in production, no migration):
- GCS blob prefix `simplify/{user_id}/inputs/...` → `care_plan/{user_id}/inputs/...`.
- Firestore collection literal `"simplify_outputs"` → `"care_plan_outputs"`.

`save_care_plan_output` returns the saved doc id (so the route can write it back into the single
payload, Task 3). `_without_raw` still strips `raw` from the stored doc only.

Update all call sites (`routes/care_plan.py`, `routes/batch.py`) — done in Tasks 1/6.
```
grep -rn "save_simplify_output\|simplify_outputs" backend --include="*.py"
```
should return only tests (fixed in Task 10) after Tasks 1/6.

**Acceptance:** function renamed; collection literal is `"care_plan_outputs"`; blob prefix is
`care_plan/...`; no non-test references to `save_simplify_output` or `"simplify_outputs"`.

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
   **SP4 boundary (PRD §8.5):** `session_id` comes from `X-Session-Id` → generated UUID and **never**
   falls back to `user_id`. Do not add new session_id semantics — SP4 owns any further fallback. This
   task only *removes the dead route-name (`appointment_id`) lookup* and keeps the header→UUID path.
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

### Task 10 — Update tests to the new surface (SP6 owns reorg/CI; SP2 updates paths/imports)

**Edit (and rename files `test_simplify_*` → `test_care_plan_*`, confirm naming with SP6):**
- `tests/test_simplify_version_dispatch.py` — assert `v1`/`v1-1` → 400, `v1-2`/omitted → 200 against
  `POST /care_plan`; remove dispatch-to-v1/v1_1 assertions.
- `tests/test_batch_route.py` — path `/care_plan/batch`; imports of `run_care_plan_pipeline`;
  `save_care_plan_output`.
- `tests/test_dataset_routes.py` — paths `/care_plan/datasets...`.
- `tests/test_saved_outputs_route.py` — paths `/care_plan/saved...`.
- `tests/test_simplify_auth.py` — auth test against `/care_plan`.
- `tests/test_simplify_v1_2_persistence.py` — path/imports; `save_care_plan_output`; assert the
  persisted dict is the SAME one returned in the response (single serialize incl. persistence).
- `tests/test_simplify_pipeline_executors.py` — import `run_care_plan_pipeline` (was `run_v1_2_pipeline`);
  drop any v1/v1_1 executor tests.
- `tests/test_save_output.py` — `save_care_plan_output`; collection literal now `care_plan_outputs`;
  blob prefix now `care_plan/...`.
- `tests/test_grading_model.py`, `tests/test_models.py`, `tests/test_container_startup.py` — update any
  `/simplify` path strings, `SIMPLIFY_DEFAULT_VERSION`, `SimplifyOutput`→`CarePlanInternal`,
  `simplified_care_plan`→`care_plan` (inner key), and `"simplify_outputs"`→`"care_plan_outputs"`
  references.

**Add new route tests (PRD §7):** items 1–9 in PRD §7 — note the resolved decisions:
- #1 asserts the inner key is `care_plan` and `simplified_care_plan` is **absent**.
- #2 asserts single-serialize INCLUDING persistence (the persisted dict == the response dict).
- #5 asserts `/simplify*` → **404 unconditionally** (HARD CUT, no alias).
- #7 asserts `session_id` from `X-Session-Id`→UUID, **never** `user_id`.
- #9 asserts grade reads collection `"care_plan_outputs"`.

**Acceptance:** `pytest backend/tests` green; no test references `/simplify`, `simplify_v1_1`,
`run_v1_pipeline`, `SIMPLIFY_DEFAULT_VERSION`, `save_simplify_output`, `simplified_care_plan`, or
`"simplify_outputs"`. (No alias tests — `/simplify*` is a hard 404.)

**Depends on:** Tasks 1–9.

---

## Summary of what requires you (not a dev agent)

All design questions are resolved (PRD §9). Remaining items are deploy/ops actions only:

1. **Rename the deploy env var** `SIMPLIFY_DEFAULT_VERSION` → `CARE_PLAN_DEFAULT_VERSION` in Cloud
   Run / deploy config / secrets (PRD §8.2). Code change alone is not enough.
2. **Coordinate the frontend (SP5) lockstep deploy** of the new `/care_plan*` paths AND the `care_plan`
   inner key. FE + BE deploy together — there is NO alias window (PRD §6, §8.3).
3. **SP4 boundary:** confirm SP4 owns/has-landed the `session_id` fallback (`X-Session-Id`→UUID, never
   `user_id`) so removing the dead `appointment_id` branch (Task 9) does not regress trace grouping
   (PRD §8.5).
4. **Metric/log name renames** (`simplify_*` → `care_plan_*`) create new series; old `simplify_*`
   series stop entirely. Update Monitoring dashboards/alerts to the new names (PRD §8.6, §9.3).

Resolved (no action needed beyond the deploy):
- **Hard cut** of `/simplify*` — no alias, no redirect (PRD §9.1).
- **Inner key is `care_plan`** — hard flip, no `simplified_care_plan` alias (PRD §9.2).
- **Firestore collection renamed** `simplify_outputs` → `care_plan_outputs` in code; no migration
  (PRD §9.4).
- **Single serialize including persistence** (PRD §9.5).
- **Envelope class name is `CarePlanInternal`** (PRD §9.6).
- **Version is read from the request body** via a `PIPELINES` registry, built to add `v1-3` easily
  (PRD §9.7).
