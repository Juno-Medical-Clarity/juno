# SP2 — On-Demand Pipeline Download & Cleanup

**Date:** 2026-06-27
**Status:** Draft
**Sub-project of:** Juno Preset Dataset GCS Migration
**Prerequisite:** SP1 (GCS Infrastructure & Manifest) must be deployed first

---

## 1. Problem

`POST /care_plan/batch/jobs` currently reads preset-data files from the **local filesystem**. The call chain is:

```
batch_jobs.py → _combined_text_for_dataset_input() [batch.py]
             → read_dataset_file() [preset_data.py]
             → PRESET_DATA_ROOT / group / input_id / filename  (local disk)
```

Text is pre-extracted at HTTP request time and stored in Firestore as `input_text`. The worker then reads `input_text` from Firestore and never touches the filesystem.

After SP1 migrates preset-data files to `gs://juno-preset-data/preset-data/{group}/{input_id}/{filename}`, the local path will not exist in Cloud Run. Every batch job creation will fail at the `read_dataset_file()` call.

SP2 removes the local-filesystem dependency from the batch pipeline execution path by: (a) deferring file access to worker execution time, (b) downloading from GCS into a job-scoped temp directory, and (c) guaranteeing cleanup on all exit paths.

---

## 2. Goals

- Download selected batch dataset inputs from GCS at worker execution time (not HTTP request time)
- Reuse the existing text-extraction logic (`_extract_text_from_bytes()`) on downloaded bytes
- Guarantee temp directory cleanup on success, pipeline error, and unhandled exception via `finally`
- Sweep stale temp dirs at worker container startup (crash-safety)
- Parallelize per-file downloads using `ThreadPoolExecutor` + `blob.download_to_filename()`
- Maintain backward compatibility with existing `"batch_dataset"` jobs that have pre-extracted text in Firestore
- Zero frontend changes; the `BatchDatasetSelection` wire format is unchanged

---

## 3. Non-Goals

- `list_datasets()`, manifest generation, or preview routes — those are SP1
- Changes to the single-job execution path (`POST /care_plan/jobs`, `input_source_kind: "upload"/"text"/"doc_id"`)
- Persistent caching of downloaded inputs across pipeline runs
- Streaming/SSE pipeline signature changes
- GCS upload of preset-data files — SP1
- IAM provisioning — SP1 (but SP2 requires it to be complete before deploy)

---

## 4. Architecture Decisions

### A. Injection Point

**Current file access locations in the batch execution path:**

| Location | Call | Access type |
|---|---|---|
| `batch_jobs.py` L72 | `_combined_text_for_dataset_input(group, input_id, files)` | local FS read, at HTTP request time |
| `batch.py` L44 | `_resolve_requested_runs()` → `list_datasets()` | local FS read, validates selection |
| `batch.py` L87 | `read_dataset_file(group, input_id, filename)` | local FS read, inside `_combined_text_for_dataset_input()` |
| `worker.py` L50-55 | `_resolve_input_from_job_doc()` for `batch_dataset` | Firestore read of pre-extracted `input_text` only; no file access |

**Chosen injection point: `worker.py` → `execute_job()`**

The download step is inserted in `execute_job()`, immediately before the existing `text = _resolve_input_from_job_doc(job_doc)` call. Text pre-extraction is removed from `batch_jobs.py`.

Rationale for choosing the worker over the HTTP handler:
1. The Cloud Tasks worker budget for batch items is 870s (`BATCH_ITEM_INTERNAL_DEADLINE_S`), vs. the default HTTP request timeout (~300s). Long downloads won't time out the user-facing HTTP response.
2. Cleanup via `finally` naturally wraps the entire pipeline execution, covering timeout early-returns, pipeline errors, and unhandled exceptions.
3. Keeps `POST /care_plan/batch/jobs` fast (enqueue-only), consistent with how `doc_id` jobs work — text is fetched in the worker, not at enqueue time.

`_resolve_requested_runs()` in `batch.py` still calls `list_datasets()` at HTTP request time for validation. SP1 migrates `list_datasets()` to read the GCS manifest; SP2 depends on that migration being in place.

---

