# SP06 Batch + Job-Creation Route Hardening — TASKS

## Prerequisites

Harden the two job-creation routes (`POST /care_plan/batch/jobs`, `POST /care_plan/jobs`) by replacing manual body parsing with strict Pydantic request models, adding outer error handling and Markers instrumentation, swapping inline job-doc dicts for SP05 `JobDoc` factories, and turning `routes/batch.py` into `routes/batch_utils.py` (dead helpers removed).

Assumes **SP01–SP05 are complete and deployed**:
- **SP01** — unified error envelope: `make_error_response(ErrorCode.<X>, request.path, details).to_dict()`; codes `INPUT_VALIDATION_ERROR`, `BATCH_INVALID_SELECTION`, `BATCH_TOO_LARGE`, `INTERNAL_ERROR` already in the registry.
- **SP02** — constants/config: `Constants.PIPELINE_VERSION_V1_2`, `Constants.MAX_BATCH_RUNS`, and a nested `Constants.Athena.AthenaSourceKind` enum/set with members `ATHENA_ENCOUNTER` (`"athena_encounter"`) and `ATHENA_CLINICAL_DOC` (`"athena_clinical_doc"`).
- **SP03** — reorganized `backend/models/` package (this SP adds `models/batch_requests.py` there).
- **SP04** — athena typed API (no direct work here).
- **SP05** — `backend/models/job.py` exposes `JobDoc` with `for_gcs_dataset(...)`, `for_athena(...)`, `for_single(...)` factories that return the Firestore payload dict.

> Note: On the current branch `models/job.py`, `Constants.Athena.AthenaSourceKind`, and `Markers.Batch` do not yet exist — they arrive with SP02/SP05. These tasks are written against those APIs per the strict ship order. If a referenced SP05/SP02 symbol's signature differs at implementation time, adjust the call site to match the upstream signature; the approach (typed model + factory) is locked.

> Note (Q3): GCS `gcs_dataset` selections **gain an explicit `input_source_kind: "gcs_dataset"` field**. The discriminated union requires the discriminator on every member. Task 06.8 covers the matching frontend change so the request shape stays valid end-to-end.

> Note (Q2): `_grading_enabled_from_request` in `routes/care_plan.py` is **deleted outright** (no stub, no `# TODO(SP07)` comment). SP07–SP10 run in order after SP06, so removing it now is safe. All callers are migrated in this SP.

---

## Tasks

### Task 06.1: Create `models/batch_requests.py` with shared grading coercion + request models

- **Goal:** Introduce a single canonical module holding the `grading_enabled` coercion helper, the `Selection` discriminated union, and the two top-level request models.
- **Files:** `backend/models/batch_requests.py` (new)
- **Steps:**
  1. Create `backend/models/batch_requests.py`.
  2. Define `_TRUTHY = {"1", "true", "yes", "on"}` and `def _coerce_grading_enabled(v) -> bool:` returning `v` if `isinstance(v, bool)` else `str(v).strip().lower() in _TRUTHY`.
  3. Define three per-kind selection models using `utils.constants.Constants.Athena.AthenaSourceKind` literal values:
     - `AthenaEncounterSelection`: `input_source_kind: Literal["athena_encounter"]`; `athena_practice_id: str = ""`, `athena_patient_id: str = ""`, `athena_encounter_id: str`, `athena_document_id: str | None = None`, `athena_api_path: str = ""`; `@model_validator(mode="after")` raising `ValueError("athena_encounter requires athena_encounter_id")` when `athena_encounter_id` is empty.
     - `AthenaClinicalDocSelection`: `input_source_kind: Literal["athena_clinical_doc"]`; `athena_encounter_id: str | None = None`, `athena_document_id: str` (required); validator raising `ValueError("athena_clinical_doc requires athena_document_id")` when empty.
     - `GcsDatasetSelection`: `input_source_kind: Literal["gcs_dataset"]`; `group: str`, `files: list[str]`, `inputs: str | list[str]`; `@model_validator(mode="after")` enforcing non-empty `group` (`"Selection is missing group"`), non-empty all-string `files` (`f"Selection for {self.group} must include files"`), and `inputs == "all"` or a list of strings (`f"Selection for {self.group} must include inputs"`).
  4. Define `Selection = Annotated[Union[AthenaEncounterSelection, AthenaClinicalDocSelection, GcsDatasetSelection], Field(discriminator="input_source_kind")]`.
  5. Define `BatchJobsRequest(BaseModel)`: `selections: list[Selection] = Field(min_length=1)`, `version: str = Constants.PIPELINE_VERSION_V1_2`, `grading_enabled: bool = False`; add `@model_validator(mode="before") @classmethod _coerce_grading(cls, data)` that runs `data["grading_enabled"]` through `_coerce_grading_enabled` when present in a dict.
  6. Define `SingleJobRequest(BaseModel)`: `version: str = Constants.PIPELINE_VERSION_V1_2`, `grading_enabled: bool = True` (default `True` matches the old `_grading_enabled_from_request` default); same `_coerce_grading` before-validator.
  7. Add `from __future__ import annotations` and all imports (`Annotated, Literal, Union` from `typing`; `BaseModel, Field, model_validator` from `pydantic`; `Constants` from `utils.constants`).
