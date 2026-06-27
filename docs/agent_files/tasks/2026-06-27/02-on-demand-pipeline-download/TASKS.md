# Tasks: SP2 — On-Demand Pipeline Download & Cleanup

**Fresh authoring — 2026-06-27**
**Prerequisite:** SP1 (GCS Infrastructure & Manifest) must be deployed before SP2 goes live.

---

### Task 1 — Add `DATASETS_BUCKET_ENV_VAR` constant

- **Files:** `/root/projects/juno/backend/utils/constants.py`
- **Changes:** In the `Constants` class, add one line in the `# ── GCS / Cloud config ─` section, immediately after `GCS_BUCKET_ENV_VAR`:
  ```python
  DATASETS_BUCKET_ENV_VAR: str = "DATASETS_BUCKET_NAME"
  ```
- **Acceptance criteria:** `from utils.constants import Constants; assert Constants.DATASETS_BUCKET_ENV_VAR == "DATASETS_BUCKET_NAME"` passes in a Python shell.

---

### Task 2 — Add `DATASET_DOWNLOAD_ERROR` to web error codes

- **Files:** `/root/projects/juno/backend/utils/error_codes.py`
- **Changes:**
  1. In the `ErrorCode(StrEnum)` enum body, add after `DATASET_NOT_FOUND` (in the `# Batch` section):
     ```python
     DATASET_DOWNLOAD_ERROR  = "DATASET_DOWNLOAD_ERROR"
     ```
  2. In `_REGISTRY`, add after the `ErrorCode.DATASET_NOT_FOUND` entry:
     ```python
     ErrorCode.DATASET_DOWNLOAD_ERROR: ("GCS dataset download failed",   "Failed to download {group}/{input_id} from GCS: {detail}"),
     ```
- **Acceptance criteria:** `from utils.error_codes import ErrorCode, make_error_response; r = make_error_response(ErrorCode.DATASET_DOWNLOAD_ERROR, "/", {"group": "G", "input_id": "I", "detail": "err"}); assert r.error.code == "DATASET_DOWNLOAD_ERROR"` passes without `KeyError`.

---

### Task 3 — Create `backend/utils/gcs_datasets.py`

- **Files:** `/root/projects/juno/backend/utils/gcs_datasets.py` *(new file)*
- **Changes:** Create the module with exactly these three public functions plus one private helper. Follow the `care_plan.py` L218 GCS client pattern (`gcs.Client(project=project_id or None)`).

  ```python
  """utils/gcs_datasets.py — GCS download helpers for batch dataset jobs (SP2)."""
  import logging
  import os
  import shutil
  import time
  from concurrent.futures import ThreadPoolExecutor, as_completed
  from pathlib import Path

  from google.cloud import storage as gcs

  logger = logging.getLogger(__name__)

  GCS_PRESET_PREFIX = "preset-data"        # blob path prefix inside the bucket
  TEMP_BASE = Path("/tmp/juno-datasets")   # job-scoped temp root


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

      project_id = os.environ.get("GCP_PROJECT_ID") or None
      client = gcs.Client(project=project_id)
      bucket = client.bucket(bucket_name)

      job_dir = TEMP_BASE / job_id

      def _download_one(blob_name: str, local_path: Path) -> None:
          local_path.parent.mkdir(parents=True, exist_ok=True)
          bucket.blob(blob_name).download_to_filename(str(local_path))

      tasks = [
          (
              f"{GCS_PRESET_PREFIX}/{group}/{input_id}/{f}",
              job_dir / group / input_id / f,
          )
          for f in files
      ]

      with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
          futures = [
              pool.submit(_download_one, blob_name, local_path)
              for blob_name, local_path in tasks
          ]
          for future in as_completed(futures):
              future.result()  # re-raises any download exception

      logger.info(
          "gcs_datasets: downloaded %d file(s) for job %s (%s/%s)",
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
          logger.info("gcs_datasets: cleaned up temp dir for job %s", job_id)
      except Exception:
          logger.exception("gcs_datasets: failed to remove temp dir %s", job_dir)


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
                      "gcs_datasets: swept stale dir %s (age=%.0fs)", entry, age
                  )
          except Exception:
              logger.exception("gcs_datasets: error sweeping dir %s", entry)
  ```

- **Acceptance criteria:**
  - `from utils.gcs_datasets import download_dataset_inputs, cleanup_dataset_inputs, sweep_stale_dataset_dirs` imports without error.
  - All three public functions are importable and have correct signatures.
  - `TEMP_BASE == Path("/tmp/juno-datasets")`.

