"""TDD tests for POST /internal/jobs/execute/<job_id>."""
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock, patch, call
from flask import Flask
from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError


QUEUE_HEADER = {"X-CloudTasks-QueueName": "my-queue"}


@pytest.fixture(autouse=True)
def _disable_oidc_verification(monkeypatch):
    """Disable OIDC verification by default so the existing functional tests
    exercise job execution without a signed Cloud Tasks token. Tests that
    target the auth gate re-enable it explicitly via monkeypatch.
    """
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


def _make_job_doc(status="not_started", stage=None, batch_group_id=None, source_kind="text"):
    return {
        "uid": "user-1",
        "name": "Jan 15, 2026 10:00",
        "source_filename": "text_input",
        "created_at": datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
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
    mock_get_doc.return_value = _make_job_doc()

    # Mock Firestore client for status update
    mock_db = MagicMock()
    mock_fs_client.return_value = mock_db

    # Mock care_plan result
    care_plan_mock = MagicMock()
    care_plan_mock.to_dict.return_value = {"reason_for_visit": [{"reason": "Hypertension"}]}
    grading_mock = MagicMock()

    def fake_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
        yield AdapterStepEvent(step=2, status="active", label="Terms")
        yield AdapterStepEvent(step=2, status="done", label="Terms")
        yield AdapterResult(
            care_plan=care_plan_mock,
            grading=grading_mock,
            raw_text=text,
            clarified_text="clarified",
        )

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
        yield AdapterError(error_data={
            "code": "PIPELINE_ERROR",
            "message": "Pipeline error",
            "details": "Pipeline exploded",
            "timestamp": "2026-06-22T00:00:00+00:00",
            "path": "/care_plan",
        })

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
    assert error_data["details"] == "Pipeline exploded"
    mock_complete.assert_not_called()


@patch("utils.firebase.firestore.client")
@patch("routes.worker.complete_job")
@patch("routes.worker.update_job_stage")
@patch("routes.worker.fail_job")
@patch("routes.worker.get_job_doc")
def test_timeout_fails_job_with_job_timeout_code(
    mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
    client_worker
):
    mock_get_doc.return_value = _make_job_doc()
    mock_db = MagicMock()
    mock_fs_client.return_value = mock_db

    def fake_pipeline_slow(text, metrics, grading_enabled, source_kind="text", is_batch=False):
        # Emit a stage transition so _check_timeout runs.
        yield AdapterStepEvent(step=2, status="active", label="Terms")

    # First monotonic() call records the start; the next (inside _check_timeout)
    # jumps far past the single-job deadline so the timeout triggers.
    from utils.constants import Constants
    deadline = Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S
    monotonic_values = iter([0.0, deadline + 100.0])

    with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline_slow(*a, **kw)}):
        with patch("routes.worker.time.monotonic", side_effect=lambda: next(monotonic_values)):
            resp = client_worker.post(
                "/internal/jobs/execute/job-1",
                headers=QUEUE_HEADER,
            )

    assert resp.status_code == 200
    mock_fail.assert_called_once()
    error_data = mock_fail.call_args.args[1]
    assert error_data["code"] == "JOB_TIMEOUT"
    mock_complete.assert_not_called()


@patch("routes.worker.get_job_doc")
def test_idempotent_completed_job_returns_200(mock_get_doc, client_worker):
    mock_get_doc.return_value = _make_job_doc(status="completed")
    resp = client_worker.post(
        "/internal/jobs/execute/job-1",
        headers=QUEUE_HEADER,
    )
    assert resp.status_code == 200


@patch("routes.worker.get_job_doc")
def test_idempotent_error_job_returns_200(mock_get_doc, client_worker):
    mock_get_doc.return_value = _make_job_doc(status="error")
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


# --- OIDC verification gate (verification ENABLED) ---


@patch("routes.worker.get_job_doc")
def test_oidc_enabled_missing_auth_header_returns_403(mock_get_doc, client_worker, monkeypatch):
    """With verification on, a request with no Authorization header is rejected
    at the auth gate (before any job lookup)."""
    monkeypatch.setenv("WORKER_VERIFY_OIDC", "true")
    resp = client_worker.post("/internal/jobs/execute/job-1", headers=QUEUE_HEADER)
    assert resp.status_code == 403
    mock_get_doc.assert_not_called()


@patch("routes.worker.get_job_doc")
def test_oidc_enabled_garbage_token_returns_403(mock_get_doc, client_worker, monkeypatch):
    """A malformed/garbage Bearer token fails google-auth verification → 403."""
    monkeypatch.setenv("WORKER_VERIFY_OIDC", "true")
    monkeypatch.delenv("WORKER_SERVICE_ACCOUNT", raising=False)
    headers = {**QUEUE_HEADER, "Authorization": "Bearer not-a-real-jwt"}
    resp = client_worker.post("/internal/jobs/execute/job-1", headers=headers)
    assert resp.status_code == 403
    mock_get_doc.assert_not_called()


@patch("routes.worker.get_job_doc")
def test_oidc_enabled_valid_claims_passes_auth_gate(mock_get_doc, client_worker, monkeypatch):
    """A token whose verified claims match the expected email and audience
    passes the auth gate (verified by reaching the job lookup, here a missing
    doc → 200)."""
    monkeypatch.setenv("WORKER_VERIFY_OIDC", "true")
    monkeypatch.setenv("WORKER_SERVICE_ACCOUNT", "worker@proj.iam.gserviceaccount.com")
    mock_get_doc.return_value = None  # missing doc → idempotent 200

    # The test client uses http on localhost; aud reconstruction honors
    # X-Forwarded-Proto, so set it to match what we return as the claim aud.
    headers = {
        **QUEUE_HEADER,
        "Authorization": "Bearer valid-token",
        "X-Forwarded-Proto": "https",
    }
    valid_claims = {
        "email_verified": True,
        "email": "worker@proj.iam.gserviceaccount.com",
        "aud": "https://localhost/internal/jobs/execute/job-1",
    }
    with patch(
        "google.oauth2.id_token.verify_oauth2_token", return_value=valid_claims
    ):
        resp = client_worker.post("/internal/jobs/execute/job-1", headers=headers)

    assert resp.status_code == 200
    mock_get_doc.assert_called_once()
