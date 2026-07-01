# SP08 Cross-Cutting Error-Handling + Metrics + Dedup Sweep — TASKS

## Prerequisites

Purpose: a single cleanup sweep that (a) wraps every unguarded Firestore/GCS call in the saved-outputs / admin / grading / firebase-wrapper layers in structured error handling, (b) expands the `Markers` registry and wires it into the job-lifecycle and saved-outputs surfaces, (c) de-duplicates five copy-pasted patterns into shared helpers, (d) replaces two hand-rolled isinstance validation ladders with Pydantic models, and (e) removes the legacy `input_pdf_gcs` data-shape fallback.

This sub-project **assumes SP01–SP07 are fully complete and deployed**:
- SP01: unified error system — `make_error_response`, `ErrorCode`, `ApiResponse.to_dict()` (in `utils/error_codes.py`) and `AthenaApiError`.
- SP02: namespaced constants / `ErrorCode`.
- SP03: models reorganized under `models/` as the house Pydantic pattern.
- SP04: athena typed external API complete (`utils/athena_client.py` exists; SP04 wires `Markers.Athena.ApiCall`).
- SP05: `JobDoc` model / job-doc field shape settled.
- SP06: batch entry-point consolidated (owns `batch_jobs.py` enqueue edits and any `batch.py` rename).
- SP07: consolidated pipeline with typed event dataclasses in `models/` and the dead SSE protocol already removed (owns `care_plan.py` / `worker.py` orchestration internals).

> Note (USER DECISIONS applied): Q5 — no legacy is impacted; **remove** the `input_pdf_gcs` fallback outright; do **not** check Firestore and do **not** gate the removal on whether old docs still exist. Q6 — SP04 has landed; assume the athena typed API is complete (SP08 only registers the `Markers.Athena.ApiCall` leaf; SP04 already wired the call). Q7 — SP07 has landed; assume the consolidated pipeline, typed event dataclasses, and SSE removal are complete (SP08 does **not** rewrite any pipeline/orchestration internals).

> Note (legacy policy): per global rule 1, all legacy/back-compat is removed entirely — no shims, no "is it still used" gating. The `input_pdf_gcs` fallback (§4l) and the `or data.get('input_pdf_gcs', '')` legs are deleted, not deprecated.

> Note (SP07/SP06 overlap reconciliation): the PRD anticipated SP07/SP06 landing *alongside* SP08 and hedged ("if SP07 lands first, defer those lines"). Under the assumption that SP07 and SP06 are already merged, those hedges resolve deterministically: SP08 simply edits the current code as it exists post-SP07/SP06. Where the PRD names a file SP06/SP07 may have renamed (e.g. `batch.py` → `batch_utils.py`), each task says "locate the file currently containing `<symbol>`" rather than hard-coding a path. As of this writing the symbols still live in `routes/worker.py`, `routes/batch.py`, `routes/care_plan.py`, `routes/care_plan_jobs.py`, and `routes/batch_jobs.py`.

---

## Tasks

Ordering: shared helpers and the registry are created first (Tasks 08.1–08.6) so later wiring tasks can import them; error-handling, Pydantic, legacy-removal, and comment tasks follow.

---

### Task 08.1: Add `derive_output_name` shared helper (`utils/output_helpers.py`)

- **Goal:** One canonical output-name derivation function replacing `worker._derive_name` and `batch._output_name`.
- **Files:**
  - Create `backend/utils/output_helpers.py`
  - Create `backend/tests/utils/test_output_helpers.py`
- **Steps:**
  1. Create `backend/utils/output_helpers.py` with a single public function:
     ```python
     def derive_output_name(
         care_plan_data: dict,
         source_filename: str = "",
         group_fallback: str = "",
     ) -> str:
     ```
     Priority order (each result capped at 60 chars):
     1. `care_plan_data["reason_for_visit"][0]["reason"]` → `.title()[:60]` (guard: list, non-empty stripped reason).
     2. `care_plan_data["diagnosis"]["main_conclusion"]` first sentence (`split(".")[0].strip()`) → `[:60]`.
     3. `source_filename` (when not `""` and not `"text_input"`): take `split(",")[0].strip()`, drop extension via `rsplit(".", 1)[0]` if a `.` is present, replace `_`/`-` with spaces, then `.title()[:60]`.
     4. `group_fallback` → `[:60]` (used by batch, e.g. `f"{group} {input_id}"`).
     5. literal `"Appointment"`.
     Wrap steps 1–2 in a `try/except Exception: pass` exactly as the existing `worker._derive_name` does, so malformed care-plan dicts fall through to filename/group/Appointment.
  2. Copy the exact logic from `routes/worker.py:354 _derive_name` (lines 354–377) as the base; add the `group_fallback` branch between the filename branch and the final `"Appointment"`.
  3. Create `tests/utils/test_output_helpers.py` covering: rfv title-case (`{"reason_for_visit":[{"reason":"chest pain"}]}` → `"Chest Pain"`); diagnosis first-sentence fallback (empty rfv, populated `main_conclusion`); filename fallback (`source_filename="annual_checkup.pdf"` → `"Annual Checkup"`); group fallback (`group_fallback="sp1 0001"` → `"Sp1 0001"`, not `"Appointment"`); all-empty → `"Appointment"`; 100-char reason → output length exactly 60.