---

### Task 4 — Update `batch_jobs.py` to remove local read and store new Firestore fields

- **Files:** `/root/projects/juno/backend/routes/batch_jobs.py`
- **Changes:**

  1. **Import line (line 12):** Remove `_combined_text_for_dataset_input` from the import. Change:
     ```python
     from routes.batch import _resolve_requested_runs, _combined_text_for_dataset_input, _batch_timestamp
     ```
     to:
     ```python
     from routes.batch import _resolve_requested_runs, _batch_timestamp
     ```

  2. **For-loop body (lines 70–79):** Remove the entire try/except block that calls `_combined_text_for_dataset_input`. Delete these lines:
     ```python
         try:
             text = _combined_text_for_dataset_input(group, input_id, files)
         except Exception:
             logger.exception("batch_jobs: failed to read dataset input %s/%s", group, input_id)
             return make_error_response(
                 ErrorCode.DATASET_NOT_FOUND,
                 request.path,
                 {"group": group, "input_id": input_id},
             ).to_dict(), 400
     ```

  3. **`job_doc` dict (lines 85–107):** Make these three changes:
     - Change `"input_source_kind": "batch_dataset"` → `"input_source_kind": "gcs_batch_dataset"`
     - Change `"input_text": text` → `"input_text": None`
     - Add two new fields after `"dataset_group": group`:
       ```python
       "dataset_input_id": input_id,
       "dataset_files": files,
       ```

  The job_doc block should look like this after the change (showing only the modified/added lines in context):
  ```python
  job_doc = {
      "uid": user_id,
      "name": now.strftime("%b %d, %Y %H:%M"),
      "source_filename": source_filename,
      "created_at": now,
      "updated_at": now,
      "status": "not_started",
      "stage": None,
      "started_at": None,
      "completed_at": None,
      "output_data": None,
      "error_data": None,
      "batch_run_id": batch_run_id,
      "batch_group_id": batch_group_id,
      "dataset_group": group,
      "dataset_input_id": input_id,       # NEW
      "dataset_files": files,             # NEW
      "input_source_kind": "gcs_batch_dataset",  # CHANGED from "batch_dataset"
      "input_text": None,                 # CHANGED from text
      "input_doc_id": None,
      "input_source_filename": source_filename,
      "input_pdf_gcs_uri": None,
      "input_version": version,
      "grading_enabled": grading_enabled,
  }
  ```

- **Acceptance criteria:**
  - `_combined_text_for_dataset_input` no longer appears anywhere in `batch_jobs.py`.
  - A POST to `/care_plan/batch/jobs` (with `_resolve_requested_runs`, `create_job_doc`, and `enqueue_job` mocked) creates job docs with `input_source_kind == "gcs_batch_dataset"`, `input_text is None`, and both `dataset_input_id` and `dataset_files` present.

---

### Task 5 — Update `worker.py` (GCS download branch + `finally` cleanup)

