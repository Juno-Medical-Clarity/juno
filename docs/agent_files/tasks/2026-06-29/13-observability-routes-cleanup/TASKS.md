# SP13 Observability/Logging Reconciliation & Routes-Utils-Services Boundary Cleanup — TASKS

## Prerequisites

Purpose: (a) delete the dead `JunoLogger` class and make `app.py` emit request-lifecycle structured output through `Markers`/`JunoContext` only; (b)–(c) merge three pairs/trios of small `utils/` files that duplicate client construction or are single-function clutter; (d)–(f) remove `routes/batch_utils.py` and `routes/care_plan.py` as routes files (neither has any `@bp.route` handler) by relocating their logic into `utils/`/`services/`, and relocate the six free-standing helper functions sitting above `routes/worker.py`'s one real route handler. After this sub-project, every file under `routes/` contains only Flask blueprint setup and `@bp.route`-decorated handlers (PRD Goal 7).

This sub-project assumes **SP11 (Legacy Shim Purge)** and **SP12 (Error System & Athena Consolidation)** are already merged and deployed (PRD "Dependencies"):

- **SP11** deletes `routes/care_plan.py`'s `_score_or_none` wrapper (lines ~50–52) and the `_juno_error_logger` secondary logger (line ~44) before SP13 lands. Task 13.5 below assumes these are already gone and that `run_care_plan_pipeline`'s two scoring call sites already read `score_text_safe(text, "before")` / `score_text_safe(event.clarified, "after")` directly (the same pattern `routes/grading.py` already uses). **As of this writing, SP11 has not yet run on this checkout** — `routes/care_plan.py` still defines `_score_or_none` (lines 50–52) and calls it at lines 253–254. Task 13.5 includes an explicit grep-check step so it does the right thing whether SP11 has landed or not: if `_score_or_none` is still defined, inline its two call sites to `score_text_safe(...)` as part of the move (do not carry the wrapper into the new file); if it is already gone, the call sites already read `score_text_safe(...)` and the step is a no-op.
- **SP12** touches `routes/worker.py` lines ~230–250 (the Athena `source_kind` branch inside `execute_job`'s body, calling `athena_client.fetch_encounter_summary`/`fetch_clinical_doc`). No task below touches that branch's logic — Task 13.7 only rewrites the *import block* at the top of `routes/worker.py` and relocates the free-standing helper functions *above* `execute_job`; `execute_job`'s body (including the Athena branch) is left untouched except for the already-existing references to relocated helper names (`_canonical_input_type` → `canonical_input_type`, `_is_batch_item` → `is_batch_item`, `_build_error_data` → `build_error_data`), which keep working as plain renamed calls.

All work is under `backend/`. After every task, the backend test suite for the touched files (and any file that imports from them) must stay green: run `pytest tests/` from `backend/` (or the narrower path called out in each task's Acceptance) before moving to the next task.

Every task traces to a specific PRD §4 Architecture Decision and, where applicable, a §9 Resolved Q (all eight Q items in §9 are `[RESOLVED]` — confirmed via `grep -c "\[OPEN" PRD.md` returning 0 before this file was written).

---

## Tasks

Ordering: the new `utils/misc.py` is created first (Task 13.1) because the `JunoLogger` deletion (Task 13.2) needs `utils.misc.monotonic_ms` to already exist before `app.py`'s import can be repointed. `utils/gcs.py` and `utils/batch.py` (Tasks 13.3–13.4) are independent merges and can be done any time after 13.1, but are sequenced next to keep all `utils/`-only tasks together before the `routes/care_plan.py` breakup begins. The `routes/care_plan.py` breakup (Tasks 13.5–13.6) must precede the `routes/worker.py` helper relocation (Task 13.7) because Task 13.7 appends two more functions to the `services/care_plan_input.py` file Task 13.6 creates. `routes/care_plan.py`'s deletion (Task 13.8) is last because it is only safe once every function that used to live in it has a new home and every caller has been repointed.

---

### Task 13.1: Create `utils/misc.py` — merge `utils/env.py` + `utils/output_helpers.py` + `utils/html.py`

**Goal**
One `utils/misc.py` file holding `get_env`, `derive_output_name`, and `extract_text_from_html` — three single-function files that share no domain, merged per PRD §4c. `get_env` is kept (not deleted) per PRD §9 Q5: despite zero current production call sites, its docstring describes a deliberate future test-mocking patch point, so it is carried forward rather than dropped as dead code.

**Files**
- Create: `backend/utils/misc.py`
- Delete: `backend/utils/env.py`, `backend/utils/output_helpers.py`, `backend/utils/html.py`
- Edit: `backend/routes/worker.py` (import only)
- Edit: `backend/routes/care_plan.py` (import only — the file itself is not broken up until Tasks 13.5–13.8)
- Delete: `backend/tests/utils/test_env.py`, `backend/tests/utils/test_output_helpers.py`, `backend/tests/utils/test_html.py`
- Create: `backend/tests/utils/test_misc.py`

**Steps**
1. Create `backend/utils/misc.py`:
   ```python
   """utils/misc.py — small, single-purpose, side-effect-light helpers that don't
   share a cohesive domain (merged from output_helpers.py, html.py, env.py)."""

   import logging
   import os
   from typing import Optional

   logger = logging.getLogger(__name__)


   # ---------------------------------------------------------------------------
   # Environment variable access
   # ---------------------------------------------------------------------------

   def get_env(key: str, default: Optional[str] = None, *, required: bool = False) -> Optional[str]:
       """Return os.environ.get(key, default); raise if required and absent.

       Kept despite zero current production call sites: this is a deliberate
       single patch point for test mocking, intended for future adoption
       across the codebase (see PRD SP13 §9 Q5). Not adopted more broadly here
       — out of scope for this sub-project.
       """
       value = os.environ.get(key)
       if required and not value:
           raise EnvironmentError(
               f"Required environment variable '{key}' is not set. "
               f"Set it before starting the server."
           )
       return value if value is not None else default


   # ---------------------------------------------------------------------------
   # Output naming
   # ---------------------------------------------------------------------------

   def derive_output_name(
       care_plan_data: dict,
       source_filename: str = "",
       group_fallback: str = "",
   ) -> str:
       """Derive a human-readable output name from care plan data.

       Priority (each result capped at 60 chars):
       1. reason_for_visit[0].reason (title-cased)
       2. diagnosis.main_conclusion first sentence
       3. source_filename stem (if not '' and not 'text_input')
       4. group_fallback (e.g. '{group} {input_id}' for batch)
       5. 'Appointment'
       """
       try:
           rfv = care_plan_data.get("reason_for_visit")
           if rfv and isinstance(rfv, list):
               reason = (rfv[0].get("reason") or "").strip()
               if reason:
                   return reason.title()[:60]
           diagnosis = care_plan_data.get("diagnosis") or {}
           main = (diagnosis.get("main_conclusion") or "").strip()
           if main:
               first_sentence = main.split(".")[0].strip()
               if first_sentence:
                   return first_sentence[:60]
       except Exception:
           pass
       filename = source_filename or ""
       if filename and filename != "text_input":
           stem = filename.split(",")[0].strip()
           if "." in stem:
               stem = stem.rsplit(".", 1)[0]
           stem = stem.replace("_", " ").replace("-", " ").strip()
           if stem:
               return stem.title()[:60]
       if group_fallback:
           return group_fallback.title()[:60]
       return "Appointment"


   # ---------------------------------------------------------------------------
   # HTML text extraction
   # ---------------------------------------------------------------------------

   def extract_text_from_html(html_content: bytes) -> str:
       """Extract plain text from HTML bytes.

       Strategy:
       1. Parse with BeautifulSoup using stdlib html.parser (no lxml needed).
       2. Decompose all <script> and <style> tags and their contents.
       3. Target the <body> element if present; fall back to the full document.
       4. Call .get_text(separator="\\n", strip=True) to produce readable text.
       """
       try:
           from bs4 import BeautifulSoup
       except ImportError as exc:
           raise RuntimeError(
               "beautifulsoup4 is not installed. Add 'beautifulsoup4' to requirements.txt."
           ) from exc

       soup = BeautifulSoup(html_content, "html.parser")

       for tag in soup.find_all(["script", "style"]):
           tag.decompose()

       _INLINE_TAGS = [
           "a", "abbr", "b", "cite", "code", "em", "i", "kbd", "mark",
           "q", "s", "small", "span", "strong", "sub", "sup", "u",
       ]
       for tag in list(soup.find_all(_INLINE_TAGS)):
           tag.unwrap()
       soup.smooth()

       target = soup.body if soup.body else soup

       text = target.get_text(separator="\n", strip=True)
       logger.info("html_extract: %d chars extracted", len(text))
       return text
   ```
   (Bodies are copied unchanged from the three source files — `get_env` from `utils/env.py:20-42`, `derive_output_name` from `utils/output_helpers.py:4-42`, `extract_text_from_html` from `utils/html.py:10-50`.)
2. Delete `backend/utils/env.py`, `backend/utils/output_helpers.py`, `backend/utils/html.py`.
3. In `backend/routes/worker.py`, change line 26 from `from utils.output_helpers import derive_output_name` to `from utils.misc import derive_output_name`. Do not change the call site (`derive_output_name(...)` at line 327 stays as-is).
4. In `backend/routes/care_plan.py`, change the local import inside `_extract_text_from_bytes` at line 98 from `from utils.html import extract_text_from_html` to `from utils.misc import extract_text_from_html`. (This file's own breakup happens later in Tasks 13.5–13.8; this is only the import-path fix so the file keeps working in the interim.)
5. Delete `backend/tests/utils/test_env.py`, `backend/tests/utils/test_output_helpers.py`, `backend/tests/utils/test_html.py`.
6. Create `backend/tests/utils/test_misc.py` consolidating their test bodies (mirrors the source merge, per PRD §7's suggestion): import `get_env`, `derive_output_name`, `extract_text_from_html` from `utils.misc` and carry forward each of the three old files' test cases verbatim under that one import.
**Acceptance**
- `grep -rn "utils.env\|utils.output_helpers\|utils\.html" backend --include="*.py"` returns no matches (excluding `utils/misc.py` itself and any unrelated `.html` substring false positives — confirm by eye).
- `backend/utils/env.py`, `backend/utils/output_helpers.py`, `backend/utils/html.py` no longer exist.
- `python -c "from utils.misc import get_env, derive_output_name, extract_text_from_html"` succeeds from `backend/`.
- `pytest tests/utils/test_misc.py tests/routes/test_worker.py` passes.
**Commit**
```
refactor(utils): merge env.py + output_helpers.py + html.py into utils/misc.py
```

---

### Task 13.2: Delete `JunoLogger`; `app.py` uses `Markers`/`JunoContext` only

**Goal**
Delete the `JunoLogger` class and `utils/juno_logger.py` entirely (PRD §4a, §9 Q1 — confirmed dead: zero call sites outside `app.py` and two test files). `app.py`'s `before_request`/`after_request` emit request-lifecycle structured output through `Markers`/`JunoContext` only; the standalone `"request_start"` log line is dropped (no `Markers` equivalent exists — `CodeMarker.execute()` only emits once, at completion). This is a deliberate, stated behavioral consequence (PRD §4a, §5), not a bug to fix.

**Files**
- Delete: `backend/utils/juno_logger.py`
- Edit: `backend/app.py`
- Delete: `backend/tests/utils/test_juno_logger.py`

**Steps**
1. In `backend/app.py`, change line 15 from `from utils.juno_logger import JunoLogger, monotonic_ms` to `from utils.misc import monotonic_ms`.
2. Replace the `extract_session_id` function (lines 91–118) with:
   ```python
   @app.before_request
   def extract_session_id():
       """
       Determine the session_id for this request and store it on flask.g
       for use in route handlers, structured logging, and Cloud Trace.

       Source: X-Session-Id request header, or a generated UUID if absent.
       SP4 boundary: session_id never falls back to user_id.
       """
       session_id = request.headers.get("X-Session-Id", "") or str(uuid.uuid4())
       g.session_id = session_id
       g.request_start_ms = monotonic_ms()

       current_span = trace.get_current_span()
       if current_span and current_span.is_recording():
           current_span.set_attribute("session.id", session_id)
           current_span.set_attribute("http.route", request.path)
   ```
   (This drops the `if request.path != "/health": juno_logger = JunoLogger(...); juno_logger.log_request_start(...)` block — lines 112–118 — entirely; nothing replaces it, per PRD §4a/§5.)
3. Replace the `attach_session_id_header` function (lines 121–154) with:
   ```python
   @app.after_request
   def attach_session_id_header(response):
       """Echo the session ID back to the client and emit the request-lifecycle marker."""
       session_id = getattr(g, "session_id", None)
       if session_id:
           response.headers["X-Session-Id"] = session_id

       span_ctx = trace.get_current_span().get_span_context()
       if span_ctx and span_ctx.is_valid:
           response.headers["X-Trace-Id"] = format(span_ctx.trace_id, "032x")

       # Record request-level metrics + timeline log via Markers (skip health checks
       # and SSE routes — the latter emit their own per-chunk markers).
       if request.path != "/health" and response.content_type != "text/event-stream":
           start_ms = getattr(g, "request_start_ms", None)
           duration_ms = (monotonic_ms() - start_ms) if start_ms is not None else 0.0

           def _emit(scope):
               JunoContext.from_g(function="http_request").apply(scope)
               scope.add("http_method", request.method)
               scope.add("http_path", request.path)
               scope.add("http_status", str(response.status_code))
               scope.add("duration_ms_observed", round(duration_ms, 1))
               if response.status_code >= 500:
                   scope.mark_failed()
           Markers.Http.Request.execute(_emit)

       return response
   ```
   Note the old code had two separate `if request.path != "/health":` guards (one wrapping the `JunoLogger` calls, one (nested) wrapping the `Markers` call); the new code has one guard combining both conditions (`!= "/health" and != "text/event-stream"`), matching PRD §4a's "after" snippet exactly.
4. Delete `backend/utils/juno_logger.py` in full (the `JunoLogger` class and `monotonic_ms()` — the latter already has a new home in `utils/misc.py` from Task 13.1).
5. Delete `backend/tests/utils/test_juno_logger.py` in full (it is a dedicated contract-test file for a class that no longer exists).
**Acceptance**
- `grep -rn "JunoLogger\|utils.juno_logger" backend --include="*.py"` returns no matches.
- `backend/utils/juno_logger.py` and `backend/tests/utils/test_juno_logger.py` no longer exist.
- `pytest tests/` passes (no leftover `JunoLogger` import errors).
- Manual/local check (see Summary section below): triggering a request locally shows exactly one structured log line + one log-based metric for it, no `request_start` line.
**Commit**
```
refactor(observability): delete JunoLogger; app.py emits request lifecycle via Markers only
```

---

### Task 13.3: Merge `utils/gcs_helpers.py` + `utils/gcs_datasets.py` → `utils/gcs.py`

**Goal**
One `utils/gcs.py` file for GCS client construction, generic bucket access, and the batch-dataset download/cleanup workflow (PRD §4b). The two previous files each constructed their own `gcs.Client`; the merged version shares one `_gcs_client()` constructor.

**Files**
- Create: `backend/utils/gcs.py`
- Delete: `backend/utils/gcs_helpers.py`, `backend/utils/gcs_datasets.py`
- Edit: `backend/routes/saved_outputs.py`, `backend/routes/worker.py`, `backend/routes/care_plan.py`, `backend/app.py` (imports only)
- Rename + edit: `backend/tests/utils/test_gcs_datasets.py` → `backend/tests/utils/test_gcs.py`
- Edit: `backend/tests/routes/test_worker_gcs_dataset.py`

**Steps**
1. Create `backend/utils/gcs.py`:
   ```python
   """utils/gcs.py — GCS client construction, generic bucket access, and the
   batch-dataset download/cleanup workflow (merged from gcs_helpers.py + gcs_datasets.py)."""

   import logging
   import os
   import shutil
   import time
   from concurrent.futures import ThreadPoolExecutor, as_completed
   from pathlib import Path

   from google.cloud import storage as gcs

   from utils.constants import Constants

   logger = logging.getLogger(__name__)

   _DEFAULT_BUCKET = os.environ.get("GCP_BUCKET_NAME", "")
   # Module-level constant so tests can monkeypatch it.
   TEMP_BASE: Path = Path(Constants.Storage.TEMP_BASE)


   def _gcs_client() -> gcs.Client:
       """Single construction point for the GCS client (project from GCP_PROJECT_ID env)."""
       return gcs.Client(project=os.environ.get("GCP_PROJECT_ID") or None)


   # ---------------------------------------------------------------------------
   # Generic bucket access
   # ---------------------------------------------------------------------------

   def get_gcs_bucket(bucket_name: str | None = None):
       """Return a GCS Bucket for the given name (default: GCP_BUCKET_NAME env)."""
       name = bucket_name or _DEFAULT_BUCKET
       return _gcs_client().bucket(name)


   # ---------------------------------------------------------------------------
   # Batch dataset download / cleanup workflow (SP2)
   # ---------------------------------------------------------------------------

   def download_dataset_inputs(
       group: str,
       input_id: str,
       files: list[str],
       job_id: str,
   ) -> Path:
       """Download selected files from GCS to a job-scoped temp directory.

       GCS source:  gs://{DATASETS_BUCKET_NAME}/preset-data/{group}/{input_id}/{filename}
       Local dest:  /tmp/juno-datasets/{job_id}/{group}/{input_id}/{filename}

       Downloads exactly the filenames in `files`. Uses ThreadPoolExecutor for
       parallel blob.download_to_filename() calls.

       Returns: /tmp/juno-datasets/{job_id}/  (the job-scoped base dir)
       Raises:  RuntimeError if DATASETS_BUCKET_NAME is not set
                google.api_core.exceptions.NotFound if a blob is missing
       """
       bucket_name = os.environ.get("DATASETS_BUCKET_NAME")
       if not bucket_name:
           raise RuntimeError("DATASETS_BUCKET_NAME is not configured")

       bucket = _gcs_client().bucket(bucket_name)

       job_dir = TEMP_BASE / job_id

       def _download_one(blob_name: str, local_path: Path) -> None:
           local_path.parent.mkdir(parents=True, exist_ok=True)
           bucket.blob(blob_name).download_to_filename(str(local_path))

       tasks = [
           (
               f"{Constants.Storage.GCS_PRESET_PREFIX}/{group}/{input_id}/{f}",
               job_dir / group / input_id / f,
           )
           for f in files
       ]

       if not tasks:
           return job_dir

       with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
           futures = [
               pool.submit(_download_one, blob_name, local_path)
               for blob_name, local_path in tasks
           ]
           for future in as_completed(futures):
               future.result()  # re-raises any download exception

       logger.info(
           "gcs: downloaded %d file(s) for job %s (%s/%s)",
           len(files), job_id, group, input_id,
       )
       return job_dir


   def cleanup_dataset_inputs(job_id: str) -> None:
       """Delete /tmp/juno-datasets/{job_id}/ and all contents.

       Idempotent — safe to call even if the directory was never created.
       Logs but does not raise on errors (best-effort cleanup).
       """
       job_dir = TEMP_BASE / job_id
       if not job_dir.exists():
           return
       try:
           shutil.rmtree(job_dir)
           logger.info("gcs: cleaned up temp dir for job %s", job_id)
       except Exception:
           logger.exception("gcs: failed to remove temp dir %s", job_dir)


   def sweep_stale_dataset_dirs(max_age_seconds: int = 86400) -> None:
       """Scan /tmp/juno-datasets/ and remove job dirs older than max_age_seconds.

       Called once at worker container startup. Recovers orphaned temp dirs
       left by a container that crashed mid-job.
       Uses os.stat(dir).st_mtime for age comparison.
       """
       if not TEMP_BASE.exists():
           return
       now = time.time()
       for entry in TEMP_BASE.iterdir():
           if not entry.is_dir():
               continue
           try:
               age = now - os.stat(entry).st_mtime
               if age > max_age_seconds:
                   shutil.rmtree(entry)
                   logger.info(
                       "gcs: swept stale dir %s (age=%.0fs)", entry, age
                   )
           except Exception:
               logger.exception("gcs: error sweeping dir %s", entry)
   ```
   (`download_dataset_inputs` previously built its own `gcs.Client(project=project_id)` then `.bucket(bucket_name)` inline at `gcs_datasets.py:41-43`; the merged version reuses `_gcs_client()`, eliminating the duplicated construction path per PRD §4b.)
2. Delete `backend/utils/gcs_helpers.py`, `backend/utils/gcs_datasets.py`.
3. Update import sites:
   - `backend/routes/saved_outputs.py:21`: `from utils.gcs_helpers import get_gcs_bucket` → `from utils.gcs import get_gcs_bucket`.
   - `backend/routes/care_plan.py:18`: `from utils.gcs_helpers import get_gcs_bucket` → `from utils.gcs import get_gcs_bucket`. (`routes/care_plan.py` is still a live file at this point in the sequence — its full breakup is Tasks 13.5–13.8.)
   - `backend/routes/worker.py:217-218` (inside `execute_job`'s `gcs_batch_dataset` branch): `from utils.gcs_datasets import download_dataset_inputs` → `from utils.gcs import download_dataset_inputs`.
   - `backend/routes/worker.py:345-346` (inside the `finally` block): `from utils.gcs_datasets import cleanup_dataset_inputs` → `from utils.gcs import cleanup_dataset_inputs`.
   - `backend/app.py:81-82`: `from utils.gcs_datasets import sweep_stale_dataset_dirs` → `from utils.gcs import sweep_stale_dataset_dirs`.
4. Rename `backend/tests/utils/test_gcs_datasets.py` to `backend/tests/utils/test_gcs.py`; update its `import utils.gcs_datasets as mod` (and any other `utils.gcs_datasets` reference) to `utils.gcs`.
5. In `backend/tests/routes/test_worker_gcs_dataset.py`, update every `@patch("utils.gcs_datasets.cleanup_dataset_inputs")` and `@patch("utils.gcs_datasets.download_dataset_inputs", ...)` decorator (11 occurrences total across the file) to `@patch("utils.gcs.cleanup_dataset_inputs")` / `@patch("utils.gcs.download_dataset_inputs", ...)`.
**Acceptance**
- `grep -rn "utils.gcs_helpers\|utils.gcs_datasets" backend --include="*.py"` returns no matches.
- `backend/utils/gcs_helpers.py` and `backend/utils/gcs_datasets.py` no longer exist.
- `grep -n "gcs.Client(" backend/utils/gcs.py` shows exactly one construction site (inside `_gcs_client()`).
- `pytest tests/utils/test_gcs.py tests/routes/test_worker_gcs_dataset.py tests/routes/test_saved_outputs_route.py` passes.
**Commit**
```
refactor(utils): merge gcs_helpers.py + gcs_datasets.py into utils/gcs.py; dedupe client construction
```

---

### Task 13.4: `routes/batch_utils.py` → `utils/batch.py`; delete the dead `batch_bp` Blueprint

**Goal**
`routes/batch_utils.py` is not a routes file — `grep -n "@batch_bp" backend -r` returns zero matches, so its Blueprint registration is a confirmed no-op (PRD §4d, §9 Q2). Move its two functions into `utils/batch.py`, dropping their leading underscore since they become public API of a `utils/` module, and delete the dead `batch_bp` Blueprint and its registration entirely.

**Files**
- Create: `backend/utils/batch.py`
- Delete: `backend/routes/batch_utils.py`
- Edit: `backend/routes/__init__.py`, `backend/routes/batch_jobs.py`
- Rename + edit: `backend/tests/routes/test_batch_utils.py` → `backend/tests/utils/test_batch.py`

**Steps**
1. Create `backend/utils/batch.py`:
   ```python
   """Batch-job business helpers: timestamp formatting and dataset-selection
   resolution (moved from routes/batch_utils.py)."""

   from datetime import datetime, timezone

   from utils.preset_data import list_datasets


   def batch_timestamp() -> str:
       return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


   def resolve_requested_runs(selections: list[dict]) -> list[tuple[str, str, list[str]]]:
       datasets = list_datasets()
       datasets_by_group = {dataset["group"]: dataset for dataset in datasets}
       runs: list[tuple[str, str, list[str]]] = []

       for selection in selections:
           if not isinstance(selection, dict):
               raise ValueError("Each selection must be an object")

           group = selection.get("group")
           files = selection.get("files")
           selected_inputs = selection.get("inputs")
           if not isinstance(group, str) or not group:
               raise ValueError("Selection is missing group")
           if group not in datasets_by_group:
               raise ValueError(f"Dataset group not found: {group}")
           if not isinstance(files, list) or not files or not all(isinstance(name, str) and name for name in files):
               raise ValueError(f"Selection for {group} must include files")

           dataset = datasets_by_group.get(group)
           available_files = dataset["files"] if dataset else []
           for f in files:
               if f not in available_files:
                   raise ValueError(f"File type not found in dataset {group}: {f!r}. Available: {available_files}")

           available_inputs = datasets_by_group[group].get("inputs", [])
           if selected_inputs == "all":
               input_ids = sorted(available_inputs)
           elif isinstance(selected_inputs, list) and all(isinstance(input_id, str) for input_id in selected_inputs):
               input_ids = sorted(selected_inputs)
           else:
               raise ValueError(f"Selection for {group} must include inputs")

           if not input_ids:
               raise ValueError(f"Selection for {group} has no inputs")
           unknown_inputs = [input_id for input_id in input_ids if input_id not in available_inputs]
           if unknown_inputs:
               raise FileNotFoundError(f"Dataset input not found: {group}/{unknown_inputs[0]}")

           for input_id in input_ids:
               runs.append((group, input_id, list(files)))

       return sorted(runs, key=lambda run: (run[0], run[1]))
   ```
   (Bodies copied unchanged from `routes/batch_utils.py:13-14` and `:17-59`, with the leading underscore dropped from both names per PRD §4d. `resolve_requested_runs`'s placement in `utils/` rather than `services/` follows the PRD §9 Q7 resolution: it has no IO of its own — it delegates to `utils/preset_data.py` — and stays here per the initiative's explicit direction.)
2. Delete `backend/routes/batch_utils.py` in full, including the `batch_bp = Blueprint("batch", __name__)` declaration (line 10) — it is removed entirely, not left as an empty stub.
3. In `backend/routes/__init__.py`, remove line 2 (`from routes.batch_utils import batch_bp`) and remove `batch_bp` from the `API_BLUEPRINTS` list.
4. In `backend/routes/batch_jobs.py:11`, change `from routes.batch_utils import _resolve_requested_runs, _batch_timestamp` to `from utils.batch import resolve_requested_runs, batch_timestamp`. Update both call sites in the same file from `_resolve_requested_runs(...)` / `_batch_timestamp()` to `resolve_requested_runs(...)` / `batch_timestamp()`.
5. Rename `backend/tests/routes/test_batch_utils.py` to `backend/tests/utils/test_batch.py`. Update its imports from `routes.batch_utils` to `utils.batch`, its calls from `_resolve_requested_runs`/`_batch_timestamp` to `resolve_requested_runs`/`batch_timestamp`, and remove (or replace) any test asserting on `batch_bp` since that Blueprint no longer exists.
**Acceptance**
- `grep -rn "routes.batch_utils\|batch_bp" backend --include="*.py"` returns no matches.
- `backend/routes/batch_utils.py` no longer exists.
- `python -c "from utils.batch import batch_timestamp, resolve_requested_runs"` succeeds from `backend/`.
- `pytest tests/utils/test_batch.py tests/routes/test_batch_jobs.py` passes.
- `app.url_map` (Flask) shows the same set of live URL rules as before this task (since `batch_bp` contributed zero rules, the URL map is unchanged) — see Summary section for the manual check.
**Commit**
```
refactor(routes): move batch_utils.py logic to utils/batch.py; delete dead batch_bp Blueprint
```

---

### Task 13.5: Create `services/care_plan_pipeline.py` — move `run_care_plan_pipeline` out of `routes/care_plan.py`

**Goal**
`run_care_plan_pipeline` is the pipeline-execution adapter: it orchestrates `CarePlanV1_2Pipeline.iter_steps()`, wires `Markers`/`JunoContext` instrumentation around each step, and runs grading. This is service-layer business logic, not a generic helper or routing concern (PRD §4e). Move it into a new `services/care_plan_pipeline.py`, unchanged in body.

**Files**
- Create: `backend/services/care_plan_pipeline.py`
- Edit: `backend/routes/care_plan.py` (remove the moved function and its now-unused imports)
- Edit: `backend/tests/care_plan/test_pipeline_executors.py`, `backend/tests/utils/test_care_plan_markers.py`

**Steps**
1. First, check whether SP11 has already landed: `grep -n "_score_or_none\|_juno_error_logger" backend/routes/care_plan.py`.
   - If it returns nothing, the two scoring call sites already read `score_text_safe(text, "before")` / `score_text_safe(event.clarified, "after")` — copy the function body as-is in step 2.
   - If `_score_or_none` (lines ~50-52) and `_juno_error_logger` (line ~44) are still present, this task inlines the fix as part of the move: in the copied body, replace `_score_or_none(text, "before")` with `score_text_safe(text, "before")` and `_score_or_none(event.clarified, "after")` with `score_text_safe(event.clarified, "after")`. Do **not** carry the `_score_or_none` wrapper or `_juno_error_logger` into the new file — SP13 assumes SP11's deletion of both already happened (PRD §3 Non-Goals) and does not redesign them; this inlining only avoids a broken intermediate state if SP11 hasn't executed yet in this checkout.
2. Create `backend/services/care_plan_pipeline.py` with `run_care_plan_pipeline` (the full function body currently at `routes/care_plan.py:193-289`, including the nested `_STEP_MARKER_MAP` dict and `wrap_step` closure), its module docstring, and its required imports:
   ```python
   """services/care_plan_pipeline.py — pipeline-execution adapter.

   Orchestrates CarePlanV1_2Pipeline.iter_steps(), wires Markers/JunoContext
   instrumentation around each step, and runs grading and scoring. Distinct
   from care_plan/v1_2/pipeline.py, which holds the pure step algorithm
   implementations; this module is the adapter that turns the algorithm's
   step events into Adapter* events for the job worker.
   """

   import logging
   from typing import Generator

   from flask import g

   from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
   from utils.scoring import score_text_safe
   from models.metrics import Metrics
   from models.grading import Grading, build_grading
   from utils.markers import Markers, JunoContext
   from models.pipeline_events import (
       StepEvent,
       PipelineRunResult,
       PipelineStepError,
       AdapterStepEvent,
       AdapterResult,
       AdapterError,
   )
   from errors import build_error_data_from_exc
   from observability.telemetry import get_tracer

   logger = logging.getLogger(__name__)


   def run_care_plan_pipeline(
       text: str,
       metrics: Metrics,
       grading_enabled: bool,
       source_kind: str = "upload",
       is_batch: bool = False,
   ) -> Generator[AdapterStepEvent | AdapterResult | AdapterError, None, None]:
       # ... body unchanged from routes/care_plan.py:193-289, with the two
       # scoring call sites using score_text_safe directly (see step 1) ...
   ```
   Copy the function body verbatim (applying the step-1 substitution if needed). Do not alter any instrumentation, step-marker mapping, or grading logic.
3. In `backend/routes/care_plan.py`, delete the `run_care_plan_pipeline` function (lines 193-289) and the `# ── Pipeline adapter ──...` section comment above it. Remove now-unused imports that only that function needed: `from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline`, `Generator` from `typing` (check `grep -n "Generator" backend/routes/care_plan.py` first — keep if still used elsewhere in the file), `get_tracer` from `observability.telemetry`, and `build_grading`/`GRADING_VERSION` from `models.grading` if no longer referenced. Leave `Markers`, `JunoContext`, `Metrics`, and the `models.pipeline_events` imports in place if other functions in the file still use them (verify with `grep -n` before removing each).
4. In `backend/tests/care_plan/test_pipeline_executors.py:5`, change `from routes.care_plan import run_care_plan_pipeline` to `from services.care_plan_pipeline import run_care_plan_pipeline`.
5. In `backend/tests/utils/test_care_plan_markers.py`:
   - Update the module docstring (lines 2-3, "SP4 Task 8 — Source-level assertions that care_plan.py uses Markers instead of the old JunoMetrics / JunoLogger boilerplate.") to read: `"""SP13 — Source-level assertions that services/care_plan_pipeline.py uses Markers instead of the old JunoMetrics / JunoLogger boilerplate."""` (the "JunoLogger" reference is now historical context, not a live concern, but the file's assertions are unchanged — only the target path moves).
   - Change line 13 from `_SRC = pathlib.Path(__file__).parent.parent.parent / "routes" / "care_plan.py"` to `_SRC = pathlib.Path(__file__).parent.parent.parent / "services" / "care_plan_pipeline.py"`.
**Acceptance**
- `python -c "from services.care_plan_pipeline import run_care_plan_pipeline"` succeeds from `backend/`.
- `grep -n "_score_or_none\|_juno_error_logger" backend/services/care_plan_pipeline.py` returns no matches.
- `grep -n "def run_care_plan_pipeline" backend/routes/care_plan.py` returns no matches.
- `pytest tests/care_plan/test_pipeline_executors.py tests/utils/test_care_plan_markers.py` passes.
**Commit**
```
refactor(services): move run_care_plan_pipeline from routes/care_plan.py to services/care_plan_pipeline.py
```

---

### Task 13.6: Create `services/care_plan_input.py` — move input-resolution helpers out of `routes/care_plan.py`

**Goal**
Move `routes/care_plan.py`'s remaining business-logic functions — GCS upload, file-type validation, text extraction, multi-file resolution, and GCS fetch — into a new `services/care_plan_input.py` (PRD §4e). These are genuine input-resolution business logic, not generic helpers: they encode product rules (allowed extensions, per-extension extraction dispatch, multi-file merge). The two pure string-formatting helpers in the same block (`_source_separator`, `_text_artifact_filename`) are **not** moved here — they have no business meaning, so they join `utils/misc.py` instead (PRD §4c/§4e).

**Files**
- Create: `backend/services/care_plan_input.py`
- Edit: `backend/utils/misc.py` (add `source_separator`, `text_artifact_filename`)
- Edit: `backend/routes/care_plan.py` (remove the moved functions)
- Edit: `backend/tests/utils/test_save_output.py`

**Steps**
1. In `backend/utils/misc.py`, append a new section after `extract_text_from_html`:
   ```python
   # ---------------------------------------------------------------------------
   # String formatting (rescued from routes/care_plan.py)
   # ---------------------------------------------------------------------------

   def source_separator(filename: str) -> str:
       return f"\n\n--- Source: {filename} ---\n"


   def text_artifact_filename(filename: str) -> str:
       stem = filename.rsplit(".", 1)[0] if "." in filename else filename
       return f"{stem}.txt"
   ```
   (Bodies copied unchanged from `routes/care_plan.py:104-110`.)
2. Create `backend/services/care_plan_input.py`:
   ```python
   """services/care_plan_input.py — input resolution and storage for the care-plan
   pipeline: GCS upload, file-type validation, text extraction, multi-file
   resolution, and GCS fetch (moved from routes/care_plan.py)."""

   import io
   import logging
   import os
   import uuid

   from utils.constants import Constants
   from utils.gcs import get_gcs_bucket
   from utils.misc import extract_text_from_html, source_separator, text_artifact_filename
   from utils.pdf import merge_pdfs, extract_text_from_pdf
   from models.input import ResolvedInput
   from errors import ErrorCode, JunoError

   logger = logging.getLogger(__name__)


   def upload_combined_pdf(pdf_bytes: bytes, user_id: str) -> str:
       """Upload combined input PDF bytes and return a gs:// URI."""
       bucket_name = os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")
       if not bucket_name:
           raise RuntimeError("GCP_BUCKET_NAME is not configured")

       object_id = str(uuid.uuid4())
       blob_name = f"care_plan/{user_id}/inputs/{object_id}.pdf"

       bucket = get_gcs_bucket(bucket_name)
       blob = bucket.blob(blob_name)
       blob.upload_from_string(pdf_bytes, content_type="application/pdf")
       return f"gs://{bucket_name}/{blob_name}"


   def is_allowed_extension(filename: str) -> bool:
       return "." in filename and filename.rsplit(".", 1)[1].lower() in Constants.ALLOWED_EXTENSIONS


   def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
       """Extract plain text from PDF, TXT, DOCX, or HTML bytes."""
       ext = filename.rsplit(".", 1)[1].lower()

       if ext == "txt":
           return file_bytes.decode("utf-8", errors="replace")

       if ext == "pdf":
           return extract_text_from_pdf(file_bytes)

       if ext == "docx":
           try:
               from docx import Document
           except ImportError as exc:
               raise RuntimeError(
                   "python-docx is not installed. Add 'python-docx' to requirements.txt."
               ) from exc

           doc = Document(io.BytesIO(file_bytes))
           return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

       if ext in {"html", "htm"}:
           return extract_text_from_html(file_bytes)

       raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")


   def resolve_uploaded_files(uploads) -> tuple[ResolvedInput, bytes | None]:
       files = [upload for upload in uploads if upload and upload.filename]
       if not files:
           raise ValueError("Uploaded file is missing a filename")
       if len(files) > Constants.MAX_FILE_COUNT:
           raise ValueError(f"Upload supports at most {Constants.MAX_FILE_COUNT} files")

       text_parts: list[str] = []
       merge_candidates: list[tuple[bytes, str]] = []
       filenames: list[str] = []
       aggregate_bytes = 0

       for upload in files:
           filename = upload.filename
           if not is_allowed_extension(filename):
               raise ValueError("File must be PDF, TXT, DOCX, or HTML")

           file_bytes = upload.read()
           if len(file_bytes) > Constants.MAX_FILE_BYTES:
               raise ValueError("File exceeds 10 MB limit")
           aggregate_bytes += len(file_bytes)
           if aggregate_bytes > Constants.Uploads.MAX_AGGREGATE_FILE_BYTES:
               limit_mb = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES // (1024 * 1024)
               raise ValueError(f"combined upload size exceeds {limit_mb} MB limit")

           filenames.append(filename)
           extracted_text = extract_text_from_bytes(file_bytes, filename)
           text_parts.append(f"{source_separator(filename)}{extracted_text.strip()}")

           ext = filename.rsplit(".", 1)[1].lower()
           if ext in {"pdf", "txt"}:
               merge_candidates.append((file_bytes, filename))
           elif ext in {"docx", "html", "htm"} and extracted_text.strip():
               merge_candidates.append(
                   (extracted_text.encode("utf-8"), text_artifact_filename(filename))
               )

       combined_pdf_bytes = None
       if merge_candidates:
           try:
               combined_pdf_bytes = merge_pdfs(merge_candidates)
           except Exception:
               logger.exception("care_plan_input: failed to merge input files - continuing without combined PDF")

       file_count = len(files)
       file_types = sorted({f.filename.rsplit(".", 1)[1].lower() for f in files if "." in f.filename})

       source_filename = ", ".join(filenames)
       combined_pdf_size = float(len(combined_pdf_bytes)) if combined_pdf_bytes is not None else None
       return ResolvedInput(
           text="\n".join(text_parts).strip(),
           source_description=source_filename,
           source_filename=source_filename,
           combined_pdf_size=combined_pdf_size,
           file_count=file_count,
           file_types=file_types,
       ), combined_pdf_bytes


   def fetch_from_gcs(doc_id: str) -> tuple[bytes, str]:
       """Fetch uploaded file bytes from GCS by doc_id. Returns (bytes, filename)."""
       _gcs_bucket_name = os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")
       if not _gcs_bucket_name:
           raise RuntimeError("GCP_BUCKET_NAME is not configured")

       bucket = get_gcs_bucket(_gcs_bucket_name)
       prefix = f"{Constants.Uploads.UPLOAD_PREFIX}/{doc_id}/"
       blobs = list(bucket.list_blobs(prefix=prefix))

       if not blobs:
           raise JunoError(ErrorCode.RESOURCE_NOT_FOUND, detail=f"doc_id={doc_id}")

       if len(blobs) > 1:
           blobs.sort(key=lambda b: b.updated, reverse=True)
       blob = blobs[0]
       filename = blob.name.split("/")[-1]
       return blob.download_as_bytes(), filename
   ```
   (Renames per PRD §4e table: `_allowed` → `is_allowed_extension`, `_extract_text_from_bytes` → `extract_text_from_bytes`, `_resolve_uploaded_files` → `resolve_uploaded_files`, `_fetch_from_gcs` → `fetch_from_gcs`; `upload_combined_pdf` keeps its name. Bodies otherwise unchanged from `routes/care_plan.py:56-189`, with the local `from utils.html import extract_text_from_html` inline import replaced by the module-level `utils.misc` import already fixed in Task 13.1, and `get_gcs_bucket` now coming from `utils.gcs` per Task 13.3.)
3. In `backend/routes/care_plan.py`, delete: `upload_combined_pdf` (lines 56-68), `_allowed` (lines 72-73), `_extract_text_from_bytes` (lines 76-101), `_source_separator`/`_text_artifact_filename` (lines 104-110), `_resolve_uploaded_files` (lines 113-169), `_fetch_from_gcs` (lines 172-189), and their section comments. Remove now-unused imports (`io`, `uuid`, `merge_pdfs`/`extract_text_from_pdf` from `utils.pdf`, `ResolvedInput` from `models.input` if nothing else in the file uses it — check with `grep -n` before each removal).
4. In `backend/tests/utils/test_save_output.py:72`, change `from routes.care_plan import upload_combined_pdf` to `from services.care_plan_input import upload_combined_pdf`.
**Acceptance**
- `python -c "from services.care_plan_input import upload_combined_pdf, is_allowed_extension, extract_text_from_bytes, resolve_uploaded_files, fetch_from_gcs"` succeeds from `backend/`.
- `python -c "from utils.misc import source_separator, text_artifact_filename"` succeeds from `backend/`.
- `grep -n "_allowed\|_extract_text_from_bytes\|_resolve_uploaded_files\|_fetch_from_gcs\|_source_separator\|_text_artifact_filename\|def upload_combined_pdf" backend/routes/care_plan.py` returns no matches.
- `pytest tests/utils/test_save_output.py tests/utils/test_misc.py` passes.
**Commit**
```
refactor(services): move input-resolution helpers from routes/care_plan.py to services/care_plan_input.py
```

---

### Task 13.7: Relocate `routes/worker.py`'s six free-standing helper functions

**Goal**
After Task 13.6, the remaining four functions in `routes/worker.py:38-151` (`_canonical_input_type`+`_INPUT_TYPE_MAP`, `_is_batch_item`, `_build_error_data`, `_extract_text_from_downloaded`, `_verify_oidc_token` — the other two, `_resolve_input_from_job_doc`/`_extract_text_from_downloaded`, also belong here) move to their per-function destinations (PRD §4f): pure data-shape helpers to a new `utils/job_helpers.py`, the OIDC auth helper to `utils/firebase.py` (co-locating with `verify_firebase_token`/`require_admin`, per PRD §9 Q6), the input-resolution helpers to `services/care_plan_input.py` (created in Task 13.6), and the one-line `_build_error_data` pass-through deleted outright (it adds zero logic over the already-imported `build_error_data`).

**Files**
- Create: `backend/utils/job_helpers.py`
- Edit: `backend/utils/firebase.py`
- Edit: `backend/services/care_plan_input.py`
- Edit: `backend/routes/worker.py`
- Create: `backend/tests/utils/test_job_helpers.py`
- Edit: `backend/tests/routes/test_worker.py`

**Steps**
1. Create `backend/utils/job_helpers.py`:
   ```python
   """Pure, stateless helpers for translating between JobDoc and Metrics shapes."""

   _INPUT_TYPE_MAP = {
       "upload": "file",
       "batch_dataset": "text",
       "gcs_batch_dataset": "text",
       "doc_id": "doc_id",
       "text": "text",
       "athena_encounter": "text",
       "athena_clinical_doc": "text",
   }


   def canonical_input_type(source_kind: str) -> str:
       return _INPUT_TYPE_MAP.get(source_kind, "text")


   def is_batch_item(job) -> bool:  # job: models.job.JobDoc
       return job.batch_group_id is not None
   ```
   (Bodies copied unchanged from `routes/worker.py:38-46` (`_INPUT_TYPE_MAP`), `:49-50` (`_canonical_input_type` → `canonical_input_type`), `:53-54` (`_is_batch_item` → `is_batch_item`).)
2. In `backend/utils/firebase.py`, add a new `verify_oidc_token` function in the "Auth decorators" section (after `require_admin`, around line 140), copied unchanged from `routes/worker.py:89-151` (`_verify_oidc_token`, renamed without the leading underscore). It needs `import os` (already imported in `firebase.py`) and `from flask import request` (already imported). Add the two additional imports it uses internally (`from google.oauth2 import id_token as google_id_token` and `from google.auth.transport import requests as google_requests`) as local imports inside the function body, exactly as they are today in `worker.py` (kept lazy/local, not hoisted to module level, to match the existing style — `firebase_admin`/`auth` etc. are also Firebase-SDK-specific and this is a non-Firebase OIDC check, so keeping the import local minimizes module-load-time surface).
3. In `backend/services/care_plan_input.py` (created in Task 13.6), append:
   ```python
   def resolve_input_from_job_doc(job) -> str:  # job: models.job.JobDoc
       if job.input_source_kind == "doc_id":
           file_bytes, filename = fetch_from_gcs(job.input_doc_id)
           return extract_text_from_bytes(file_bytes, filename)
       return job.input_text or ""


   def extract_text_from_downloaded(
       base_dir, group: str, input_id: str, files: list[str]
   ) -> str:
       parts: list[str] = []
       has_text = False
       for filename in files:
           local_path = base_dir / group / input_id / filename
           file_bytes = local_path.read_bytes()
           text = extract_text_from_bytes(file_bytes, filename).strip()
           has_text = has_text or bool(text)
           parts.append(f"\n\n--- {filename} ---\n\n{text}")
       return "".join(parts) if has_text else ""
   ```
   (Bodies copied unchanged from `routes/worker.py:58-62` (`_resolve_input_from_job_doc` → `resolve_input_from_job_doc`) and `:74-85` (`_extract_text_from_downloaded` → `extract_text_from_downloaded`), both renamed without the leading underscore. `extract_text_from_downloaded`'s `base_dir: Path` type hint needs `from pathlib import Path` added to `services/care_plan_input.py`'s imports if not already present.)
4. In `backend/routes/worker.py`:
   - Delete `_INPUT_TYPE_MAP`, `_canonical_input_type`, `_is_batch_item` (lines 38-54).
   - Delete `_resolve_input_from_job_doc` (lines 58-62).
   - Delete `_build_error_data` (lines 65-71) entirely — do not relocate it. Replace its 4 call sites in `execute_job` with direct calls to `build_error_data` (already imported at the top of the file): `_build_error_data(ErrorCode.JOB_TIMEOUT, f"Job timed out at stage {stage}")` → `build_error_data(ErrorCode.JOB_TIMEOUT, f"Job timed out at stage {stage}")`; `_build_error_data(ErrorCode.EMPTY_DOCUMENT)` → `build_error_data(ErrorCode.EMPTY_DOCUMENT)`; the two `_build_error_data(ErrorCode.UNKNOWN_ERROR, "...")` call sites likewise.
   - Delete `_extract_text_from_downloaded` (lines 74-85).
   - Delete `_verify_oidc_token` (lines 89-151); replace its one call site in `execute_job` (`if not _verify_oidc_token():`) with `if not verify_oidc_token():`.
   - Replace the entire import block (lines 12-28) with:
     ```python
     from utils.firebase import get_job_doc, update_job_stage, complete_job, fail_job, verify_oidc_token
     from services.care_plan_pipeline import run_care_plan_pipeline
     from services.care_plan_input import (
         fetch_from_gcs,
         extract_text_from_bytes,
         resolve_input_from_job_doc,
         extract_text_from_downloaded,
     )
     from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError
     from models.care_plan.envelope import CarePlanInternal
     from models.job import JobDoc
     from models.input import TextInput, DocIdInput
     from models.metrics import Metrics
     from utils.constants import Constants
     from utils.misc import derive_output_name
     from utils.gcs import download_dataset_inputs, cleanup_dataset_inputs
     from utils.job_helpers import canonical_input_type, is_batch_item
     from utils.markers import Markers, JunoContext
     from errors import ErrorCode, build_error_data, build_error_data_from_exc
     ```
   - Update the remaining call sites in `execute_job` from the old private names to the new imported names: `_resolve_input_from_job_doc(job)` → `resolve_input_from_job_doc(job)`; `_extract_text_from_downloaded(...)` → `extract_text_from_downloaded(...)`; `_canonical_input_type(source_kind)` → `canonical_input_type(source_kind)`; `_is_batch_item(job)` → `is_batch_item(job)` (2 call sites). Also remove the now-redundant local `from utils.gcs_datasets import download_dataset_inputs` / `cleanup_dataset_inputs` lines inside `execute_job`'s body (lines 217-218, 345-346 — these were already repointed to `utils.gcs` in Task 13.3; since the import block above now imports both at module level, delete the two local re-imports and rely on the module-level import instead).
   - After this task, `routes/worker.py` contains only: the `PIPELINES` route-wiring dict and the `execute_job` route handler (PRD §4f, closing statement). Do not change anything inside `execute_job`'s Athena branch (lines ~230-250) — that is SP12's territory (PRD §3 Non-Goals).
5. Create `backend/tests/utils/test_job_helpers.py` (PRD §7 "New test file suggestion" — these two functions were previously untested as standalone functions, only indirectly via worker route tests):
   ```python
   """Tests for utils/job_helpers.py."""
   from unittest.mock import MagicMock

   from utils.job_helpers import canonical_input_type, is_batch_item


   def test_canonical_input_type_known_kinds():
       assert canonical_input_type("upload") == "file"
       assert canonical_input_type("doc_id") == "doc_id"
       assert canonical_input_type("text") == "text"
       assert canonical_input_type("batch_dataset") == "text"
       assert canonical_input_type("gcs_batch_dataset") == "text"
       assert canonical_input_type("athena_encounter") == "text"
       assert canonical_input_type("athena_clinical_doc") == "text"


   def test_canonical_input_type_unknown_kind_defaults_to_text():
       assert canonical_input_type("something_unrecognized") == "text"


   def test_is_batch_item_true_when_batch_group_id_set():
       job = MagicMock(batch_group_id="group-1")
       assert is_batch_item(job) is True


   def test_is_batch_item_false_when_batch_group_id_none():
       job = MagicMock(batch_group_id=None)
       assert is_batch_item(job) is False
   ```
6. In `backend/tests/routes/test_worker.py:6`, change `from routes.care_plan import AdapterStepEvent, AdapterResult, AdapterError` to `from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError`.
**Acceptance**
- `grep -n "_canonical_input_type\|_is_batch_item\|_resolve_input_from_job_doc\|_build_error_data\|_extract_text_from_downloaded\|_verify_oidc_token" backend/routes/worker.py` returns no matches.
- `python -c "from utils.job_helpers import canonical_input_type, is_batch_item"` and `python -c "from utils.firebase import verify_oidc_token"` succeed from `backend/`.
- `routes/worker.py` contains exactly two top-level callables: `PIPELINES` (module-level dict) and `execute_job` (the route handler) — confirm by eye after the edits.
- `pytest tests/utils/test_job_helpers.py tests/routes/test_worker.py tests/routes/test_worker_gcs_dataset.py` passes.
**Commit**
```
refactor(routes): relocate routes/worker.py's free-standing helpers to utils/services per function
```

---

### Task 13.8: Delete `routes/care_plan.py`; fix remaining import sites; remove the dead `care_plan_bp` Blueprint

**Goal**
After Tasks 13.5-13.7, `routes/care_plan.py` has zero `@care_plan_bp.route` decorators (confirmed PRD §9 Q3) and no remaining business logic — every function in it has moved to `services/care_plan_pipeline.py` or `services/care_plan_input.py`. Delete the file entirely, remove its dead Blueprint registration, and repoint the last two routes files that still import from it directly.

**Files**
- Delete: `backend/routes/care_plan.py`
- Edit: `backend/routes/__init__.py`, `backend/routes/care_plan_jobs.py`, `backend/routes/datasets.py`
- Edit: `backend/tests/models/test_envelope.py`

**Steps**
1. Confirm `routes/care_plan.py` has nothing left to move: `grep -n "^def \|^    def " backend/routes/care_plan.py` should return nothing (all functions relocated in Tasks 13.5-13.6); the file should now contain only its module docstring, imports, the `logger`/`_juno_error_logger` declarations (gone if SP11 landed; see Task 13.5 step 1's grep-check — if still present, delete them now as part of this final cleanup, matching PRD §3's assumption that SP13 leaves them in SP11's hands but does not ship a file that still references a function that no longer exists), and the `care_plan_bp = Blueprint("care_plan", __name__)` declaration plus the now-unused `AdapterStepEvent`/`AdapterResult`/`AdapterError` pass-through imports from `models.pipeline_events` (re-exported but never defined there).
2. Delete `backend/routes/care_plan.py` in full, including the `care_plan_bp` Blueprint — confirmed dead with no live effect (zero `@care_plan_bp.route` decorators, no `template_folder`/`static_folder` configured), same reasoning as `batch_bp` in Task 13.4.
3. In `backend/routes/__init__.py`, remove line 1 (`from routes.care_plan import care_plan_bp`) and remove `care_plan_bp` from the `API_BLUEPRINTS` list. The file should now read:
   ```python
   from routes.saved_outputs import saved_outputs_bp
   from routes.datasets import datasets_bp
   from routes.grading import grading_bp
   from routes.care_plan_jobs import care_plan_jobs_bp
   from routes.batch_jobs import batch_jobs_bp
   from routes.worker import worker_bp
   from routes.admin import admin_bp

   API_BLUEPRINTS = [
       care_plan_jobs_bp,
       batch_jobs_bp,
       saved_outputs_bp,
       datasets_bp,
       grading_bp,
       admin_bp,
   ]

   WORKER_BLUEPRINTS = [
       worker_bp,
   ]
   ```
4. In `backend/routes/care_plan_jobs.py:15-21`, change:
   ```python
   from routes.care_plan import (
       _resolve_uploaded_files,
       upload_combined_pdf,
       _fetch_from_gcs,
       _extract_text_from_bytes,
       _allowed,
   )
   ```
   to:
   ```python
   from services.care_plan_input import (
       resolve_uploaded_files,
       upload_combined_pdf,
       fetch_from_gcs,
       extract_text_from_bytes,
       is_allowed_extension,
   )
   ```
   Update the file's call sites: `_resolve_uploaded_files(uploads)` (line 62) → `resolve_uploaded_files(uploads)`; `_fetch_from_gcs(doc_id)` (line 78) → `fetch_from_gcs(doc_id)`; `_allowed(filename)` (line 79) → `is_allowed_extension(filename)`; `_extract_text_from_bytes(file_bytes, filename)` (line 83) → `extract_text_from_bytes(file_bytes, filename)`.
5. In `backend/routes/datasets.py:3`, change `from routes.care_plan import _extract_text_from_bytes` to `from services.care_plan_input import extract_text_from_bytes`. Update the call site at line 31 from `_extract_text_from_bytes(file_bytes, filename)` to `extract_text_from_bytes(file_bytes, filename)`.
6. In `backend/tests/models/test_envelope.py`, remove lines 126-127 (`import routes.batch_utils  # noqa: F401` and `import routes.care_plan  # noqa: F401`) from `test_model_consuming_routes_import_without_removed_aliases`. Leave the rest of the test (the `routes.grading`/`routes.saved_outputs` imports and the `routes_dir.glob("*.py")` substring-absence loop at lines 128-135) unchanged — it continues to scan whatever `.py` files remain under `routes/`, which after this task no longer include `batch_utils.py` or `care_plan.py`.
**Acceptance**
- `backend/routes/care_plan.py` no longer exists.
- `grep -rn "routes.care_plan\b\|care_plan_bp" backend --include="*.py"` returns no matches (excluding `routes/care_plan_jobs.py`'s own module name, which is unrelated).
- `grep -rn "from routes\." backend/routes backend/tests --include="*.py"` shows no route file importing from another route file (the layering smell called out in PRD §4e is gone).
- `python -c "import routes; print(routes.API_BLUEPRINTS, routes.WORKER_BLUEPRINTS)"` succeeds from `backend/` and shows 6 entries in `API_BLUEPRINTS`, 1 in `WORKER_BLUEPRINTS`.
- Every file under `backend/routes/*.py` (other than `__init__.py`) contains only Flask blueprint setup and `@bp.route`-decorated handlers — spot-check by eye (PRD Goal 7).
- `pytest tests/` passes in full from `backend/`.
**Commit**
```
refactor(routes): delete routes/care_plan.py; repoint care_plan_jobs.py and datasets.py to services/care_plan_input
```

---

## Verification

Run all commands from `backend/`:

```bash
# 1. Full test suite
pytest tests/

# 2. Confirm no [OPEN] items remain undecided (sanity-check on the source PRD, not code)
grep -c '\[OPEN' ../docs/agent_files/tasks/2026-06-29/13-observability-routes-cleanup/PRD.md  # expect 0

# 3. Confirm routes/ contains no non-route business logic
grep -rln "^def " backend_or_n/a  # (manual scan — see Task 13.8 acceptance)
```

Targeted greps (all must return zero matches, run from `backend/`):

```bash
grep -rn "JunoLogger\|utils.juno_logger" .
grep -rn "utils.env\b\|utils.output_helpers\|utils\.html\b" . --include="*.py"
grep -rn "utils.gcs_helpers\|utils.gcs_datasets" . --include="*.py"
grep -rn "routes.batch_utils\|batch_bp" . --include="*.py"
grep -rn "routes.care_plan\b\|care_plan_bp" . --include="*.py"
```

### Definition of done

- All eight tasks committed (one conventional commit each), in order.
- `pytest tests/` passes in full.
- Every targeted grep above returns no matches.
- `backend/utils/juno_logger.py`, `backend/utils/env.py`, `backend/utils/output_helpers.py`, `backend/utils/html.py`, `backend/utils/gcs_helpers.py`, `backend/utils/gcs_datasets.py`, `backend/routes/batch_utils.py`, `backend/routes/care_plan.py` are all deleted.
- `backend/utils/misc.py`, `backend/utils/gcs.py`, `backend/utils/batch.py`, `backend/utils/job_helpers.py`, `backend/services/care_plan_pipeline.py`, `backend/services/care_plan_input.py` all exist with the functions described above.
- Every file under `backend/routes/*.py` (other than `__init__.py`) contains only Flask blueprint setup and `@bp.route`-decorated handlers.
- No HTTP-visible behavior changes other than the one stated, intentional drop of the standalone `"request_start"` log line (PRD §5).

---

## Summary of what requires you (not a dev agent)

**Per PRD §8 "Manual Intervention Required From You": None.** This is a pure code-reorganization sub-project — no new infra, no env vars, no Firestore/GCS schema changes, no Cloud Run config changes, no deploy-time migration steps. Every task above is fully executable by a dev agent with no external access.

Two non-blocking checks from PRD §7 "Testing" are worth a human (or CI) running locally after all eight tasks land, since they exercise live request behavior rather than unit assertions — neither requires special access, just a local dev server:

1. **Manual/integration check (PRD §7, after Task 13.2):** trigger a request locally against the dev server and confirm exactly one structured log line + one log-based metric appear for it (via the dev console formatter), with no `request_start`/`request_end` step-named lines remaining in the output — confirming the intentional drop of the standalone request-start log line (PRD §5) behaves as designed.
2. **Blueprint-registration regression check (PRD §7, after Task 13.8):** with the app running locally, inspect `app.url_map` and confirm the same set of live URL rules as before this sub-project (since `batch_bp` and `care_plan_bp` both contributed zero rules, the URL map should be byte-for-byte identical before and after).

Everything else — file moves, renames, import updates, test updates — is captured in Tasks 13.1-13.8 above and requires no judgment calls beyond what's already specified in the PRD's `[RESOLVED]` §9 entries.