- **Acceptance:**
  - `from models.batch_requests import BatchJobsRequest, SingleJobRequest, Selection, _coerce_grading_enabled` succeeds.
  - `BatchJobsRequest.model_validate({"selections": [{"input_source_kind": "gcs_dataset", "group": "sp1", "files": ["q.txt"], "inputs": "all"}]})` parses; `.version == "v1-2"`, `.grading_enabled is False`.
  - `BatchJobsRequest.model_validate({"selections": [{"input_source_kind": "athena_encounter", "athena_encounter_id": ""}]})` raises `pydantic.ValidationError`.
  - `_coerce_grading_enabled("yes") is True`, `_coerce_grading_enabled("false") is False`, `_coerce_grading_enabled(True) is True`.
- **Commit:** `feat(models): add batch_requests pydantic models for job-creation routes`

> Note: `_resolve_requested_runs` (Task 06.4) still performs dataset-existence/file-membership checks against `list_datasets()`. `GcsDatasetSelection` only validates shape (presence/types), not catalog membership — the two layers are complementary, not redundant.

---

### Task 06.2: Add `Markers.Batch` leaf

- **Goal:** Register two batch operation markers so both handlers can emit telemetry.
- **Files:** `backend/utils/markers/markers.py`
- **Steps:**
  1. Inside `class Markers`, add a nested `class Batch:` alongside `CarePlan`, `Grading`, `Http`.
  2. Add `@code_marker("batch.create_jobs") class CreateJobs(CodeMarker): pass`.
  3. Add `@code_marker("batch.create_single_job") class CreateSingleJob(CodeMarker): pass`.
- **Acceptance:**
  - `from utils.markers.markers import Markers` then `Markers.Batch.CreateJobs.name() == "batch.create_jobs"` and `Markers.Batch.CreateSingleJob.name() == "batch.create_single_job"`.
- **Commit:** `feat(markers): add Markers.Batch leaf for job-creation routes`

---

### Task 06.3: Rename `routes/batch.py` → `routes/batch_utils.py`; delete dead helpers

