"""utils/gcs_datasets.py — GCS download helpers for batch dataset jobs (SP2)."""
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage as gcs

from utils.constants import Constants

logger = logging.getLogger(__name__)


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

    job_dir = Path(Constants.Storage.TEMP_BASE) / job_id

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
        "gcs_datasets: downloaded %d file(s) for job %s (%s/%s)",
        len(files), job_id, group, input_id,
    )
    return job_dir


def cleanup_dataset_inputs(job_id: str) -> None:
    """Delete /tmp/juno-datasets/{job_id}/ and all contents.

    Idempotent — safe to call even if the directory was never created.
    Logs but does not raise on errors (best-effort cleanup).
    """
    job_dir = Path(Constants.Storage.TEMP_BASE) / job_id
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
    if not Path(Constants.Storage.TEMP_BASE).exists():
        return
    now = time.time()
    for entry in Path(Constants.Storage.TEMP_BASE).iterdir():
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