- **Files:** `/root/projects/juno/backend/routes/worker.py`
- **Changes:**

  1. **Add import** at the top of the file (with other stdlib imports):
     ```python
     from pathlib import Path
     ```

  2. **Update `_INPUT_TYPE_MAP`** — add one entry for `"gcs_batch_dataset"`:
     ```python
     _INPUT_TYPE_MAP = {
         "upload": "file",
         "batch_dataset": "text",       # legacy, pre-extracted text
         "gcs_batch_dataset": "text",   # new, downloads from GCS at worker time
         "doc_id": "doc_id",
         "text": "text",
     }
     ```

  3. **Add `_extract_text_from_downloaded` helper** — insert this function at module level, after `_build_error_data` and before `_verify_oidc_token`:
     ```python
     def _extract_text_from_downloaded(
         base_dir: Path, group: str, input_id: str, files: list[str]
     ) -> str:
         """Read downloaded local files and concatenate extracted text.

         Mirrors the logic of _combined_text_for_dataset_input() in batch.py
         but reads from local paths instead of calling read_dataset_file().
         """
         parts: list[str] = []
         has_text = False
         for filename in files:
             local_path = base_dir / group / input_id / filename
             file_bytes = local_path.read_bytes()
             text = _extract_text_from_bytes(file_bytes, filename).strip()
             has_text = has_text or bool(text)
             parts.append(f"\n\n--- {filename} ---\n\n{text}")
         return "".join(parts) if has_text else ""
     ```

  4. **Modify `execute_job()`** — four changes inside the function body:

     a. **Before the outer `try:` block**, add:
        ```python
        gcs_temp_dir: Path | None = None
        ```

     b. **Move `source_kind` extraction earlier.** The current line 186:
        ```python
        source_kind = job_doc.get("input_source_kind", "text")
        ```
        must be moved to immediately before the text-resolution step (currently line 179). Place it right before the existing `text = _resolve_input_from_job_doc(job_doc)` line. Then **delete** the duplicate occurrence at the original line 186 location.

     c. **Replace the single-line `text = _resolve_input_from_job_doc(job_doc)` call** with the GCS branch:
        ```python
        if source_kind == "gcs_batch_dataset":
            from utils.gcs_datasets import download_dataset_inputs
            gcs_temp_dir = download_dataset_inputs(
                group=job_doc["dataset_group"],
                input_id=job_doc["dataset_input_id"],
                files=job_doc["dataset_files"],
                job_id=job_id,
            )
            text = _extract_text_from_downloaded(
                gcs_temp_dir,
                job_doc["dataset_group"],
                job_doc["dataset_input_id"],
                job_doc["dataset_files"],
            )
        else:
            text = _resolve_input_from_job_doc(job_doc)
        ```

     d. **Add a `finally:` block** after the `except Exception as exc:` block (at the same indentation level as `try:` and `except:`):
        ```python
        finally:
            if gcs_temp_dir is not None:
                from utils.gcs_datasets import cleanup_dataset_inputs
                cleanup_dataset_inputs(job_id)
        ```

  After all changes the overall structure of `execute_job()` is:
  ```
  gcs_temp_dir: Path | None = None
  try:
      <...existing queue/OIDC checks, get_job_doc, status check, uid/batch_run_id...>
      <...Firestore status update to "processing"...>
      <...deadline_s computation...>

      source_kind = job_doc.get("input_source_kind", "text")
      if source_kind == "gcs_batch_dataset":
          gcs_temp_dir = download_dataset_inputs(...)
          text = _extract_text_from_downloaded(...)
      else:
          text = _resolve_input_from_job_doc(job_doc)

      if not text.strip():
          fail_job(...)
          return "", 200

      version = job_doc.get("input_version", "v1-2")
      grading_enabled = job_doc.get("grading_enabled", False)
      # source_kind already extracted above — do NOT re-extract here
      is_batch = _is_batch_item(job_doc)

      <...rest of pipeline loop, complete_job, return "", 200...>

  except Exception as exc:
      <...existing handler: fail_job + return "", 500...>
  finally:
      if gcs_temp_dir is not None:
          from utils.gcs_datasets import cleanup_dataset_inputs
          cleanup_dataset_inputs(job_id)
  ```

- **Acceptance criteria:**
  - `_INPUT_TYPE_MAP["gcs_batch_dataset"] == "text"`.
  - When `execute_job()` runs with a `gcs_batch_dataset` job_doc (mocked), `download_dataset_inputs` is called and `cleanup_dataset_inputs` is called in `finally` regardless of pipeline outcome.
  - When `execute_job()` runs with a `text` or `batch_dataset` job_doc, `download_dataset_inputs` is never called.
  - No `NameError: name 'source_kind'` — the variable is defined once before the `if` branch and not re-assigned again later.

---

### Task 6 — Add startup sweep call in `app.py`

- **Files:** `/root/projects/juno/backend/app.py`
- **Changes:** After the `for bp in _blueprints: app.register_blueprint(bp)` loop (around line 77), add:
  ```python
  # Sweep stale GCS dataset temp dirs left by any previous container instance
  if JUNO_MODE in ("worker", "combined"):
      try:
          from utils.gcs_datasets import sweep_stale_dataset_dirs
          sweep_stale_dataset_dirs()
      except Exception:
          logger.exception("app: stale dataset dir sweep failed at startup")
  ```

- **Acceptance criteria:**
  - In worker mode (`JUNO_MODE=worker`), `sweep_stale_dataset_dirs` is called once when the Flask app module is loaded.
  - If `sweep_stale_dataset_dirs` raises, the exception is caught and logged — the app starts normally.
  - In API mode (`JUNO_MODE=api`), the import and call are skipped entirely.

---

### Task 7 — Write unit tests for `gcs_datasets.py`