- **Goal:** Reframe the file as a utility module, removing five helpers that have zero callers and `_grading_enabled` (now centralized in `models/batch_requests`).
- **Files:** `backend/routes/batch.py` → `backend/routes/batch_utils.py` (rename via `git mv`); `backend/routes/__init__.py`; `backend/routes/batch_jobs.py`
- **Steps:**
  1. `git mv backend/routes/batch.py backend/routes/batch_utils.py`.
  2. In `batch_utils.py`, update the file docstring to: `"""Batch utilities: timestamp helper, GCS selection resolver, and deprecated 410 stub (removal: SP07)."""`.
  3. Delete these functions entirely: `_grading_enabled` (lines ~32–35), `_pipeline_for_version` (~38–41), `_combined_text_for_dataset_input` (~89–97), `_output_name` (~100–109), `_batch_progress_error` (~112–121), `_pipeline_kwargs_for_batch` (~124–133).
  4. Remove now-unused imports left behind by the deletions: `Callable, Generator` from `typing`; `from routes.care_plan import _extract_text_from_bytes, run_care_plan_pipeline`; `from utils.firebase import save_care_plan_output`; and `read_dataset_file` from `utils.preset_data` (keep `list_datasets`, still used by `_resolve_requested_runs`). Verify each removed import has no remaining reference in the file before deleting.
  5. **Keep** `batch_bp`, the 410 stub `care_plan_batch_sse_deprecated`, `_batch_timestamp`, and `_resolve_requested_runs` unchanged.
  6. In `routes/__init__.py` line 2, change `from routes.batch import batch_bp` → `from routes.batch_utils import batch_bp`.
  7. In `routes/batch_jobs.py` line 11, change `from routes.batch import _resolve_requested_runs, _batch_timestamp` → `from routes.batch_utils import _resolve_requested_runs, _batch_timestamp`.
- **Acceptance:**
  - `python -c "import routes"` succeeds; no module references `routes.batch`.
  - `from routes.batch_utils import _resolve_requested_runs, _batch_timestamp, batch_bp, care_plan_batch_sse_deprecated` succeeds.
  - `from routes.batch_utils import _grading_enabled` raises `ImportError`; same for `_pipeline_for_version`, `_combined_text_for_dataset_input`, `_output_name`, `_batch_progress_error`, `_pipeline_kwargs_for_batch`.
  - `grep -rn "routes.batch import\|routes/batch\b\|from routes import batch\b" backend/` returns no hits referencing the old module.
- **Commit:** `refactor(routes): rename batch.py to batch_utils.py and remove dead helpers`

---

### Task 06.4: Rewrite `create_care_plan_batch_jobs` on `BatchJobsRequest` + JobDoc factories + Markers + outer try/except