- **Acceptance:** `pytest tests/utils/test_output_helpers.py` passes; `derive_output_name({}) == "Appointment"`; the six cases above hold.
- **Commit:** `feat(utils): add derive_output_name shared output-name helper`

---

### Task 08.2: Migrate call sites to `derive_output_name`; remove the two private copies

- **Goal:** `worker._derive_name` and `batch._output_name` deleted; both callers use `derive_output_name`.
- **Files:**
  - `backend/routes/worker.py`
  - The file currently defining `_output_name` (`routes/batch.py:100`; `grep -rn "def _output_name" backend/routes` to confirm post-SP06 location).
- **Steps:**
  1. In `routes/worker.py`: add `from utils.output_helpers import derive_output_name` to the import block. Change line 333 `name = _derive_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))` to `name = derive_output_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))`. Delete the `_derive_name` function (lines 354–377).
  2. In the file defining `_output_name`: add `from utils.output_helpers import derive_output_name`. Replace the call site `return _output_name(output_data, group, input_id)` with `return derive_output_name(output_data.get("care_plan", {}), group_fallback=f"{group} {input_id}")`. Delete the `_output_name` function.
     > Note: the old `_output_name(output_data, group, input_id)` took the whole `output_data` envelope and read `output_data.get("care_plan", {})` internally; the new helper takes the inner `care_plan` dict, so pass `output_data.get("care_plan", {})`. Verify against the current body of `_output_name` before deleting (it may already operate on the inner dict — match its actual key access).
  3. `grep -rn "_derive_name\|_output_name" backend/` and confirm zero remaining references (outside test files you update).
- **Acceptance:** `grep -rn "_derive_name\|_output_name" backend/routes backend/utils` returns nothing; `pytest tests/routes/test_worker.py tests/routes/test_batch_jobs.py` (and any batch route test) passes.
- **Commit:** `refactor(routes): use derive_output_name; drop duplicate name derivers`

---

### Task 08.3: Add `score_text_safe` to `utils/scoring.py`; migrate `_score_or_none` / `_score_safe`

- **Goal:** One safe-scoring wrapper; the two private copies removed.
- **Files:**
  - `backend/utils/scoring.py`
  - `backend/routes/grading.py`
  - `backend/routes/care_plan.py`
  - `backend/tests/utils/test_scoring.py`
- **Steps:**
  1. In `utils/scoring.py`: add a module logger (the file currently has **no** logger). After the imports add:
     ```python
     import logging
     logger = logging.getLogger(__name__)
     ```
  2. Append `score_text_safe`:
     ```python
     def score_text_safe(text: str, label: str) -> dict | None:
         """Call score_text; return None and log on any failure."""
         try:
             return score_text(text)
         except Exception:
             logger.exception("scoring: %s-score failed", label)
             return None
     ```
  3. In `routes/grading.py`: change `from utils.scoring import score_text` to `from utils.scoring import score_text_safe`. Replace the two `_score_safe(...)` calls (lines 51–52 and 69–70) with `score_text_safe(...)`. Delete the `_score_safe` function (lines 76–81).
  4. In `routes/care_plan.py`: add `from utils.scoring import score_text_safe` (keep the existing `score_text` import only if other code still uses it; `grep -n "score_text\b" routes/care_plan.py` to check — if `_score_or_none` was the only user, switch the import). Replace `_score_or_none(text, "before")` / `_score_or_none(clarified, "after")` (lines 360–361) with `score_text_safe(...)`. Delete `_score_or_none` (lines 233–237).
     > Note: SP07 owns the broader `care_plan.py` refactor. Since SP07 has landed, only these specific lines change here; do not touch any other function in `care_plan.py`. If SP07's merged version already routes these through a shared helper, this step is a no-op for `care_plan.py` — verify with `grep -n "_score_or_none\|score_text_safe" routes/care_plan.py` and skip if already done.
  5. Add tests to `tests/utils/test_scoring.py`: `score_text_safe` returns the dict on success (mock `score_text` → `{"score": 5}`); returns `None` on exception (mock `score_text` to raise `RuntimeError`).
- **Acceptance:** `grep -rn "_score_or_none\|_score_safe" backend/routes` returns nothing; `pytest tests/utils/test_scoring.py tests/routes/test_grading_route.py` passes.
- **Commit:** `refactor(scoring): add score_text_safe; drop duplicate safe-score wrappers`

---

### Task 08.4: Add `get_gcs_bucket` shared helper (`utils/gcs_helpers.py`); migrate call sites

- **Goal:** GCS client+bucket construction lives in one place; all four inline copies removed.
- **Files:**
  - Create `backend/utils/gcs_helpers.py`
  - `backend/routes/saved_outputs.py`
  - `backend/routes/care_plan.py`