- **Files:** `/root/projects/juno/backend/tests/utils/test_gcs_datasets.py` *(new file)*
- **Changes:** Create the file with the 11 tests listed below. Use `monkeypatch` to override `TEMP_BASE` to a `tmp_path` fixture directory so tests never touch real `/tmp`. Mock `gcs.Client` with `unittest.mock.MagicMock` to avoid network calls.

  | Test name | What it verifies |
  |---|---|
  | `test_download_creates_local_dir_structure` | After `download_dataset_inputs()`, `tmp_path/job-1/GroupA/input-1/notes.txt` exists |
  | `test_download_calls_download_to_filename_for_each_file` | `blob.download_to_filename()` called once per filename in `files` list |
  | `test_download_parallel_via_thread_pool` | `ThreadPoolExecutor` is used — patch `concurrent.futures.ThreadPoolExecutor` and verify it is instantiated |
  | `test_download_raises_on_missing_bucket_env` | `DATASETS_BUCKET_NAME` not set → `RuntimeError` raised |
  | `test_download_propagates_gcs_not_found` | `blob.download_to_filename()` raises `google.api_core.exceptions.NotFound` → propagated |
  | `test_cleanup_removes_job_dir` | Create `tmp_path/job-1/` manually, call `cleanup_dataset_inputs("job-1")`, assert dir gone |
  | `test_cleanup_is_idempotent_on_missing_dir` | Call `cleanup_dataset_inputs("no-such-job")` on non-existent dir → no exception |
  | `test_cleanup_logs_but_does_not_raise_on_shutil_error` | Patch `shutil.rmtree` to raise `OSError`, call `cleanup_dataset_inputs(...)` → returns normally |
  | `test_sweep_removes_dirs_older_than_threshold` | Create a dir under `TEMP_BASE`, set its mtime to `now - 90000`, call `sweep_stale_dataset_dirs(86400)`, assert dir gone |
  | `test_sweep_keeps_recent_dirs` | Create a dir with current mtime, call `sweep_stale_dataset_dirs(86400)`, assert dir still present |
  | `test_sweep_is_noop_when_temp_base_missing` | Point `TEMP_BASE` to a non-existent path, call `sweep_stale_dataset_dirs()` → no exception |

  For `test_download_creates_local_dir_structure`, patch `gcs.Client` so `bucket.blob(name).download_to_filename(path)` writes an empty file at `path` (use a side-effect that calls `Path(path).touch()`).

  Monkeypatch `TEMP_BASE` example:
  ```python
  import utils.gcs_datasets as mod

  @pytest.fixture(autouse=True)
  def patch_temp_base(monkeypatch, tmp_path):
      monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)
  ```

- **Acceptance criteria:** `pytest backend/tests/utils/test_gcs_datasets.py` passes all 11 tests with no network calls.

---

### Task 8 — Write worker GCS dataset integration tests

- **Files:** `/root/projects/juno/backend/tests/routes/test_worker_gcs_dataset.py` *(new file)*
- **Changes:** Create the file with the 7 tests below. Reuse the `app_worker` / `client_worker` fixture pattern from the existing `test_worker.py`. Add a helper `_make_gcs_job_doc()` that returns a job_doc with `input_source_kind="gcs_batch_dataset"`, `dataset_group="GroupA"`, `dataset_input_id="input-1"`, `dataset_files=["notes.txt"]`, and other required fields.

  | Test name | What it verifies |
  |---|---|
  | `test_execute_job_downloads_and_extracts_text` | Mock `download_dataset_inputs` returning a `Path`; mock `_extract_text_from_downloaded` returning `"patient text"`; assert both are called with correct args and `complete_job` is called |
  | `test_execute_job_cleanup_called_on_success` | After a successful pipeline run, `cleanup_dataset_inputs` is called with `job_id` |
  | `test_execute_job_cleanup_called_on_pipeline_error` | Pipeline emits `{"step": "error", "error_data": {...}}`; `fail_job` called; `cleanup_dataset_inputs` still called |
  | `test_execute_job_cleanup_called_on_unhandled_exception` | `run_care_plan_pipeline` raises `RuntimeError`; `except Exception` fires; `cleanup_dataset_inputs` still called via `finally` |
  | `test_execute_job_cleanup_skipped_if_download_not_reached` | Use a job_doc with `get_job_doc` returning `None` (early return before download); assert `cleanup_dataset_inputs` is NOT called |
  | `test_execute_job_legacy_batch_dataset_uses_stored_text` | job_doc has `input_source_kind="batch_dataset"` with `input_text="legacy text"`; assert `download_dataset_inputs` is never called |
  | `test_execute_job_download_failure_marks_job_failed` | `download_dataset_inputs` raises `RuntimeError("bucket not set")`; assert `fail_job` is called and response is 500 |

  Patch targets for `download_dataset_inputs` and `cleanup_dataset_inputs`:
  ```python
  @patch("routes.worker.download_dataset_inputs", ...)   # only works if imported at module level
  ```
  Since the worker uses lazy imports inside `execute_job()` (e.g. `from utils.gcs_datasets import download_dataset_inputs`), patch the module directly:
  ```python
  @patch("utils.gcs_datasets.download_dataset_inputs", ...)
  ```
  OR import the function before patching and patch the reference. The simplest approach is to patch `utils.gcs_datasets` module attributes directly.