- **Goal:** Replace all manual parsing, the function-local `ATHENA_KINDS`, inline coercion, the two inline 20-key job dicts, and the mid-loop required-field checks with the typed model, SP05 factories, and full error handling/instrumentation.
- **Files:** `backend/routes/batch_jobs.py`
- **Steps:**
  1. Update imports: add `from models.batch_requests import BatchJobsRequest, AthenaEncounterSelection, AthenaClinicalDocSelection, GcsDatasetSelection`; `from models.job import JobDoc`; `from utils.markers.markers import Markers`; `from utils.markers.marker import Scope`; `from pydantic import ValidationError`.
  2. Restructure the handler so its full body runs inside `Markers.Batch.CreateJobs.execute(_handler)`, where `_handler(scope: Scope)` contains everything and the route function returns its result.
  3. Wrap the `_handler` body in an outer `try/except Exception` → `logger.exception("create_care_plan_batch_jobs: unexpected error")` and `return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500`.
  4. **Parse + validate** (replaces lines 22–41): `try: req = BatchJobsRequest.model_validate(request.get_json(silent=True) or {})` `except ValidationError as exc:` → `make_error_response(ErrorCode.INPUT_VALIDATION_ERROR, request.path, {"detail": str(exc)}).to_dict(), 400`. Use `req.version`, `req.grading_enabled`.
  5. **Partition** (replaces lines 43–52, removing `ATHENA_KINDS`): `athena_selections = [s for s in req.selections if isinstance(s, (AthenaEncounterSelection, AthenaClinicalDocSelection))]`; `gcs_selections = [s for s in req.selections if isinstance(s, GcsDatasetSelection)]`.
  6. **Resolve GCS runs:** call `_resolve_requested_runs([s.model_dump() for s in gcs_selections])` inside the existing inner `try/except (ValueError, FileNotFoundError)` → `BATCH_INVALID_SELECTION` 400 (kept).
  7. Compute `total_count = len(runs) + len(athena_selections)`; keep the `Constants.MAX_BATCH_RUNS` check → `BATCH_TOO_LARGE` 400.
  8. **Instrument:** after partitioning/resolving, `scope.add_many({"batch_size": total_count, "athena_count": len(athena_selections), "gcs_count": len(runs), "grading_enabled": req.grading_enabled, "version": req.version, "source_kind": _source_kind_label(len(athena_selections), len(runs))})`. Add a small module-level helper `_source_kind_label(athena_n, gcs_n) -> str` returning `"all_athena"` / `"all_gcs"` / `"mixed"` / `"empty"`. (Q5 — derived dimension included.)
  9. **GCS job docs:** in the `for group, input_id, files in runs:` loop, replace the inline dict (lines 89–119) with `job_doc = JobDoc.for_gcs_dataset(user_id=user_id, batch_run_id=batch_run_id, batch_group_id=batch_group_ids[group], group=group, input_id=input_id, files=files, version=req.version, grading_enabled=req.grading_enabled, now=now)`. Keep `create_job_doc(...)`, the `enqueue_job` inner try/except, and `job_ids.append(...)`.
  10. **Athena job docs:** in the `for sel in athena_selections:` loop, delete the per-field locals (lines 146–151) and the manual required-field checks (lines 153–168) — they are enforced by the model. Compute `source_filename` from typed attrs (`f"athena_encounter_{sel.athena_encounter_id}"` for `AthenaEncounterSelection`, else `f"athena_doc_{sel.athena_document_id}"`). Replace the inline dict (lines 171–202) with `job_doc = JobDoc.for_athena(user_id=user_id, batch_run_id=batch_run_id, batch_group_id=athena_batch_group_id, selection=sel, version=req.version, grading_enabled=req.grading_enabled, now=now)`. Keep `create_job_doc`, the `enqueue_job` inner try/except, `job_ids.append`.
  11. Final `return jsonify({"batch_run_id": batch_run_id, "job_ids": job_ids}), 202` (unchanged).
  12. Standardize section-header comments (Task 06.7 covers exact wording).
- **Acceptance:**
  - POST `{}` → 400, `error.code == "INPUT_VALIDATION_ERROR"`.
  - POST `{"selections": []}` → 400.
  - POST one valid GCS + one valid Athena selection → 202 with `batch_run_id` and two `job_ids`; both `create_job_doc` and `enqueue_job` invoked twice (mockable in tests).
  - POST `athena_encounter` without `athena_encounter_id` → 400 `INPUT_VALIDATION_ERROR`.
  - POST `{"grading_enabled": "on", "selections": [<valid>]}` → resulting `JobDoc` carries `grading_enabled True`.
  - Mocking `create_job_doc` to raise `RuntimeError` → 500 with `ApiResponse` JSON envelope (not a Flask HTML traceback).
  - No reference to `ATHENA_KINDS` remains; no inline `grading_enabled` coercion remains; no inline job-doc dicts remain.
- **Commit:** `refactor(batch_jobs): use BatchJobsRequest, JobDoc factories, markers, and outer error handling`

> Note: `_resolve_requested_runs` keeps its `list[dict]` contract; pass `s.model_dump()` rather than changing its signature (out of scope per Non-Goals). SP05's `for_athena` takes the typed `Selection` instance; if SP05's signature instead wants a plain dict, pass `sel.model_dump()` and adjust.

---

### Task 06.5: Rewrite `create_care_plan_job` on `SingleJobRequest` + JobDoc factory + Markers + outer try/except