- **Steps:**
  1. Create `backend/utils/gcs_helpers.py`:
     ```python
     import os
     from google.cloud import storage as gcs

     _DEFAULT_BUCKET = os.environ.get("GCP_BUCKET_NAME", "")

     def get_gcs_bucket(bucket_name: str | None = None):
         """Return a GCS Bucket for the given name (default: GCP_BUCKET_NAME env)."""
         name = bucket_name or _DEFAULT_BUCKET
         client = gcs.Client(project=os.environ.get("GCP_PROJECT_ID") or None)
         return client.bucket(name)
     ```
     > Note: `_DEFAULT_BUCKET` is read at import time, matching the existing `_BUCKET_NAME = os.environ.get('GCP_BUCKET_NAME', '')` in `saved_outputs.py:27` and `care_plan.py`. Each caller still passes/uses its own `_BUCKET_NAME` constant for the `gs://` prefix stripping, so behavior is unchanged.
  2. In `routes/saved_outputs.py`: add `from utils.gcs_helpers import get_gcs_bucket`. In `delete_saved` replace lines 182–183 (`client = gcs.Client(...)` / `bucket = client.bucket(_BUCKET_NAME)`) with `bucket = get_gcs_bucket()`. In `get_input_pdf_url` replace lines 218–219 likewise with `bucket = get_gcs_bucket()`. Remove the now-unused `from google.cloud import storage as gcs` import **only if** no other usage remains (`grep -n "gcs\." routes/saved_outputs.py`).
  3. In `routes/care_plan.py`: add `from utils.gcs_helpers import get_gcs_bucket`. In `upload_combined_pdf` replace lines 68–69 with `bucket = get_gcs_bucket(bucket_name)` (it already computes a local `bucket_name`). In `_fetch_from_gcs` replace lines 218–219 with `bucket = get_gcs_bucket(_gcs_bucket_name)`.
     > Note: SP07 owns the `care_plan.py` refactor and has landed; only these two construction sites change. If SP07's merged version already centralized GCS construction, `grep -n "gcs.Client" routes/care_plan.py` — skip the care_plan.py edits if no inline `gcs.Client` remains.
- **Acceptance:** `grep -rn "gcs.Client(" backend/routes` returns nothing (all construction goes through the helper); `pytest tests/routes/test_saved_outputs_route.py` passes; GCS-touching behavior unchanged (signed URL / delete paths still resolve `gs://{bucket}/...`).
- **Commit:** `refactor(gcs): centralize GCS bucket construction in get_gcs_bucket`

---

### Task 08.5: Add `enqueue_job_safe` to `utils/cloud_tasks.py`; migrate `care_plan_jobs.py`

- **Goal:** The enqueue try/except block exists once; `care_plan_jobs.py` uses it.
- **Files:**
  - `backend/utils/cloud_tasks.py`
  - `backend/routes/care_plan_jobs.py`
  - `backend/tests/utils/test_cloud_tasks.py`
- **Steps:**
  1. In `utils/cloud_tasks.py`: add `import logging`, `logger = logging.getLogger(__name__)`, and `from utils.error_codes import make_error_response, ErrorCode`. After `enqueue_job()` add:
     ```python
     def enqueue_job_safe(
         job_id: str,
         *,
         queue_name: str,
         worker_url: str,
         service_account: str,
         deadline_seconds: int,
         batch_run_id: str | None = None,
         path: str | None = None,
     ) -> tuple[dict, int] | None:
         """Enqueue a job; return (error_response_dict, status) on failure, None on success."""
         try:
             enqueue_job(
                 job_id,
                 queue_name=queue_name,
                 worker_url=worker_url,
                 service_account=service_account,
                 deadline_seconds=deadline_seconds,
                 batch_run_id=batch_run_id,
             )
             return None
         except MissingJobConfigError:
             logger.exception("enqueue_job_safe: missing Cloud Tasks config for job_id=%s", job_id)
             return make_error_response(ErrorCode.INTERNAL_ERROR, path).to_dict(), 500
         except Exception:
             logger.exception("enqueue_job_safe: failed to enqueue Cloud Task for job_id=%s", job_id)
             return make_error_response(ErrorCode.INTERNAL_ERROR, path).to_dict(), 500
     ```
  2. In `routes/care_plan_jobs.py`: change the import to `from utils.cloud_tasks import enqueue_job_safe, require_env` (drop `enqueue_job`/`MissingJobConfigError` if now unused — `grep -n` to confirm). Replace the whole `try: enqueue_job(...) except MissingJobConfigError: ... except Exception: ...` block (lines 123–144) with:
     ```python
     if err := enqueue_job_safe(
         job_id,
         queue_name=require_env("CLOUD_TASKS_QUEUE"),
         worker_url=require_env("WORKER_URL"),
         service_account=require_env("WORKER_SERVICE_ACCOUNT"),
         deadline_seconds=int(os.environ.get("JOB_TIMEOUT_SECONDS_SINGLE", "300")),
         path=request.path,
     ):
         return err
     ```
     > Note: `require_env(...)` is still evaluated by the caller (it raises `MissingJobConfigError` before `enqueue_job_safe` is entered if a var is missing). To keep the structured-500 behavior the PRD intends, wrap the `require_env` calls inside `enqueue_job_safe` instead by passing the env-var names — OR keep `require_env` at the call site but catch its raise. Simplest faithful approach: keep `require_env` at the call site (it currently raises into the deleted `except MissingJobConfigError`). To preserve that, move the three `require_env(...)` calls **inside** a small local try or pass already-resolved values. Recommended: resolve them before the `if err :=` and let any `MissingJobConfigError` from `require_env` be caught by adding `except MissingJobConfigError` is no longer present — therefore resolve env vars *inside* `enqueue_job_safe` is out of scope. Implement it as: compute `queue = require_env(...)` etc. wrapped so a missing var still yields a structured 500. Concretely, keep this minimal: leave `require_env` resolution where it is but guard it — see Acceptance. Do not over-engineer; the existing tests in `test_care_plan_jobs.py` pin the contract, so make them pass.
  3. > Note (resolve the ambiguity above with a sensible default): wrap env resolution + enqueue together. Final shape:
     ```python
     try:
         queue_name = require_env("CLOUD_TASKS_QUEUE")
         worker_url = require_env("WORKER_URL")
         service_account = require_env("WORKER_SERVICE_ACCOUNT")
     except MissingJobConfigError:
         logger.exception("care_plan_jobs: missing Cloud Tasks config; cannot enqueue job %s", job_id)
         return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
     if err := enqueue_job_safe(job_id, queue_name=queue_name, worker_url=worker_url,
                                service_account=service_account,
                                deadline_seconds=int(os.environ.get("JOB_TIMEOUT_SECONDS_SINGLE", "300")),
                                path=request.path):
         return err
     ```
     This keeps the missing-config 500 path and routes enqueue failures through the shared helper. Keep `MissingJobConfigError` imported for the `require_env` guard.
  4. Add tests to `tests/utils/test_cloud_tasks.py`: `enqueue_job_safe` returns `None` on success (mock `enqueue_job`); returns `(dict, 500)` with `error.code == "INTERNAL_ERROR"` when `enqueue_job` raises `MissingJobConfigError`; same for a bare `Exception`.