- **Acceptance criteria:** `pytest backend/tests/routes/test_worker_gcs_dataset.py` passes all 7 tests.

---

### Task 9 — Update existing `test_batch_jobs.py`

- **Files:** `/root/projects/juno/backend/tests/routes/test_batch_jobs.py`
- **Changes:**

  1. **Update `test_valid_batch_returns_202`:**
     - Remove the `@patch("routes.batch_jobs._combined_text_for_dataset_input", return_value="patient text")` decorator and its corresponding mock parameter `mock_combined` from the function signature.
     - Add assertions on each job_doc payload (inside the existing `for call in calls:` loop):
       ```python
       assert payload["input_source_kind"] == "gcs_batch_dataset"
       assert payload["input_text"] is None
       assert payload["dataset_input_id"] in ("input1", "input2")
       assert payload["dataset_files"] == ["file1.txt"]
       ```

  2. **Add a new test** to confirm `_combined_text_for_dataset_input` is never reached:
     ```python
     @patch.dict("os.environ", {
         "CLOUD_TASKS_QUEUE": "my-queue",
         "WORKER_URL": "https://worker.run.app",
         "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
     })
     @patch("routes.batch_jobs.enqueue_job")
     @patch("routes.batch_jobs.create_job_doc")
     @patch("routes.batch_jobs._batch_timestamp", return_value="20260101120000")
     @patch("routes.batch_jobs._resolve_requested_runs", return_value=MOCK_RUNS)
     def test_batch_dataset_does_not_read_local_files(
         mock_resolve, mock_ts, mock_create_doc, mock_enqueue,
         client_batch_jobs, auth_ok, monkeypatch,
     ):
         """_combined_text_for_dataset_input must NOT be called after SP2."""
         from routes import batch as batch_module
         monkeypatch.setattr(
             batch_module,
             "_combined_text_for_dataset_input",
             lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not be called")),
         )
         resp = client_batch_jobs.post(
             "/care_plan/batch/jobs",
             json={"selections": VALID_SELECTIONS, "version": "v1-2"},
             headers=auth_ok,
         )
         assert resp.status_code == 202
     ```

- **Acceptance criteria:** `pytest backend/tests/routes/test_batch_jobs.py` passes all tests including the new one. The updated `test_valid_batch_returns_202` no longer patches `_combined_text_for_dataset_input`.

---

## Summary of what requires you (not a dev agent)

From PRD §8 — these are manual deployment steps, not code changes:

1. **GCS IAM (coordinate with SP1):** Confirm that `firebase-adminsdk-fbsvc@juno-medical-clarity.iam.gserviceaccount.com` has `roles/storage.objectViewer` on `juno-preset-data` before deploying SP2.

2. **Env var on Cloud Run worker service:** Verify `DATASETS_BUCKET_NAME=juno-preset-data` is set on the worker service revision specifically (not only the API service). SP1 may only have set it on the API service.

3. **Deployment ordering:** SP1 must be fully deployed and files uploaded to GCS before SP2 is live. Deploying SP2 before SP1 will break all batch requests.

4. **In-flight job safety:** Jobs already enqueued with `input_source_kind: "batch_dataset"` (the old value) will continue to route through `_resolve_input_from_job_doc()` in the worker. Monitor worker logs during rollout for both source_kind values.

5. **Cloud Run `/tmp` memory sizing:** `/tmp` is memory-backed on Cloud Run. If files in `juno-preset-data` are large (>100 MB per input set), raise the container memory limit before deploying.