- **Goal:** Read `grading_enabled`/`version` from a parsed `SingleJobRequest` (removing the `_grading_enabled_from_request` dependency), replace the inline job dict with `JobDoc.for_single`, and add outer error handling + Markers while preserving the multipart path and the 400 input-validation catch.
- **Files:** `backend/routes/care_plan_jobs.py`
- **Steps:**
  1. Update imports: drop `_grading_enabled_from_request` from the `from routes.care_plan import (...)` block (keep `_resolve_uploaded_files`, `upload_combined_pdf`, `_fetch_from_gcs`, `_extract_text_from_bytes`, `_allowed`). Add `from models.batch_requests import SingleJobRequest`; `from models.job import JobDoc`; `from utils.markers.markers import Markers`; `from utils.markers.marker import Scope`.
  2. In `_resolve_input_for_job`, replace `version = (...)` and `grading_enabled = _grading_enabled_from_request()` with one parse: build `req = SingleJobRequest.model_validate({"version": request.form.get("version") or (request.get_json(silent=True) or {}).get("version"), "grading_enabled": request.form.get("grading_enabled", (request.get_json(silent=True) or {}).get("grading_enabled")) })` — drop keys whose value is `None` before validation so model defaults (`"v1-2"`, `True`) apply. Use `req.version` and `req.grading_enabled` in all three returned dicts. (Multipart dispatch over `text`/`files`/`doc_id` is otherwise unchanged.)
  3. Wrap the handler body in `Markers.Batch.CreateSingleJob.execute(_handler)`; `_handler(scope)` holds the logic and the route returns its result.
  4. Add `scope.add_many({"grading_enabled": <resolved>, "version": <resolved>})` once `input_fields` is resolved (read from `input_fields["grading_enabled"]` / `input_fields["input_version"]`).
  5. Keep the existing `try: input_fields = _resolve_input_for_job(user_id) except (ValueError, FileNotFoundError): return INPUT_VALIDATION_ERROR 400` as a **local** catch nested inside the new outer try.
  6. Add an outer `try/except Exception` around the remaining body → `logger.exception("create_care_plan_job: unexpected error")` + `INTERNAL_ERROR` 500.
  7. Replace the inline job-doc dict (lines 101–120) with `job_doc = JobDoc.for_single(user_id=user_id, trace_id=trace_id, input_fields=input_fields, now=now)`. Keep `create_job_doc`, the `enqueue_job` inner try/except, and `return jsonify({"job_id": job_id}), 202`.
- **Acceptance:**
  - POST JSON `{"text": "hello"}` (no `grading_enabled`) → `JobDoc` `grading_enabled True` (the `SingleJobRequest` default).
  - POST JSON `{"text": "hello", "grading_enabled": "false"}` → `grading_enabled False`.
  - POST with neither text/files/doc_id → 400 `INPUT_VALIDATION_ERROR` (local catch).
  - Mock `create_job_doc` to raise → structured 500 JSON envelope.
  - No import of `_grading_enabled_from_request` remains in this file; no inline job-doc dict remains.
- **Commit:** `refactor(care_plan_jobs): use SingleJobRequest, JobDoc.for_single, markers, and outer error handling`

> Note: multipart/form-data takes priority over JSON for the same field name (mirrors the original `request.form.get(...) or json_data.get(...)` precedence). Preserve that precedence when building the dict in step 2.

---

### Task 06.6: Delete `_grading_enabled_from_request` from `care_plan.py` (Q2)

- **Goal:** Remove the now-orphaned bool-coercion helper entirely (no stub, no TODO).
- **Files:** `backend/routes/care_plan.py`
- **Steps:**
  1. Confirm no remaining references: `grep -rn "_grading_enabled_from_request" backend/` should show only the definition in `care_plan.py` after Task 06.5 lands (the `care_plan_jobs.py` import was removed there).
  2. Delete the `def _grading_enabled_from_request() -> bool:` function (lines ~241–248) in full.
  3. Remove any import that becomes unused solely because of this deletion (verify before removing — `request` is used elsewhere in the file, do not remove it).
- **Acceptance:**
  - `grep -rn "_grading_enabled_from_request" backend/` returns zero hits.
  - `python -c "import routes.care_plan"` succeeds.
- **Commit:** `refactor(care_plan): remove orphaned _grading_enabled_from_request helper`

---

### Task 06.7: Standardize section-header comments in `batch_jobs.py`