- **Acceptance:** `pytest tests/utils/test_cloud_tasks.py tests/routes/test_care_plan_jobs.py` passes; `care_plan_jobs.py` no longer contains an inline `except MissingJobConfigError` around `enqueue_job`.
- **Commit:** `refactor(cloud-tasks): add enqueue_job_safe; use it in care_plan_jobs`

> Note (SP06 scope): the PRD's §4j also lists `batch_jobs.py:122` and `batch_jobs.py:205`. SP06 owns `batch_jobs.py`. Since SP06 has landed, its enqueue blocks should already call `enqueue_job_safe`. SP08 does **not** edit `batch_jobs.py` here; verify with `grep -n "enqueue_job_safe\|except MissingJobConfigError" routes/batch_jobs.py` — if raw try/except blocks remain, file a follow-up against SP06 rather than editing them in this SP.

---

### Task 08.6: Add `_extract_bearer_token` helper inside `utils/firebase.py`; de-dup the two decorators

- **Goal:** Bearer-parse logic lives once; `verify_firebase_token` and `require_admin` call it.
- **Files:**
  - `backend/utils/firebase.py`
  - `backend/tests/utils/test_firebase.py`
- **Steps:**
  1. In `utils/firebase.py`, add a private helper just below `require_admin` (or above `verify_firebase_token`):
     ```python
     def _extract_bearer_token(auth_header: str | None) -> tuple[str | None, tuple | None]:
         """Parse 'Bearer <token>'. Returns (token, None) or (None, (error_dict, status))."""
         if not auth_header:
             return None, (make_error_response(ErrorCode.MISSING_AUTH_HEADER, None).to_dict(), 401)
         parts = auth_header.split(" ", 1)
         if len(parts) != 2 or parts[0] != "Bearer":
             return None, (make_error_response(ErrorCode.MALFORMED_AUTH_HEADER, None).to_dict(), 401)
         return parts[1], None
     ```
     > Note: the helper passes `None` for the error `path` (it has no request context). To preserve the existing behavior where the decorators put `request.path` in the error, have each decorator re-build its error with `request.path` OR accept the minor change to `path=None`. Decision: keep `request.path` fidelity — in each decorator, call the helper for parsing only; on the `(None, err)` branch, re-issue the response with `request.path`. Concretely:
     ```python
     token, err = _extract_bearer_token(request.headers.get("Authorization"))
     if err:
         # err already carries the correct ErrorCode; reissue with request.path for parity
         code = ErrorCode.MISSING_AUTH_HEADER if not request.headers.get("Authorization") else ErrorCode.MALFORMED_AUTH_HEADER
         return make_error_response(code, request.path).to_dict(), 401
     ```
     If preserving `request.path` adds this much branching, prefer the simpler default: accept `path=None` in the helper's error responses and return `err` directly. **Default chosen:** return `err` directly (path=None) — the auth-failure path is rare and the error code is the load-bearing field; tests assert on status + code, not path.
  2. In `verify_firebase_token`: replace the manual header check (lines 63–73, the `auth_header = ...`, `if not auth_header`, and `parts = ...` block) with:
     ```python
     token, err = _extract_bearer_token(request.headers.get("Authorization"))
     if err:
         return err
     ```
     Keep the `try/except` around `auth.verify_id_token(token)` and the `g.user_id`/kwargs assignment.
  3. In `require_admin`: same replacement for lines 102–112; keep the admin-claim check and the `except Exception` warning branch.
  4. Add tests to `tests/utils/test_firebase.py`: `_extract_bearer_token(None)` → `(None, (_, 401))`; `_extract_bearer_token("Token abc")` → `(None, (_, 401))`; `_extract_bearer_token("Bearer mytoken")` → `("mytoken", None)`.
