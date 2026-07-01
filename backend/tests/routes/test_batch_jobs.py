"""TDD tests for POST /care_plan/batch/jobs."""
import pytest
from unittest.mock import MagicMock, patch
from flask import Flask


@pytest.fixture
def app_with_batch_jobs():
    from routes.batch_jobs import batch_jobs_bp
    app = Flask(__name__)
    app.register_blueprint(batch_jobs_bp)
    return app


@pytest.fixture
def client_batch_jobs(app_with_batch_jobs):
    return app_with_batch_jobs.test_client()


@pytest.fixture
def auth_ok(monkeypatch):
    monkeypatch.setattr("utils.firebase.auth.verify_id_token", lambda *a, **k: {"uid": "user-1"})
    return {"Authorization": "Bearer test-token"}


VALID_SELECTIONS = [
    {"input_source_kind": "gcs_dataset", "group": "GroupA", "inputs": "all", "files": ["file1.txt"]},
]

MOCK_RUNS = [
    ("GroupA", "input1", ["file1.txt"]),
    ("GroupA", "input2", ["file1.txt"]),
]


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.batch_jobs.enqueue_job")
@patch("routes.batch_jobs.create_job_doc")
@patch("routes.batch_jobs.batch_timestamp", return_value="20260101120000")
@patch("routes.batch_jobs.resolve_requested_runs", return_value=MOCK_RUNS)
def test_valid_batch_returns_202(
    mock_resolve, mock_ts, mock_create_doc, mock_enqueue,
    client_batch_jobs, auth_ok
):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": VALID_SELECTIONS, "version": "v1-2"},
        headers=auth_ok,
    )
    assert resp.status_code == 202
    body = resp.get_json()
    assert "batch_run_id" in body
    assert "job_ids" in body
    assert len(body["job_ids"]) == 2

    # All jobs share the same batch_run_id and carry SP2 GCS fields
    calls = mock_create_doc.call_args_list
    assert len(calls) == 2
    batch_run_id = body["batch_run_id"]
    for call in calls:
        payload = call.kwargs["payload"]
        assert payload["batch_run_id"] == batch_run_id
        assert payload["status"] == "not_started"
        assert payload["input_source_kind"] == "gcs_batch_dataset"
        assert payload["input_text"] is None
        assert "dataset_input_id" in payload
        assert "dataset_files" in payload

    # enqueue called with batch_run_id
    enqueue_calls = mock_enqueue.call_args_list
    assert len(enqueue_calls) == 2
    for call in enqueue_calls:
        assert call.kwargs["batch_run_id"] == batch_run_id


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.batch_jobs.enqueue_job")
@patch("routes.batch_jobs.create_job_doc")
@patch("routes.batch_jobs.batch_timestamp", return_value="20260101120000")
@patch("routes.batch_jobs.resolve_requested_runs", return_value=MOCK_RUNS)
def test_batch_dataset_does_not_read_local_files(
    mock_resolve, mock_ts, mock_create_doc, mock_enqueue,
    client_batch_jobs, auth_ok,
):
    """After SP2, _combined_text_for_dataset_input must never be called.

    The route returns 202 without reading any local dataset files.  If the old
    text-extraction function were still invoked it would fail (no longer imported),
    causing a non-202 response.
    """
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": VALID_SELECTIONS, "version": "v1-2"},
        headers=auth_ok,
    )
    assert resp.status_code == 202


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.batch_jobs.resolve_requested_runs", side_effect=ValueError("Dataset group not found: BadGroup"))
def test_unknown_dataset_group_returns_400(mock_resolve, client_batch_jobs, auth_ok):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": [{"input_source_kind": "gcs_dataset", "group": "BadGroup", "inputs": "all", "files": ["f.txt"]}]},
        headers=auth_ok,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "error" in body


def test_unauthenticated_request_returns_401(client_batch_jobs):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": VALID_SELECTIONS},
    )
    assert resp.status_code == 401


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
def test_missing_selections_returns_400(client_batch_jobs, auth_ok):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={},
        headers=auth_ok,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]["code"] == "INPUT_VALIDATION_ERROR"


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
def test_empty_selections_returns_400(client_batch_jobs, auth_ok):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": []},
        headers=auth_ok,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]["code"] == "INPUT_VALIDATION_ERROR"


def test_athena_encounter_missing_encounter_id_returns_400(client_batch_jobs, auth_ok):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": [{"input_source_kind": "athena_encounter", "athena_encounter_id": ""}]},
        headers=auth_ok,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]["code"] == "INPUT_VALIDATION_ERROR"


def test_athena_clinical_doc_missing_document_id_returns_400(client_batch_jobs, auth_ok):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": [{"input_source_kind": "athena_clinical_doc", "athena_document_id": ""}]},
        headers=auth_ok,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]["code"] == "INPUT_VALIDATION_ERROR"


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.batch_jobs.enqueue_job")
@patch("routes.batch_jobs.create_job_doc")
@patch("routes.batch_jobs.batch_timestamp", return_value="20260101120000")
@patch("routes.batch_jobs.resolve_requested_runs", return_value=MOCK_RUNS)
def test_grading_enabled_string_coercion(
    mock_resolve, mock_ts, mock_create_doc, mock_enqueue,
    client_batch_jobs, auth_ok
):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"grading_enabled": "yes", "selections": VALID_SELECTIONS},
        headers=auth_ok,
    )
    assert resp.status_code == 202
    for call in mock_create_doc.call_args_list:
        assert call.kwargs["payload"]["grading_enabled"] is True


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.batch_jobs.enqueue_job")
@patch("routes.batch_jobs.create_job_doc")
@patch("routes.batch_jobs.batch_timestamp", return_value="20260101120000")
@patch("routes.batch_jobs.resolve_requested_runs", return_value=MOCK_RUNS)
def test_version_defaults_to_v1_2(
    mock_resolve, mock_ts, mock_create_doc, mock_enqueue,
    client_batch_jobs, auth_ok
):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": VALID_SELECTIONS},
        headers=auth_ok,
    )
    assert resp.status_code == 202
    for call in mock_create_doc.call_args_list:
        assert call.kwargs["payload"]["input_version"] == "v1-2"


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.batch_jobs.resolve_requested_runs", return_value=MOCK_RUNS)
@patch("routes.batch_jobs.create_job_doc", side_effect=RuntimeError("db exploded"))
def test_unhandled_exception_returns_500_json(
    mock_create_doc, mock_resolve, client_batch_jobs, auth_ok
):
    resp = client_batch_jobs.post(
        "/care_plan/batch/jobs",
        json={"selections": VALID_SELECTIONS},
        headers=auth_ok,
    )
    assert resp.status_code == 500
    body = resp.get_json()
    assert body is not None, "Response must be JSON, not HTML"
    assert body["error"]["code"] == "INTERNAL_ERROR"
