"""TDD tests for the gcs_batch_dataset branch of execute_job (SP2).

These tests exercise the download → extract → pipeline → cleanup flow that was
added in SP2 for jobs whose input_source_kind is "gcs_batch_dataset".
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


QUEUE_HEADER = {"X-CloudTasks-QueueName": "my-queue"}


# ---------------------------------------------------------------------------
# Fixtures — reuse the same pattern as test_worker.py
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _disable_oidc_verification(monkeypatch):
    """Disable OIDC token verification so tests reach job execution logic."""
    monkeypatch.setenv("WORKER_VERIFY_OIDC", "false")


@pytest.fixture
def app_worker():
    from routes.worker import worker_bp
    app = Flask(__name__)
    app.register_blueprint(worker_bp)
    return app


@pytest.fixture
def client_worker(app_worker):
    return app_worker.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gcs_job_doc(status="not_started"):
    """Job document for a gcs_batch_dataset job."""
    return {
        "uid": "user-1",
        "status": status,
        "stage": None,
        "batch_group_id": "GroupA-20260101",
        "batch_run_id": "batch-1",
        "input_source_kind": "gcs_batch_dataset",
        "input_text": None,
        "input_doc_id": None,
        "dataset_group": "GroupA",
        "dataset_input_id": "input-1",
        "dataset_files": ["notes.txt"],
        "input_version": "v1-2",
        "grading_enabled": False,
        "input_source_filename": "notes.txt",
    }


def _make_success_pipeline_items():
    from utils.constants import Constants
    care_plan_mock = MagicMock()
    care_plan_mock.to_dict.return_value = {"reason_for_visit": [{"reason": "Hypertension"}]}
    grading_mock = MagicMock()
    return (Constants.RESULT_SENTINEL, care_plan_mock, grading_mock, "text", "text")


def _fake_success_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
    yield _make_success_pipeline_items()


def _envelope_mock():
    m = MagicMock()
    m.to_dict.return_value = {
        "care_plan": {"reason_for_visit": [{"reason": "Hypertension"}]},
        "metrics": {"saved_id": None},
    }
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
@patch("routes.worker._extract_text_from_downloaded", return_value="patient text")
@patch("utils.gcs_datasets.cleanup_dataset_inputs")
@patch("utils.gcs_datasets.download_dataset_inputs", return_value=Path("/tmp/juno-datasets/job-1"))
def test_execute_job_downloads_and_extracts_text(
    mock_download, mock_cleanup, mock_extract, mock_get_doc,
    mock_fail, mock_update, mock_complete, mock_fs_client,
    client_worker,
):
    """download_dataset_inputs and _extract_text_from_downloaded are called with correct args."""
    mock_get_doc.return_value = _make_gcs_job_doc()
    mock_fs_client.return_value = MagicMock()

    with patch.dict("routes.worker.PIPELINES", {"v1-2": _fake_success_pipeline}):
        with patch("routes.worker.CarePlanInternal", return_value=_envelope_mock()):
            resp = client_worker.post(
                "/internal/jobs/execute/job-1",
                headers=QUEUE_HEADER,
            )

    assert resp.status_code == 200
    mock_download.assert_called_once_with(
        group="GroupA",
        input_id="input-1",
        files=["notes.txt"],
        job_id="job-1",
    )
    mock_extract.assert_called_once()


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
@patch("routes.worker._extract_text_from_downloaded", return_value="patient text")
@patch("utils.gcs_datasets.cleanup_dataset_inputs")
@patch("utils.gcs_datasets.download_dataset_inputs", return_value=Path("/tmp/juno-datasets/job-1"))
def test_execute_job_cleanup_called_on_success(
    mock_download, mock_cleanup, mock_extract, mock_get_doc,
    mock_fail, mock_update, mock_complete, mock_fs_client,
    client_worker,
):
    """cleanup_dataset_inputs is called with the job_id after the pipeline succeeds."""
    mock_get_doc.return_value = _make_gcs_job_doc()
    mock_fs_client.return_value = MagicMock()

    with patch.dict("routes.worker.PIPELINES", {"v1-2": _fake_success_pipeline}):
        with patch("routes.worker.CarePlanInternal", return_value=_envelope_mock()):
            client_worker.post(
                "/internal/jobs/execute/job-1",
                headers=QUEUE_HEADER,
            )

    mock_cleanup.assert_called_once_with("job-1")


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
@patch("routes.worker._extract_text_from_downloaded", return_value="patient text")
@patch("utils.gcs_datasets.cleanup_dataset_inputs")
@patch("utils.gcs_datasets.download_dataset_inputs", return_value=Path("/tmp/juno-datasets/job-1"))
def test_execute_job_cleanup_called_on_pipeline_error(
    mock_download, mock_cleanup, mock_extract, mock_get_doc,
    mock_fail, mock_update, mock_complete, mock_fs_client,
    client_worker,
):
    """cleanup_dataset_inputs is still called when the pipeline emits an SSE error event."""
    mock_get_doc.return_value = _make_gcs_job_doc()
    mock_fs_client.return_value = MagicMock()

    def _error_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
        yield "data: " + json.dumps({
            "step": "error",
            "error_data": {
                "code": "PIPELINE_ERROR",
                "message": "Something went wrong",
                "details": "Boom",
                "timestamp": "2026-06-27T00:00:00+00:00",
                "path": "/care_plan",
            },
        })

    with patch.dict("routes.worker.PIPELINES", {"v1-2": _error_pipeline}):
        client_worker.post(
            "/internal/jobs/execute/job-1",
            headers=QUEUE_HEADER,
        )

    mock_cleanup.assert_called_once_with("job-1")


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
@patch("routes.worker._extract_text_from_downloaded", return_value="patient text")
@patch("utils.gcs_datasets.cleanup_dataset_inputs")
@patch("utils.gcs_datasets.download_dataset_inputs", return_value=Path("/tmp/juno-datasets/job-1"))
def test_execute_job_cleanup_called_on_unhandled_exception(
    mock_download, mock_cleanup, mock_extract, mock_get_doc,
    mock_fail, mock_update, mock_complete, mock_fs_client,
    client_worker,
):
    """cleanup_dataset_inputs is called via finally even when the pipeline raises."""
    mock_get_doc.return_value = _make_gcs_job_doc()
    mock_fs_client.return_value = MagicMock()

    def _raising_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
        raise RuntimeError("pipeline exploded")
        yield  # make it a generator

    with patch.dict("routes.worker.PIPELINES", {"v1-2": _raising_pipeline}):
        client_worker.post(
            "/internal/jobs/execute/job-1",
            headers=QUEUE_HEADER,
        )

    mock_cleanup.assert_called_once_with("job-1")


@patch("utils.gcs_datasets.cleanup_dataset_inputs")
@patch("routes.worker.get_job_doc", return_value=None)
def test_execute_job_cleanup_skipped_if_download_not_reached(
    mock_get_doc, mock_cleanup,
    client_worker,
):
    """When the job doc is not found (early return), cleanup is never called.

    gcs_temp_dir stays None, so the finally block skips cleanup.
    """
    resp = client_worker.post(
        "/internal/jobs/execute/job-1",
        headers=QUEUE_HEADER,
    )

    assert resp.status_code == 200
    mock_cleanup.assert_not_called()


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
@patch("utils.gcs_datasets.download_dataset_inputs")
def test_execute_job_legacy_batch_dataset_uses_stored_text(
    mock_download, mock_get_doc,
    mock_fail, mock_update, mock_complete, mock_fs_client,
    client_worker,
):
    """input_source_kind='batch_dataset' uses input_text directly; download is never called."""
    legacy_doc = {
        "uid": "user-1",
        "status": "not_started",
        "stage": None,
        "batch_group_id": "GroupA-20260101",
        "batch_run_id": "batch-1",
        "input_source_kind": "batch_dataset",
        "input_text": "legacy patient text",
        "input_doc_id": None,
        "input_version": "v1-2",
        "grading_enabled": False,
        "input_source_filename": "notes.txt",
    }
    mock_get_doc.return_value = legacy_doc
    mock_fs_client.return_value = MagicMock()

    envelope_mock = _envelope_mock()

    with patch.dict("routes.worker.PIPELINES", {"v1-2": _fake_success_pipeline}):
        with patch("routes.worker.CarePlanInternal", return_value=envelope_mock):
            resp = client_worker.post(
                "/internal/jobs/execute/job-1",
                headers=QUEUE_HEADER,
            )

    assert resp.status_code == 200
    mock_download.assert_not_called()


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
@patch("utils.gcs_datasets.cleanup_dataset_inputs")
@patch(
    "utils.gcs_datasets.download_dataset_inputs",
    side_effect=RuntimeError("GCS unavailable"),
)
def test_execute_job_download_failure_marks_job_failed(
    mock_download, mock_cleanup, mock_get_doc,
    mock_fail, mock_update, mock_complete, mock_fs_client,
    client_worker,
):
    """When download_dataset_inputs raises, the route returns 500 and fail_job is called."""
    mock_get_doc.return_value = _make_gcs_job_doc()
    mock_fs_client.return_value = MagicMock()

    resp = client_worker.post(
        "/internal/jobs/execute/job-1",
        headers=QUEUE_HEADER,
    )

    assert resp.status_code == 500
    mock_fail.assert_called_once()
    # cleanup IS called even when download raises, to remove any partial temp dirs
    mock_cleanup.assert_called_once_with("job-1")
