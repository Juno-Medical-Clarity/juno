"""Tests for utils/gcs_datasets.py (SP2 — on-demand GCS download helpers)."""
import os
import shutil
import time
import concurrent.futures
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_bucket_env(monkeypatch):
    """Provide DATASETS_BUCKET_NAME for all tests by default."""
    monkeypatch.setenv("DATASETS_BUCKET_NAME", "test-bucket")


@pytest.fixture
def mock_gcs_module(monkeypatch):
    """Patch utils.gcs_datasets.gcs with a MagicMock; return the blob mock.

    Chain: gcs.Client() → mock_client → .bucket() → mock_bucket → .blob() → mock_blob
    """
    import utils.gcs_datasets as mod

    mock_gcs = MagicMock()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    mock_gcs.Client.return_value = mock_client
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    monkeypatch.setattr(mod, "gcs", mock_gcs)
    return mock_blob


# ---------------------------------------------------------------------------
# download_dataset_inputs
# ---------------------------------------------------------------------------

def test_download_creates_local_dir_structure(tmp_path, mock_gcs_module, monkeypatch):
    """The function creates the full nested directory and file on the local filesystem."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    # Side-effect: actually touch the file so Path.exists() returns True
    mock_gcs_module.download_to_filename.side_effect = lambda p: Path(p).touch()

    from utils.gcs_datasets import download_dataset_inputs
    download_dataset_inputs("GroupA", "input-1", ["notes.txt"], "job-1")

    assert (tmp_path / "job-1" / "GroupA" / "input-1" / "notes.txt").exists()


def test_download_calls_download_to_filename_for_each_file(tmp_path, mock_gcs_module, monkeypatch):
    """download_to_filename is called exactly once per filename in the files list."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    mock_gcs_module.download_to_filename.side_effect = lambda p: Path(p).touch()

    from utils.gcs_datasets import download_dataset_inputs
    download_dataset_inputs("GroupA", "input-1", ["a.txt", "b.txt"], "job-1")

    assert mock_gcs_module.download_to_filename.call_count == 2


def test_download_parallel_via_thread_pool(tmp_path, mock_gcs_module, monkeypatch):
    """download_dataset_inputs uses a ThreadPoolExecutor for parallel downloads."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    mock_gcs_module.download_to_filename.side_effect = lambda p: Path(p).touch()

    with patch(
        "utils.gcs_datasets.ThreadPoolExecutor",
        wraps=concurrent.futures.ThreadPoolExecutor,
    ) as mock_tpe:
        from utils.gcs_datasets import download_dataset_inputs
        download_dataset_inputs("GroupA", "input-1", ["notes.txt"], "job-1")

    assert mock_tpe.called


def test_download_raises_on_missing_bucket_env(tmp_path, monkeypatch):
    """RuntimeError is raised immediately when DATASETS_BUCKET_NAME is not set."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)
    monkeypatch.delenv("DATASETS_BUCKET_NAME", raising=False)

    from utils.gcs_datasets import download_dataset_inputs
    with pytest.raises(RuntimeError, match="DATASETS_BUCKET_NAME"):
        download_dataset_inputs("GroupA", "input-1", ["notes.txt"], "job-1")


def test_download_propagates_gcs_not_found(tmp_path, mock_gcs_module, monkeypatch):
    """google.api_core.exceptions.NotFound propagates out of download_dataset_inputs."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    from google.api_core.exceptions import NotFound
    mock_gcs_module.download_to_filename.side_effect = NotFound("blob not found")

    from utils.gcs_datasets import download_dataset_inputs
    with pytest.raises(NotFound):
        download_dataset_inputs("GroupA", "input-1", ["notes.txt"], "job-1")


# ---------------------------------------------------------------------------
# cleanup_dataset_inputs
# ---------------------------------------------------------------------------

def test_cleanup_removes_job_dir(tmp_path, monkeypatch):
    """cleanup_dataset_inputs deletes the job-scoped directory."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    job_dir = tmp_path / "job-1"
    job_dir.mkdir()

    from utils.gcs_datasets import cleanup_dataset_inputs
    cleanup_dataset_inputs("job-1")

    assert not job_dir.exists()


def test_cleanup_is_idempotent_on_missing_dir(tmp_path, monkeypatch):
    """cleanup_dataset_inputs does not raise when the job directory is absent."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    from utils.gcs_datasets import cleanup_dataset_inputs
    cleanup_dataset_inputs("no-such-job")  # must not raise


def test_cleanup_logs_but_does_not_raise_on_shutil_error(tmp_path, monkeypatch):
    """If shutil.rmtree raises OSError, cleanup_dataset_inputs logs and returns normally."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    job_dir = tmp_path / "job-x"
    job_dir.mkdir()

    with patch("utils.gcs_datasets.shutil.rmtree", side_effect=OSError("permission denied")):
        from utils.gcs_datasets import cleanup_dataset_inputs
        cleanup_dataset_inputs("job-x")  # must not raise


# ---------------------------------------------------------------------------
# sweep_stale_dataset_dirs
# ---------------------------------------------------------------------------

def test_sweep_removes_dirs_older_than_threshold(tmp_path, monkeypatch):
    """Directories whose mtime exceeds max_age_seconds are deleted by the sweep."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    old_dir = tmp_path / "old-job"
    old_dir.mkdir()

    # Set mtime to 25 hours ago (well past the default 24-hour threshold)
    stale_mtime = time.time() - 90000
    os.utime(old_dir, (stale_mtime, stale_mtime))

    from utils.gcs_datasets import sweep_stale_dataset_dirs
    sweep_stale_dataset_dirs(86400)

    assert not old_dir.exists()


def test_sweep_keeps_recent_dirs(tmp_path, monkeypatch):
    """Directories whose mtime is within max_age_seconds are left untouched."""
    import utils.gcs_datasets as mod
    monkeypatch.setattr(mod, "TEMP_BASE", tmp_path)

    recent_dir = tmp_path / "recent-job"
    recent_dir.mkdir()
    # mtime defaults to now — well within 86 400 s

    from utils.gcs_datasets import sweep_stale_dataset_dirs
    sweep_stale_dataset_dirs(86400)

    assert recent_dir.exists()


def test_sweep_is_noop_when_temp_base_missing(tmp_path, monkeypatch):
    """sweep_stale_dataset_dirs returns silently when TEMP_BASE does not exist."""
    import utils.gcs_datasets as mod
    nonexistent = tmp_path / "does-not-exist"
    monkeypatch.setattr(mod, "TEMP_BASE", nonexistent)

    from utils.gcs_datasets import sweep_stale_dataset_dirs
    sweep_stale_dataset_dirs()  # must not raise