- **Goal:** Make the handler's structure scannable with consistent box-drawing headers.
- **Files:** `backend/routes/batch_jobs.py`
- **Steps:**
  1. Ensure these headers appear (add/standardize wording and `─` length) in order: `# ── Parse and validate request ──`, `# ── Partition selections ──`, `# ── Resolve GCS runs ──`, `# ── Check total job count ──`, `# ── GCS dataset job docs ──`, `# ── Athena job docs ──`.
  2. Remove any redundant/duplicate inline comments superseded by the headers.
- **Acceptance:** `grep -c "# ── " backend/routes/batch_jobs.py` returns at least 6; headers read top-to-bottom in the order above.
- **Commit:** `style(batch_jobs): standardize section-header comments`

> Note: This is cosmetic and can be folded into Task 06.4's commit if implemented together; kept separate so 06.4's diff stays focused on behavior.

---

### Task 06.8: Add `input_source_kind: "gcs_dataset"` to GCS selections on the frontend (Q3)

- **Goal:** The discriminated union requires the discriminator on every selection; GCS selections previously omitted it. Add it where the frontend builds the batch request payload.
- **Files:** frontend selection-payload builder (locate with `grep -rn "selections" frontend/src --include=*.ts --include=*.tsx` and `grep -rn "/care_plan/batch/jobs" frontend/src`).
- **Steps:**
  1. Find where the `selections` array for `POST /care_plan/batch/jobs` is assembled for dataset (GCS) selections.
  2. Add `input_source_kind: "gcs_dataset"` to each GCS selection object alongside `group`, `files`, `inputs`.
  3. Confirm Athena selections already include their `input_source_kind` (`"athena_encounter"` / `"athena_clinical_doc"`); add if missing.
  4. Update any TypeScript type/interface for the selection payload to include the literal `input_source_kind` field.
- **Acceptance:**
  - The request body sent for a GCS batch includes `"input_source_kind": "gcs_dataset"` on every dataset selection (verify via Vitest assertion on the payload builder or a network/unit snapshot).
  - Existing frontend selection tests pass.
- **Commit:** `feat(frontend): add input_source_kind discriminator to gcs_dataset selections`

> Note (Q3): This makes the request shape strict end-to-end rather than relying on a server-side GCS fallback. If the frontend builder cannot be located (path differs), report `needs input:` with the grep results rather than guessing a file.

---

### Task 06.9: Backend tests — batch_jobs

- **Goal:** Cover validation, coercion, defaults, and the 500 safety net for the batch handler.
- **Files:** `backend/tests/routes/test_batch_jobs.py`
- **Steps:** Add/extend tests:
  1. `test_missing_selections_returns_400` — POST `{}` → 400, `error.code == "INPUT_VALIDATION_ERROR"`.
  2. `test_empty_selections_returns_400` — POST `{"selections": []}` → 400.
  3. `test_athena_encounter_missing_encounter_id_returns_400` — 400, `INPUT_VALIDATION_ERROR`.
  4. `test_athena_clinical_doc_missing_document_id_returns_400` — 400, `INPUT_VALIDATION_ERROR`.
  5. `test_grading_enabled_string_coercion` — `{"grading_enabled": "yes", "selections": [<valid gcs>]}`; assert the captured `JobDoc`/`create_job_doc` payload has `grading_enabled` `True` (mock `create_job_doc`, `enqueue_job`, `_resolve_requested_runs`).
  6. `test_version_defaults_to_v1_2` — no `version` key; assert captured doc `input_version == "v1-2"`.
  7. `test_unhandled_exception_returns_500_json` — patch `create_job_doc` to raise `RuntimeError`; assert 500 and a JSON `ApiResponse` envelope (has `error.code == "INTERNAL_ERROR"`), not HTML.
- **Acceptance:** `pytest backend/tests/routes/test_batch_jobs.py` passes; all seven cases present.
- **Commit:** `test(batch_jobs): cover validation, coercion, defaults, and 500 safety net`

---

### Task 06.10: Backend tests — care_plan_jobs