### B. New File: `backend/utils/gcs_datasets.py`

New module. Does not modify `preset_data.py`.

**Constants / env vars used:**

```python
import os
import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage as gcs

logger = logging.getLogger(__name__)

GCS_PRESET_PREFIX = "preset-data"      # blob path prefix inside the bucket
TEMP_BASE = Path("/tmp/juno-datasets") # job-scoped temp root
```

Bucket name read from `os.environ["DATASETS_BUCKET_NAME"]` (introduced by SP1).
GCS client: `gcs.Client(project=os.environ.get("GCP_PROJECT_ID") or None)` — identical pattern to `care_plan.py` L218.

**Function signatures and contracts:**

```python
def download_dataset_inputs(
    group: str,
    input_id: str,
    files: list[str],
    job_id: str,
) -> Path:
    """Download selected files from GCS to a job-scoped temp directory.

    GCS source: gs://{DATASETS_BUCKET_NAME}/preset-data/{group}/{input_id}/{filename}
    Local dest:  /tmp/juno-datasets/{job_id}/{group}/{input_id}/{filename}

    Downloads exactly the filenames in `files` (the user-selected subset stored
    in dataset_files on the job_doc). Uses ThreadPoolExecutor for parallel
    blob.download_to_filename() calls.

    Returns: /tmp/juno-datasets/{job_id}/  (the job-scoped base dir)
    Raises:  RuntimeError if DATASETS_BUCKET_NAME is not set
             google.api_core.exceptions.NotFound if a blob is missing
    """

def cleanup_dataset_inputs(job_id: str) -> None:
    """Delete /tmp/juno-datasets/{job_id}/ and all contents.

    Idempotent — safe to call even if the directory was never created.
    Logs but does not raise on errors (best-effort cleanup).
    """

def sweep_stale_dataset_dirs(max_age_seconds: int = 86400) -> None:
    """Scan /tmp/juno-datasets/ and remove job dirs older than max_age_seconds.

    Called once at worker container startup. Recovers from orphaned temp dirs
    left by a previous container instance that crashed mid-job.
    Uses os.stat(dir).st_mtime for age comparison.
    """
```

**Download parallelism detail:**

```python
# Inside download_dataset_inputs():
def _download_one(blob_name: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    bucket.blob(blob_name).download_to_filename(str(local_path))

tasks = [
    (f"{GCS_PRESET_PREFIX}/{group}/{input_id}/{f}", job_dir / group / input_id / f)
    for f in files
]
with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
    futures = [pool.submit(_download_one, blob_name, local_path) for blob_name, local_path in tasks]
    for future in as_completed(futures):
        future.result()  # re-raises any download exception
```

This matches `care_plan.py`'s existing pattern of instantiating `gcs.Client()` and calling a download method directly on the blob object, extended to parallel multi-file downloads with `download_to_filename()` instead of `download_as_bytes()` (disk-backed, avoids holding all file content in RAM simultaneously).

---

### C. Integration With Pipeline

**Recommendation: extract text inline in `execute_job()` before calling the pipeline; do not pass the temp path to `run_care_plan_pipeline()` or use an env var override.**

