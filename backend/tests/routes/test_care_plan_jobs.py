"""TDD tests for POST /care_plan/jobs."""
import io
import pytest
from unittest.mock import patch
from flask import Flask

# A minimal, valid 1x1 PNG (no network, no fixture file needed).
_ONE_PX_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


@pytest.fixture
def app_with_jobs():
    from routes.care_plan_jobs import care_plan_jobs_bp
    app = Flask(__name__)
    app.register_blueprint(care_plan_jobs_bp)
    return app


@pytest.fixture
def client_jobs(app_with_jobs):
    return app_with_jobs.test_client()


@pytest.fixture
def auth_ok(monkeypatch):
    monkeypatch.setattr("utils.firebase.auth.verify_id_token", lambda *a, **k: {"uid": "user-1"})
    return {"Authorization": "Bearer test-token"}


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_text_returns_202_and_job_id(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "Patient has hypertension.", "version": "v1-2"},
        headers=auth_ok,
    )
    assert resp.status_code == 202
    body = resp.get_json()
    assert "job_id" in body
    assert body["job_id"]

    mock_create_doc.assert_called_once()
    call_kwargs = mock_create_doc.call_args.kwargs
    assert call_kwargs["user_id"] == "user-1"
    payload = call_kwargs["payload"]
    assert payload["status"] == "not_started"
    assert payload["input_text"] == "Patient has hypertension."

    mock_enqueue.assert_called_once()
    enqueue_kwargs = mock_enqueue.call_args.kwargs
    assert enqueue_kwargs["deadline_seconds"] == 300
    assert enqueue_kwargs["queue_name"] == "my-queue"


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_no_input_returns_400(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={},
        headers=auth_ok,
    )
    assert resp.status_code == 400
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


def test_unauthenticated_request_returns_401(client_jobs):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "test"},
    )
    assert resp.status_code == 401


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=({"status": "error", "error": {"code": "INTERNAL_ERROR"}}, 500))
@patch("routes.care_plan_jobs.create_job_doc")
def test_enqueue_failure_returns_500(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "Patient has hypertension."},
        headers=auth_ok,
    )
    assert resp.status_code == 500
    body = resp.get_json()
    assert "error" in body


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_grading_enabled_false_string_coercion(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "hello", "grading_enabled": "false"},
        headers=auth_ok,
    )
    assert resp.status_code == 202
    payload = mock_create_doc.call_args.kwargs["payload"]
    assert payload["grading_enabled"] is False


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_grading_enabled_default_true(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "hello"},
        headers=auth_ok,
    )
    assert resp.status_code == 202
    payload = mock_create_doc.call_args.kwargs["payload"]
    assert payload["grading_enabled"] is True


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
@patch("routes.care_plan_jobs.upload_combined_pdf", return_value="gs://fake-bucket/fake.pdf")
@patch("services.care_plan_input.extract_text_from_image", return_value="OCR'd image text")
def test_create_care_plan_job_accepts_image_upload(
    mock_extract_image, mock_upload_pdf, mock_create_doc, mock_enqueue, client_jobs, auth_ok
):
    resp = client_jobs.post(
        "/care_plan/jobs",
        data={"files": (io.BytesIO(_ONE_PX_PNG), "photo.png")},
        content_type="multipart/form-data",
        headers=auth_ok,
    )
    assert resp.status_code == 202
    body = resp.get_json()
    assert "job_id" in body

    mock_create_doc.assert_called_once()
    payload = mock_create_doc.call_args.kwargs["payload"]
    assert "OCR'd image text" in payload["input_text"]


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.create_job_doc", side_effect=RuntimeError("db exploded"))
def test_unhandled_exception_returns_500_json(mock_create_doc, client_jobs, auth_ok):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "hello"},
        headers=auth_ok,
    )
    assert resp.status_code == 500
    body = resp.get_json()
    assert body is not None, "Response must be JSON, not HTML"
    assert body["error"]["code"] == "INTERNAL_ERROR"
