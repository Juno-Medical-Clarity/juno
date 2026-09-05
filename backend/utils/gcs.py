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

# Lazily-constructed, process-wide GCS client. Populated on first use by
# _gcs_client(); see that function for details. Tests reset this to None
# (via monkeypatch) so each test gets a fresh mocked client.
_client: gcs.Client | None = None


def _gcs_client() -> gcs.Client:
    """Single construction point for the GCS client (project from GCP_PROJECT_ID env).

    Lazily constructs the client on first call and caches it at module level,
    so subsequent calls reuse the same instance instead of re-paying ADC
    credential-resolution cost on every call.
    """
    global _client
    if _client is None:
        _client = gcs.Client(project=os.environ.get("GCP_PROJECT_ID") or None)
    return _client


# ---------------------------------------------------------------------------
# Generic bucket access
# ---------------------------------------------------------------------------

def get_gcs_bucket(bucket_name: str | None = None):
    """Return a GCS Bucket for the given name (default: GCP_BUCKET_NAME env)."""
    name = bucket_name or _DEFAULT_BUCKET
    return _gcs_client().bucket(name)


def delete_gcs_object(gcs_uri: str) -> None:
    """Best-effort delete of a gs:// object. Swallows NotFound and logs any
    other failure — GCS cleanup failing must never fail the caller (job
    completion or the DELETE route); the expires_at TTL is the safety net."""
    if not gcs_uri.startswith("gs://"):
        logger.warning("gcs: delete_gcs_object called with non-gs:// uri=%s", gcs_uri)
        return
    _, _, rest = gcs_uri.partition("gs://")
    bucket_name, _, blob_name = rest.partition("/")
    try:
        _gcs_client().bucket(bucket_name).blob(blob_name).delete()
    except Exception as exc:
        from google.api_core.exceptions import NotFound
        if isinstance(exc, NotFound):
            return
        logger.exception("gcs: delete_gcs_object failed for uri=%s", gcs_uri)


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