Rationale:
- `run_care_plan_pipeline()` accepts `text: str`. It does not read files. Changing its signature to accept a path would add coupling with no benefit.
- `PRESET_DATA_ROOT` is a module-level constant in `preset_data.py`. Overriding it per-job via env var or monkeypatching is unsafe in multi-threaded execution (env vars and module globals are process-global; concurrent jobs would corrupt each other's paths).
- The temp directory is an implementation detail of the GCS download step. Scoping its lifecycle to `execute_job()` is the cleanest design.

**New private helper in `worker.py`:**

```python
def _extract_text_from_downloaded(
    base_dir: Path, group: str, input_id: str, files: list[str]
) -> str:
    """Read downloaded local files and concatenate extracted text."""
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

This reuses `_extract_text_from_bytes` already imported in `worker.py` (from `routes.care_plan`), and mirrors the logic of `_combined_text_for_dataset_input()` in `batch.py` L83-91.

---

### D. Cleanup

**In `execute_job()` — wraps the entire try/except block:**

```python
gcs_temp_dir: Path | None = None
try:
    # ... (all existing logic) ...

    source_kind = job_doc.get("input_source_kind", "text")
    if source_kind == "gcs_batch_dataset":
        from utils.gcs_datasets import download_dataset_inputs
        gcs_temp_dir = download_dataset_inputs(
            group=job_doc["dataset_group"],
            input_id=job_doc["dataset_input_id"],
            files=job_doc["dataset_files"],
            job_id=job_id,
        )
        text = _extract_text_from_downloaded(
            gcs_temp_dir, job_doc["dataset_group"], job_doc["dataset_input_id"], job_doc["dataset_files"]
        )
    else:
        text = _resolve_input_from_job_doc(job_doc)

    # ... (rest: empty-text check, pipeline loop, complete_job/fail_job, return "", 200) ...

except Exception as exc:
    # ... (existing handler: fail_job, return "", 500) ...
finally:
    if gcs_temp_dir is not None:
        from utils.gcs_datasets import cleanup_dataset_inputs
        cleanup_dataset_inputs(job_id)
```

**Exit-path coverage:**

| Exit path | `finally` runs? | Temp dir cleaned? |
|---|---|---|
| `complete_job()` → `return "", 200` | Yes | Yes |
| `fail_job()` (pipeline error) → `return "", 200` | Yes | Yes |
| Timeout early-return (`_check_timeout`) → `return "", 200` | Yes | Yes |
| Empty text → `fail_job()` → `return "", 200` | Yes | Yes (dir may not exist yet if download failed before this) |
| `except Exception` → `return "", 500` | Yes | Yes |
| GCS download raises | Caught by `except Exception` | Yes (`gcs_temp_dir` is `None` at that point, cleanup skipped; dir may be partially written but next sweep handles it) |

**Startup sweep (crash-safety):**

Call `sweep_stale_dataset_dirs()` once during worker app startup, before accepting requests. The appropriate location is the Flask app factory or a `@app.before_first_request` equivalent in `app.py`. Sweep uses `mtime` to identify dirs older than 24h. This recovers orphaned temp dirs from container crashes.

---

### E. Concurrency

Each batch job has a `job_id` that is `str(uuid.uuid4())` generated in `batch_jobs.py` L81 and is unique across all jobs and all container instances. The temp directory path `/tmp/juno-datasets/{job_id}/` is therefore unique per job. Cloud Run may run multiple worker container instances in parallel; each instance has its own isolated `/tmp` filesystem — no cross-instance collision is possible. Within a single container instance, concurrent jobs use different `job_id` subdirectories under `TEMP_BASE`.

---

### F. Efficient Download

`care_plan.py` uses `blob.download_as_bytes()` for single-file fetches (e.g., `_fetch_from_gcs()` L211-230). That returns bytes into memory. For batch inputs with multiple files, SP2 uses `blob.download_to_filename()` inside a `ThreadPoolExecutor`:

- `download_to_filename()` streams directly to disk without buffering all content in RAM simultaneously. With 5 files at 2 MB each, sequential downloads take ~5 × RTT; parallel downloads collapse to ~1 × RTT.
- `max_workers=min(8, len(files))` caps the thread count at 8 to avoid overwhelming GCS rate limits for small file counts.
- Exceptions from any download are re-raised via `future.result()` and propagate as a single exception to `execute_job()`, which catches it via `except Exception` and calls `fail_job()`.

---

### G. No Listing/Preview Changes

`list_datasets()`, `read_dataset_file()`, and the routes `GET /care_plan/datasets` and `GET /care_plan/datasets/<group>/<input>/<filename>` are exclusively SP1 territory. SP2 does not touch `preset_data.py`, the datasets route, or the preview route. `_resolve_requested_runs()` in `batch.py` continues to call `list_datasets()` for validation — SP1 migrates that function to read from the GCS manifest; SP2 depends on that migration being in place before deployment.

---

## 5. API Change Summary

### Routes

No new or modified HTTP routes. `POST /care_plan/batch/jobs` body and response are unchanged.

### Firestore Job Document Schema

New `input_source_kind` value introduced: `"gcs_batch_dataset"`. Two new fields added to job_doc for this kind.

**`batch_jobs.py` job_doc diff (for dataset selections after SP2):**

| Field | Before SP2 | After SP2 |
|---|---|---|
| `input_source_kind` | `"batch_dataset"` | `"gcs_batch_dataset"` |
| `input_text` | `"<extracted text string>"` | `null` |
| `dataset_group` | `"DocConv"` | `"DocConv"` (unchanged) |
| `dataset_input_id` | *(field absent)* | `"input-1"` *(new)* |
| `dataset_files` | *(field absent)* | `["notes.txt", "transcript.txt"]` *(new)* |
| `source_filename` | `"notes.txt, transcript.txt"` | `"notes.txt, transcript.txt"` (unchanged) |
| `input_source_filename` | `"notes.txt, transcript.txt"` | `"notes.txt, transcript.txt"` (unchanged) |

**Backward compatibility:** Existing Firestore documents with `input_source_kind: "batch_dataset"` (pre-extracted text) continue to route through the existing `_resolve_input_from_job_doc()` path in `worker.py`, which returns `job_doc.get("input_text") or ""`. No migration needed.

### `worker.py` `_INPUT_TYPE_MAP` addition

```python
_INPUT_TYPE_MAP = {
    "upload": "file",
    "batch_dataset": "text",       # legacy, pre-extracted text
    "gcs_batch_dataset": "text",   # new, downloads from GCS at worker time
    "doc_id": "doc_id",
    "text": "text",
}
```

### `constants.py` addition

```python
# ── Datasets bucket ───────────────────────────────────────────────────
DATASETS_BUCKET_ENV_VAR: str = "DATASETS_BUCKET_NAME"
```

---

## 6. Frontend Change Summary

None.

`BatchDatasetSelection` in `/root/projects/juno/frontend/src/types/datasets.ts` is unchanged:

```typescript
export interface BatchDatasetSelection {
  group: string;
  inputs: 'all' | string[];
  files: string[];
}
```

The FE sends the identical payload to `POST /care_plan/batch/jobs`. The new Firestore fields (`dataset_input_id`, `dataset_files`, `input_source_kind: "gcs_batch_dataset"`) are backend-internal and never surfaced in API responses.

---

## 7. Testing

### New: `backend/tests/utils/test_gcs_datasets.py`

| Test | What it verifies |
|---|---|
| `test_download_creates_local_dir_structure` | After `download_dataset_inputs()`, `/tmp/juno-datasets/{job_id}/{group}/{input_id}/` exists with expected files |
| `test_download_calls_download_to_filename_for_each_file` | `blob.download_to_filename()` called once per filename in `files` |
| `test_download_parallel_via_thread_pool` | `ThreadPoolExecutor` is used (mock `as_completed` / `submit` call count) |
| `test_download_raises_on_missing_bucket_env` | `DATASETS_BUCKET_NAME` unset → `RuntimeError` |
| `test_download_propagates_gcs_not_found` | `blob.download_to_filename()` raises `google.api_core.exceptions.NotFound` → propagated |
| `test_cleanup_removes_job_dir` | Create dir, call `cleanup_dataset_inputs(job_id)`, assert dir gone |
| `test_cleanup_is_idempotent_on_missing_dir` | Call `cleanup_dataset_inputs()` on non-existent dir, no exception raised |
| `test_cleanup_logs_but_does_not_raise_on_shutil_error` | Patch `shutil.rmtree` to raise, assert function returns without raising |
| `test_sweep_removes_dirs_older_than_threshold` | Create dirs, set mtime to >24h ago, assert removed after sweep |
| `test_sweep_keeps_recent_dirs` | Create dirs with current mtime, assert kept after sweep |
| `test_sweep_is_noop_when_temp_base_missing` | `TEMP_BASE` does not exist, sweep returns without error |

Use `monkeypatch` to override `TEMP_BASE` to a `tmp_path` fixture directory. Mock `gcs.Client` to avoid network calls.

### New: `backend/tests/routes/test_worker_gcs_dataset.py`

| Test | What it verifies |
|---|---|
| `test_execute_job_downloads_and_extracts_text` | Mock `download_dataset_inputs` returning a temp path; assert `_extract_text_from_downloaded()` called with correct args |
| `test_execute_job_cleanup_called_on_success` | `cleanup_dataset_inputs()` called after `complete_job()` |
| `test_execute_job_cleanup_called_on_pipeline_error` | Pipeline emits `{"step": "error"}`; `fail_job()` called; cleanup still called |
| `test_execute_job_cleanup_called_on_unhandled_exception` | `run_care_plan_pipeline` raises; `except Exception` fires; cleanup still called via `finally` |
| `test_execute_job_cleanup_skipped_if_download_not_reached` | `gcs_temp_dir` is `None` when job_doc is not found (early return); cleanup not called |
| `test_execute_job_legacy_batch_dataset_uses_stored_text` | `input_source_kind: "batch_dataset"` with `input_text`; assert `download_dataset_inputs` never called |
| `test_execute_job_download_failure_marks_job_failed` | `download_dataset_inputs` raises; `fail_job()` called with appropriate error code |

### Update: `backend/tests/routes/test_batch_jobs.py`

- Assert `input_source_kind` in created job_doc equals `"gcs_batch_dataset"` (not `"batch_dataset"`)
- Assert `input_text` in job_doc is `null`/`None`
- Assert `dataset_input_id` and `dataset_files` are present and correct
- Assert `_combined_text_for_dataset_input()` is NOT called (patch it to raise, confirm no raise)

### Manual / Integration Test

Run against staging with real GCS credentials:
1. `POST /care_plan/batch/jobs` with a valid `BatchDatasetSelection` — confirm `202`, job_doc has `input_source_kind: "gcs_batch_dataset"` and `input_text: null`
2. Worker picks up the job — confirm download log lines appear, pipeline stages advance
3. Job reaches `completed` status in Firestore with non-empty `output_data`
4. Confirm `/tmp/juno-datasets/{job_id}/` is absent on the worker container after job completion (exec into container or check Cloud Run log for cleanup log line)

---

## 8. Manual Intervention Required

1. **GCS IAM (coordinate with SP1):** Service account `firebase-adminsdk-fbsvc@juno-medical-clarity.iam.gserviceaccount.com` must have `roles/storage.objectViewer` on bucket `juno-preset-data`. Confirm this is provisioned by SP1 before deploying SP2.

2. **Env var on Cloud Run worker service:** `DATASETS_BUCKET_NAME=juno-preset-data` must be set. SP1 introduces this variable; SP2 reads it at every `download_dataset_inputs()` call. Verify the variable is set on the worker service revision (not only on the API service, if they are separate).

3. **Deployment ordering:** SP1 must be deployed and files uploaded to GCS before SP2 goes live. `_resolve_requested_runs()` calls `list_datasets()` (migrated to manifest by SP1) to validate selections; without SP1, it will return an empty dataset list and all batch requests will fail with `BATCH_INVALID_SELECTION`.

4. **In-flight job safety:** Jobs created with the old code (`input_source_kind: "batch_dataset"`, `input_text` populated) that are enqueued but not yet executed at deploy time will route through the legacy `_resolve_input_from_job_doc()` branch in the worker. No action needed; verify by watching the worker logs for `"batch_dataset"` vs. `"gcs_batch_dataset"` source_kind lines during the rollout window.

5. **Cloud Run `/tmp` memory sizing:** Cloud Run's `/tmp` is memory-backed. Default container memory is typically 256 MB–512 MB. If a single batch input's selected files exceed ~100 MB, the container may OOM during download. Check the size distribution of files in `juno-preset-data` after SP1 uploads; raise container memory allocation if needed before SP2 deploys.

---

## 9. Open Questions & Decisions

- `[RESOLVED: gcs_batch_dataset]` New `input_source_kind` value vs. reusing `"batch_dataset"`: use `"gcs_batch_dataset"` to keep backward compat. Old `"batch_dataset"` jobs with pre-extracted `input_text` continue working unchanged. The worker branches on source_kind.

- `[RESOLVED: worker execution time]` Where to trigger the GCS download — HTTP request handler (`batch_jobs.py`) vs. worker (`worker.py`): worker, for timeout budget and clean lifecycle management reasons (see Architecture Decision A).

- `[RESOLVED: explicit files from job_doc]` How to know which files to download per input_id: store `dataset_files: list[str]` in the job_doc at creation time and download exactly those names. Avoids a GCS LIST call in the worker and is consistent with how `_combined_text_for_dataset_input()` currently works (processes only the user-selected file subset).

- `[RESOLVED: ThreadPoolExecutor + download_to_filename]` Parallel vs. sequential download: `ThreadPoolExecutor(max_workers=min(8, len(files)))` with `blob.download_to_filename()`, matching the GCS client usage pattern in `care_plan.py`.

- `[RESOLVED: use (group, input_id, files, job_id) — per-input-id tuple, not a list of IDs]` Function signature for `download_dataset_inputs`: the prompt spec lists `input_ids: list[str]` but each batch job item is one `(group, input_id, files)` tuple. Using `(group, input_id, files, job_id)` is more precise and avoids an implicit "download all blobs" behavior. Confirm preferred signature with the team; the PRD assumes `(group, input_id, files, job_id)`.

- `[RESOLVED: call sweep_stale_dataset_dirs() once in the Flask app factory / startup hook, not per-request]` Stale-dir sweep call site: recommend `sweep_stale_dataset_dirs()` called once in the Flask app factory (or equivalent startup hook) rather than at the top of every `execute_job()` call to avoid per-request overhead. Confirm whether the worker service uses a startup hook or if `before_first_request` pattern is more appropriate.

- `[RESOLVED: use INTERNAL_ERROR as top-level error code; add DATASET_DOWNLOAD_ERROR as a sub-error/inner error using the existing sub-error pattern in error_codes.py — pattern: flat ErrorCode StrEnum + _REGISTRY dict[ErrorCode, tuple[str, str]] mapping each code to (message, details_template); add DATASET_DOWNLOAD_ERROR = "DATASET_DOWNLOAD_ERROR" to enum and add _REGISTRY entry e.g. ErrorCode.DATASET_DOWNLOAD_ERROR: ("GCS dataset download failed", "Failed to download {group}/{input_id} from GCS: {detail}"); context injected via details_vars dict to make_error_response(), no nested sub-error object]` Error code for GCS download failure in the worker: the existing `PipelineErrorCode` enum in `error_codes.py` does not have a `DATASET_DOWNLOAD_ERROR` value. Determine whether to add one or reuse `INTERNAL_ERROR` for this failure mode.

  **Actual pattern found in `backend/utils/error_codes.py`:** There is no nested sub-error or inner-error field — the error model is a flat `ErrorCode` StrEnum (not `PipelineErrorCode`; there is no such class) with a parallel `_REGISTRY: dict[ErrorCode, tuple[str, str]]` that maps each code to a `(message, details_template)` pair. Context is injected via `details_vars: dict` passed to `make_error_response(code, details_vars=...)`, which formats the template string. To add `DATASET_DOWNLOAD_ERROR`: (1) add `DATASET_DOWNLOAD_ERROR = "DATASET_DOWNLOAD_ERROR"` to the `ErrorCode` enum, and (2) add a corresponding `(message, details_template)` entry to `_REGISTRY`, e.g. `ErrorCode.DATASET_DOWNLOAD_ERROR: ("GCS dataset download failed", "Failed to download {group}/{input_id} from GCS: {detail}")`. The "sub-error" is expressed via the formatted `details` string, not a separate nested object.

- `[DEFERRED]` Retry behavior on GCS download failure: Cloud Tasks retries the whole job on HTTP 5xx (returned when `except Exception` fires). `cleanup_dataset_inputs()` is idempotent; partial downloads from a prior attempt are cleaned up by the sweep or by the `finally` block. No special handling needed in SP2.

- `[DEFERRED]` Persistent caching of downloaded inputs between batch runs: if the same dataset is run multiple times, the files are re-downloaded each time. A shared cache keyed on `(group, input_id, content_hash)` could improve throughput for large-scale benchmarking. Deferred; out of scope for SP2.