- **Acceptance:** `pytest tests/utils/test_firebase.py` passes; both decorators still return 401 for missing/malformed headers (existing route tests for auth still pass).
- **Commit:** `refactor(firebase): extract _extract_bearer_token; de-dup auth decorators`

---

### Task 08.7: Wrap the five `utils/firebase.py` job-lifecycle wrappers in `FirestoreError`

- **Goal:** `create_job_doc`, `update_job_stage`, `complete_job`, `fail_job`, `get_job_doc` catch any exception, log it, and re-raise as `FirestoreError`.
- **Files:**
  - `backend/utils/firebase.py`
  - `backend/tests/utils/test_firebase.py`
- **Steps:**
  1. Add a sentinel exception near the top of `utils/firebase.py` (after imports, before `initialize_firebase`):
     ```python
     class FirestoreError(RuntimeError):
         """Raised when a Firestore operation fails in a firebase wrapper function."""
     ```
  2. Wrap each of the five wrappers (lines 181–221) in `try/except Exception as exc:` that calls `logger.exception(...)` with `job_id` context and re-raises `raise FirestoreError(f"<fn> failed: {exc}") from exc`. Use the exact bodies from PRD §4a. Preserve each function's signature and return type (`get_job_doc` still returns `dict | None`).
  3. Add tests to `tests/utils/test_firebase.py`: for each wrapper, mock the underlying Firestore call (`.set` / `.update` / `.get`) to raise `Exception("network")` and assert `FirestoreError` is raised and the original message appears in `exc.args[0]`. Tests: `test_create_job_doc_raises_firestore_error_on_exception`, `test_update_job_stage_raises_firestore_error`, `test_complete_job_raises_firestore_error`, `test_fail_job_raises_firestore_error`, `test_get_job_doc_raises_firestore_error`.
