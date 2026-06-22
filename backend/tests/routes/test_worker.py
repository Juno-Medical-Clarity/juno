"""TDD tests for POST /internal/jobs/execute/<job_id>."""
import json
import pytest
from unittest.mock import MagicMock, patch, call
from flask import Flask


QUEUE_HEADER = {"X-CloudTasks-QueueName": "my-queue"}


@pytest.fixture
def app_worker():
    from routes.worker import worker_bp
    app = Flask(__name__)
    app.register_blueprint(worker_bp)
    return app


@pytest.fixture
def client_worker(app_worker):
    return app_worker.test_client()


def _make_job_doc(status="not_started", stage=None, batch_group_id=None, source_kind="text"):
    return {
        "uid": "user-1",
        "status": status,
        "stage": stage,
        "batch_group_id": batch_group_id,
        "input_source_kind": source_kind,
        "input_text": "Patient has hypertension.",
        "input_doc_id": None,
        "input_version": "v1-2",
        "grading_enabled": False,
        "input_source_filename": "text_input",
        "batch_run_id": None,
    }


def test_missing_queue_header_returns_403(client_worker):
    resp = client_worker.post("/internal/jobs/execute/job-1")
    assert resp.status_code == 403


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
def test_happy_path_completes_job(
    mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
    client_worker
):
    from utils.constants import Constants

    mock_get_doc.return_value = _make_job_doc()

    # Mock Firestore client for status update
    mock_db = MagicMock()
    mock_fs_client.return_value = mock_db

    # Mock care_plan result
    care_plan_mock = MagicMock()
    care_plan_mock.to_dict.return_value = {"reason_for_visit": [{"reason": "Hypertension"}]}
    grading_mock = MagicMock()

    result_tuple = (Constants.RESULT_SENTINEL, care_plan_mock, grading_mock, "text", "text")

    def fake_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
        yield result_tuple

    envelope_mock = MagicMock()
    envelope_mock.to_dict.return_value = {
        "care_plan": {"reason_for_visit": [{"reason": "Hypertension"}]},
        "metrics": {"saved_id": None},
    }

    with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline(*a, **kw)}):
        with patch("routes.worker.CarePlanInternal", return_value=envelope_mock):
            resp = client_worker.post(
                "/internal/jobs/execute/job-1",
                headers=QUEUE_HEADER,
                content_type="application/json",
            )

    assert resp.status_code == 200
    mock_complete.assert_called_once()
    mock_fail.assert_not_called()


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
def test_pipeline_error_fails_job(
    mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
    client_worker
):
    mock_get_doc.return_value = _make_job_doc()
    mock_db = MagicMock()
    mock_fs_client.return_value = mock_db

    def fake_pipeline_error(text, metrics, grading_enabled, source_kind="text", is_batch=False):
        yield "data: " + json.dumps({"step": "error", "error": "Pipeline exploded"})

    with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline_error(*a, **kw)}):
        resp = client_worker.post(
            "/internal/jobs/execute/job-1",
            headers=QUEUE_HEADER,
        )

    assert resp.status_code == 200
    mock_fail.assert_called_once()
    fail_args = mock_fail.call_args
    error_data = fail_args.args[1]
    assert error_data["code"] == "PIPELINE_ERROR"
    mock_complete.assert_not_called()


@patch("routes.worker.get_job_doc")
def test_idempotent_completed_job_returns_200(mock_get_doc, client_worker):
    mock_get_doc.return_value = {"status": "completed", "uid": "user-1"}
    resp = client_worker.post(
        "/internal/jobs/execute/job-1",
        headers=QUEUE_HEADER,
    )
    assert resp.status_code == 200


@patch("routes.worker.get_job_doc")
def test_idempotent_error_job_returns_200(mock_get_doc, client_worker):
    mock_get_doc.return_value = {"status": "error", "uid": "user-1"}
    resp = client_worker.post(
        "/internal/jobs/execute/job-1",
        headers=QUEUE_HEADER,
    )
    assert resp.status_code == 200


@patch("routes.worker.get_job_doc")
def test_missing_job_doc_returns_200(mock_get_doc, client_worker):
    mock_get_doc.return_value = None
    resp = client_worker.post(
        "/internal/jobs/execute/job-1",
        headers=QUEUE_HEADER,
    )
    assert resp.status_code == 200


@patch("routes.worker.get_job_doc", side_effect=Exception("DB error"))
def test_unexpected_exception_returns_500(mock_get_doc, client_worker):
    resp = client_worker.post(
        "/internal/jobs/execute/job-1",
        headers=QUEUE_HEADER,
    )
    assert resp.status_code == 500