- **Goal:** Cover JSON grading coercion and the 500 safety net for the single-job handler.
- **Files:** `backend/tests/routes/test_care_plan_jobs.py`
- **Steps:** Add tests:
  1. `test_grading_enabled_false_string_coercion` — POST JSON `{"text": "hello", "grading_enabled": "false"}`; assert captured doc `grading_enabled` `False`.
  2. `test_grading_enabled_default_true` — POST JSON `{"text": "hello"}`; assert captured doc `grading_enabled` `True`.
  3. `test_unhandled_exception_returns_500_json` — patch `create_job_doc` to raise; assert structured 500 envelope.
- **Acceptance:** `pytest backend/tests/routes/test_care_plan_jobs.py` passes.
- **Commit:** `test(care_plan_jobs): cover grading coercion default and 500 safety net`

---

### Task 06.11: Tests — markers + batch_utils symbol surface

- **Goal:** Lock the new marker names and the post-rename module surface.
- **Files:** `backend/tests/utils/test_markers.py` (new), `backend/tests/routes/test_batch_utils.py` (new)
- **Steps:**
  1. `test_markers.py`: `test_batch_create_jobs_marker_registered` asserts `Markers.Batch.CreateJobs.name() == "batch.create_jobs"`; `test_batch_create_single_job_marker_registered` asserts `... == "batch.create_single_job"`.
  2. `test_batch_utils.py`: assert `_resolve_requested_runs` and `_batch_timestamp` are importable from `routes.batch_utils`; assert each of `_pipeline_for_version`, `_combined_text_for_dataset_input`, `_output_name`, `_batch_progress_error`, `_pipeline_kwargs_for_batch`, `_grading_enabled` raises `ImportError` when imported from `routes.batch_utils` (use `pytest.raises(ImportError)` around an `importlib`/`from ... import` guarded helper, or assert `not hasattr(module, name)`).
  3. Add a test asserting `GET`/`POST /care_plan/batch` still returns 410 (the deprecated stub stays live).
- **Acceptance:** `pytest backend/tests/utils/test_markers.py backend/tests/routes/test_batch_utils.py` passes.
- **Commit:** `test(markers,batch_utils): lock new marker names and post-rename surface`

---

## Verification

Run from `/root/projects/juno/backend` (and repo root for frontend):

```bash
# Backend — targeted
pytest backend/tests/routes/test_batch_jobs.py \
       backend/tests/routes/test_care_plan_jobs.py \
       backend/tests/routes/test_batch_utils.py \
       backend/tests/utils/test_markers.py -q

# Backend — full suite (no regressions)
pytest backend -q

# Import sanity (rename + deletions)
python -c "import routes; from routes.batch_utils import _resolve_requested_runs, _batch_timestamp, batch_bp"
grep -rn "routes.batch import\|from routes import batch\b" backend/   # expect: no old-module hits
grep -rn "_grading_enabled_from_request\|ATHENA_KINDS" backend/        # expect: zero hits

# Frontend
npm --prefix frontend run lint
npx --prefix frontend vitest run
```

**Definition of done:**
- All targeted tests pass and the full backend suite is green (no regressions).
- `routes/batch.py` no longer exists; `routes/batch_utils.py` exists with only `batch_bp`, `care_plan_batch_sse_deprecated` (410), `_batch_timestamp`, `_resolve_requested_runs`.
- The five dead helpers, `_grading_enabled`, and `_grading_enabled_from_request` are gone repo-wide (grep clean).
- Both handlers parse via Pydantic models, run under `Markers.Batch.*`, have an outer `try/except` → `INTERNAL_ERROR` 500 JSON, and build job docs via `JobDoc` factories (no inline job-doc dicts, no inline `grading_enabled` coercion, no `ATHENA_KINDS`).
- External JSON request/response shapes are byte-for-byte identical except GCS selections now carry `input_source_kind: "gcs_dataset"` (frontend updated in Task 06.8); `GET /care_plan/batch` still returns 410.
- Each task committed separately with its listed conventional-commit message.