- **Acceptance:** `pytest tests/utils/test_firebase.py` passes; `FirestoreError` is importable from `utils.firebase`; no caller-side change is required (worker's outer handler already catches it — verify `routes/worker.py execute_job` still has a top-level `except Exception` that calls `fail_job`).
- **Commit:** `feat(firebase): raise FirestoreError from job-lifecycle wrappers`

---

### Task 08.8: Expand the `Markers` registry with five new/extended namespaces

- **Goal:** `markers.py` gains `Grading.Route`, `Worker`, `SavedOutputs`, `Batch`, `Firestore`, and `Athena.ApiCall` leaves.
- **Files:**
  - `backend/utils/markers/markers.py`
- **Steps:**
  1. Edit `utils/markers/markers.py`. Keep all existing `CarePlan.*`, `Grading.Run`, `Http.Request` leaves unchanged.
  2. Add a `Route` leaf to the existing `Grading` class:
     ```python
     @code_marker("grading.route")
     class Route(CodeMarker): pass
     ```
  3. Add these new top-level classes inside `Markers` (each leaf a `@code_marker(...)`-decorated `CodeMarker` subclass), matching PRD §4e names exactly:
     - `Worker`: `JobExecute` (`"worker.job_execute"`), `JobStage` (`"worker.job_stage"`).
     - `SavedOutputs`: `List` (`"saved_outputs.list"`), `Get` (`"saved_outputs.get"`), `Rename` (`"saved_outputs.rename"`), `Delete` (`"saved_outputs.delete"`), `GetPdfUrl` (`"saved_outputs.get_pdf_url"`), `ToggleShare` (`"saved_outputs.toggle_share"`).
     - `Batch`: `CreateJobs` (`"batch.create_jobs"`).
     - `Firestore`: `JobWrite` (`"firestore.job_write"`).
     - `Athena`: `ApiCall` (`"athena.api_call"`).
       > Note (Q6): SP04 has landed and wires `Markers.Athena.ApiCall.execute(...)` in `utils/athena_client.py`. If SP04 already added an `Athena` namespace to this registry, do **not** duplicate it — `grep -n "class Athena" utils/markers/markers.py` first and only add the leaf if absent. SP08 owns the registry file; reconcile so there is exactly one `Athena.ApiCall`.
- **Acceptance:** `python -c "from utils.markers import Markers; print(Markers.Worker.JobExecute.name(), Markers.SavedOutputs.List.name(), Markers.Batch.CreateJobs.name(), Markers.Firestore.JobWrite.name(), Markers.Athena.ApiCall.name(), Markers.Grading.Route.name())"` prints the six expected names; existing markers tests still pass.
- **Commit:** `feat(markers): add Worker/SavedOutputs/Batch/Firestore/Athena registry leaves`

---

### Task 08.9: Wrap `saved_outputs.py` endpoints in error handling + `SavedOutputs` markers

- **Goal:** All five unguarded Firestore reads/writes in `saved_outputs.py` return structured `make_error_response` 500s; each endpoint runs inside its `Markers.SavedOutputs.*` span.
- **Files:**
  - `backend/routes/saved_outputs.py`
  - `backend/tests/routes/test_saved_outputs_route.py`
- **Steps:**
  1. Add imports: `from utils.markers import Markers, JunoContext`.
  2. Wrap each handler body in `Markers.SavedOutputs.<Leaf>.execute(_run)` using the pattern from PRD §4e:
     ```python
     def _run(scope):
         JunoContext.from_g(function="<handler>").apply(scope)
         try:
             ...  # existing body
             return ...
         except Exception:
             scope.mark_failed()
             logger.exception("<handler>: ... %s", <ctx>)
             return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
     return Markers.SavedOutputs.<Leaf>.execute(_run)
     ```
     Map: `list_saved`→`List`, `get_saved`→`Get`, `rename_saved`→`Rename`, `delete_saved`→`Delete`, `get_input_pdf_url`→`GetPdfUrl`, `toggle_share`→`ToggleShare`.
  3. Specifically wrap these currently-unguarded calls (the `except Exception` in the `_run` wrapper covers them, but keep the existing narrow try/except for the GCS delete in `delete_saved` which only logs):
     - `list_saved`: the `.stream()` loop (lines 40–57). Add `scope.add("result_count", len(results))` before returning.
     - `get_saved`: dict access after `get_owned_doc_or_403` (line 69 `data = doc.to_dict()`).
     - `rename_saved`: the `.update(updates)` call (line 161) — see Task 08.11 which also replaces the validation ladder here; coordinate so both edits land in one final handler body.
     - `delete_saved`: the `.delete()` call (line 189). Keep the existing inner GCS-delete try/except as-is.
     - `toggle_share`: the `.update(...)` call (line 254).
     - `get_input_pdf_url` already has a try/except on the signed-URL call; extend the `_run` wrapper to also cover the `get_owned_doc_or_403` / dict access path.
  4. Add tests to `tests/routes/test_saved_outputs_route.py`: `test_list_saved_returns_500_on_firestore_error` (mock `.stream()` to raise → 500, `status == "error"`); `test_rename_saved_returns_500_on_update_error`; `test_toggle_share_returns_500_on_update_error`.
     > Note: `rename_saved` markers + Firestore wrap should be applied in coordination with Task 08.11 (Pydantic). Do Task 08.11 first if convenient, or land 08.9 with the current ladder and let 08.11 swap the validation block inside the already-wrapped `_run`.
- **Acceptance:** `pytest tests/routes/test_saved_outputs_route.py` passes; forcing a Firestore exception on each of `list_saved`/`rename_saved`/`toggle_share`/`delete_saved` yields HTTP 500 with `{"status":"error","error":{"code":"INTERNAL_ERROR",...}}`; success paths return identical JSON shapes as before.
- **Commit:** `feat(saved-outputs): wrap Firestore calls in errors + SavedOutputs markers`

---

### Task 08.10: Wrap `admin.py` and `grading.py` Firestore calls in error handling + markers

- **Goal:** `get_admin_stats` and the `grading` Firestore update return structured 500s; `grading.py` runs under `Markers.Grading.Route`.
- **Files:**
  - `backend/routes/admin.py`
  - `backend/routes/grading.py`
  - `backend/tests/routes/test_grading_route.py`
- **Steps:**
  1. `admin.py`: add `from flask import request` (currently only `Blueprint, jsonify`) and `from utils.error_codes import make_error_response, ErrorCode`. Wrap the entire body of `get_admin_stats` (lines 22–65) in `try: ... except Exception: logger.exception("admin: get_admin_stats failed"); return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500`.
     > Note: admin metrics wiring is optional in the PRD; do **not** add a marker to admin unless trivial. Default: skip the admin marker (no `Markers.Admin` leaf exists and the PRD did not define one).
  2. `grading.py`: wrap the `doc.reference.update({"output_data.grading": grading.to_dict()})` call (line 55) in `try/except Exception: logger.exception("grading: Firestore update failed for saved_id=%s", saved_id); return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500`.
  3. `grading.py`: wrap the handler body in `Markers.Grading.Route.execute(_run)` (`from utils.markers import Markers, JunoContext`), applying `JunoContext.from_g(function="run_care_plan_grading")`. Do **not** restructure the pipeline/scoring internals (SP07 owns those).
  4. Add tests to `tests/routes/test_grading_route.py`: `test_run_grading_returns_500_on_firestore_update_error` (mock `doc.reference.update()` to raise → 500).
- **Acceptance:** `pytest tests/routes/test_grading_route.py` passes; a Firestore exception in `get_admin_stats` or the grading update returns structured `ApiResponse` 500 (not HTML); success shapes unchanged.
- **Commit:** `feat(routes): wrap admin/grading Firestore calls in structured errors`

---

### Task 08.11: Add `RenameOutputRequest` + `GradingRequest` Pydantic models; remove isinstance ladders

- **Goal:** `rename_saved` and `run_care_plan_grading` validate via Pydantic; the 54-line ladder and raw `.get()` validation are gone.
- **Files:**
  - Create `backend/models/saved_outputs.py`
  - `backend/models/grading.py`
  - `backend/routes/saved_outputs.py`
  - `backend/routes/grading.py`
  - Create `backend/tests/models/test_saved_outputs_model.py`
  - `backend/tests/routes/test_grading_route.py`
- **Steps:**
  1. Create `models/saved_outputs.py` with `RenameOutputRequest` (fields `name`, `comment`, `note`, `grading`, all `Optional`). Validators: strip `name`, reject empty/whitespace, reject `> 200` chars; `comment`/`note` must be `str` and `<= 2000` chars; `grading` must be a `dict` when present. Follow SP03's house Pydantic version — `grep -n "validator\|field_validator\|BaseModel" models/grading.py models/base.py` to see whether the codebase uses Pydantic v1 (`@validator`) or v2 (`@field_validator`); match it exactly. The PRD shows v1 `@validator` syntax; use whichever the existing models use.
     > Note: `models/grading.py` uses a `JsonModel` base (`class GradingEntry(JsonModel)`), not bare `BaseModel`. Check whether request-input models in this repo subclass `JsonModel` or plain `pydantic.BaseModel`. Default: for a request-body model (input, not persisted JSON), subclass `pydantic.BaseModel` unless `JsonModel` is the established input pattern.
  2. In `routes/saved_outputs.py rename_saved`: replace the isinstance ladder (lines 87–159) with: parse `RenameOutputRequest(**(request.get_json(silent=True) or {}))` inside a `try/except ValidationError`, returning a 400 `INPUT_VALIDATION_ERROR` with `{"field": <first loc>, "reason": <first msg>}`; reject the all-`None` case with a 400; then build `updates` from the validated fields (`name`, `comment`, `output_data.care_plan.note` from `note`, `output_data.grading` from `grading`) plus `updated_at`. Keep this inside the `Markers.SavedOutputs.Rename` `_run` wrapper from Task 08.9 and before the wrapped `.update(updates)`.
  3. Add `GradingRequest` to `models/grading.py` (per Q10: place it alongside `build_grading`/`Grading`): fields `saved_id`, `text`, `clarified_text`, all `Optional[str]`.
  4. In `routes/grading.py run_care_plan_grading`: replace `body = request.get_json(silent=True) or {}` and the raw `.get()` calls with `GradingRequest(**(request.get_json(silent=True) or {}))` inside a `try/except ValidationError` → 400 `INPUT_VALIDATION_ERROR`. Then use `req.saved_id`, `req.text`, `req.clarified_text` (apply `.strip()` where the old code did).
  5. Tests — `tests/models/test_saved_outputs_model.py`: `RenameOutputRequest(name=" foo ").name == "foo"`; `name=" "` raises `ValidationError`; 201-char name raises; `comment=123` raises; `RenameOutputRequest()` succeeds (caller enforces all-None). Add to `tests/routes/test_grading_route.py`: `test_run_grading_validates_body_with_pydantic` — POST `{"saved_id": 123}` → 400 with structured error.
- **Acceptance:** `pytest tests/models/test_saved_outputs_model.py tests/routes/test_grading_route.py tests/routes/test_saved_outputs_route.py` passes; no `isinstance(...)` validation remains in `rename_saved`; `POST /care_plan/grade` with a non-string `saved_id` returns 400.
- **Commit:** `feat(models): add RenameOutputRequest/GradingRequest; drop isinstance ladders`

---

### Task 08.12: Remove the legacy `input_pdf_gcs` fallback

- **Goal:** The `or data.get('input_pdf_gcs', '')` leg is deleted from both `delete_saved` and `get_input_pdf_url`.
- **Files:**
  - `backend/routes/saved_outputs.py`
  - `backend/tests/routes/test_saved_outputs_route.py`
- **Steps:**
  1. In `delete_saved` (lines 176–179) replace the two-leg `gcs_uri` expression with:
     `gcs_uri = (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url') or ''`
  2. In `get_input_pdf_url` (lines 206–209) make the identical change; also delete the now-stale comment "fall back to legacy top-level field for old docs."
  3. Add test `test_get_input_pdf_url_returns_404_without_legacy_fallback`: a doc carrying only `input_pdf_gcs` (no `output_data.input.pdf_gcs_url`) returns 404.
     > Note (Q5 applied): per USER DECISION, no legacy is impacted — remove the fallback outright. Do **not** query Firestore to check for old-shape docs and do **not** gate the removal. The PRD's Q5/§4l SP10-coordination hedge is overridden; treat the removal as final.
- **Acceptance:** `grep -rn "input_pdf_gcs" backend/` returns nothing (outside the new test that constructs the old shape); `pytest tests/routes/test_saved_outputs_route.py` passes; the 404 test holds.
- **Commit:** `refactor(saved-outputs): remove legacy input_pdf_gcs fallback`

---

### Task 08.13: Wire `Worker.JobExecute` marker around `execute_job`

- **Goal:** The job-lifecycle entry/exit is instrumented without touching pipeline internals.
- **Files:**
  - `backend/routes/worker.py`
- **Steps:**
  1. Add `from utils.markers import Markers, JunoContext` to `worker.py`.
  2. Wrap the body of `execute_job` (after the existing OIDC/queue-name validation, which stays **outside** the marker) in `Markers.Worker.JobExecute.execute(_run)`:
     ```python
     def _run(scope):
         JunoContext.from_g(function="execute_job").apply(scope)
         scope.add("job_id", job_id)
         ...  # existing try/except body unchanged; call scope.mark_failed() on error paths
     return Markers.Worker.JobExecute.execute(_run)
     ```
  3. Do **not** move or rewrite the existing `try/except` inside `execute_job` — SP07 owns the internals; SP08 only adds the outer span and a `scope.mark_failed()` in the existing failure branch (where `fail_job` is called).
     > Note: keep the change minimal. If SP07's merged `execute_job` already has a marker wrapper, `grep -n "Markers.Worker\|JobExecute" routes/worker.py` and skip.
- **Acceptance:** `pytest tests/routes/test_worker.py` passes; `execute_job` still returns the same responses; the marker fires once per request (verify via an `InMemorySink` in a test if a sink fixture exists, otherwise rely on existing worker tests passing).
- **Commit:** `feat(worker): wrap execute_job in Worker.JobExecute marker`

---

### Task 08.14: Add section-header comments to the three large flat files

- **Goal:** `saved_outputs.py`, `firebase.py`, and `jargon_db.py` have navigation dividers; no logic changes.
- **Files:**
  - `backend/routes/saved_outputs.py`
  - `backend/utils/firebase.py`
  - `backend/utils/jargon_db.py`
- **Steps:**
  1. `saved_outputs.py`: insert the five dividers from PRD §4m above the corresponding endpoint groups (List/Get, Rename, Delete, Signed URL, Share toggle).
  2. `firebase.py`: insert the five dividers (init, auth decorators, doc-access helpers, persistence general, persistence job-lifecycle).
  3. `jargon_db.py`: insert the four dividers (data paths/loader, source metadata, abbreviation lookups, term detection). **No logic changes** to `jargon_db.py` (PRD non-goal §3).
- **Acceptance:** `python -c "import routes.saved_outputs, utils.firebase, utils.jargon_db"` imports cleanly; `git diff --stat` shows only comment additions in `jargon_db.py`; full test suite still green.
- **Commit:** `docs(backend): add section-header comments to large flat files`

---

## Verification

Run from `backend/`:

```bash
# Targeted tests for SP08 surfaces
pytest tests/utils/test_output_helpers.py \
       tests/utils/test_scoring.py \
       tests/utils/test_cloud_tasks.py \
       tests/utils/test_firebase.py \
       tests/routes/test_saved_outputs_route.py \
       tests/routes/test_grading_route.py \
       tests/routes/test_worker.py \
       tests/routes/test_care_plan_jobs.py \
       tests/models/test_saved_outputs_model.py \
       tests/models/test_grading_model.py -q

# Full backend suite (regression)
pytest -q

# Marker registry smoke
python -c "from utils.markers import Markers; \
print(Markers.Worker.JobExecute.name(), Markers.SavedOutputs.List.name(), \
Markers.Batch.CreateJobs.name(), Markers.Firestore.JobWrite.name(), \
Markers.Athena.ApiCall.name(), Markers.Grading.Route.name())"

# Dedup / legacy removal greps (each must return nothing)
grep -rn "_derive_name\|_output_name\|_score_or_none\|_score_safe" routes/ utils/
grep -rn "gcs.Client(" routes/
grep -rn "input_pdf_gcs" routes/ utils/

# Lint (repo uses pyproject.toml config)
ruff check .
```

**Definition of done:**
1. Every Firestore read/write in `saved_outputs.py`, `admin.py`, `grading.py`, and the five `firebase.py` job-lifecycle wrappers is wrapped — wrappers re-raise `FirestoreError`; routes return `make_error_response(ErrorCode.INTERNAL_ERROR)` 500s.
2. `Markers` has `Worker`, `SavedOutputs`, `Batch`, `Firestore`, `Athena.ApiCall`, and `Grading.Route`; the smoke command prints all six names; `SavedOutputs.*` is wired in `saved_outputs.py`, `Grading.Route` in `grading.py`, `Worker.JobExecute` in `worker.py`.
3. `derive_output_name`, `score_text_safe`, `get_gcs_bucket`, `enqueue_job_safe`, and `_extract_bearer_token` each exist in exactly one place; all dedup greps above return nothing.
4. `rename_saved` and `run_care_plan_grading` validate via `RenameOutputRequest` / `GradingRequest`; no isinstance ladder remains.
5. `input_pdf_gcs` appears nowhere in `routes/`/`utils/` (legacy removed); the PDF-URL endpoint returns 404 for old-shape docs.
6. Section-header comments present in `saved_outputs.py`, `firebase.py`, `jargon_db.py`; `jargon_db.py` has comment-only changes.
7. `pytest -q` is green and `ruff check .` is clean.
