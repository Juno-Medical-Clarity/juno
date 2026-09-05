"""TDD tests for POST /trial/jobs and DELETE /trial/jobs/<job_id>."""
import pytest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch, MagicMock
from flask import Flask

from errors import ErrorCode, JunoError


TRIAL_ENV = {
    "CLOUD_TASKS_QUEUE_TRIAL": "trial-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
}


@pytest.fixture
def app_trial():
    from routes.trial import trial_bp
    app = Flask(__name__)
    app.register_blueprint(trial_bp)
    return app


@pytest.fixture
def client_trial(app_trial):
    return app_trial.test_client()


@pytest.fixture
def auth_ok(monkeypatch):
    monkeypatch.setattr("utils.firebase.auth.verify_id_token", lambda *a, **k: {"uid": "user-1"})
    return {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def _allow_rate_limit(monkeypatch):
    """Most tests aren't testing the rate limiter itself — always allow."""
    monkeypatch.setattr("routes.trial.rate_limit_trial", lambda f: f)


# ---------------------------------------------------------------------------
# POST /trial/jobs
# ---------------------------------------------------------------------------

@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
def test_post_text_returns_202_with_trial_fields(mock_create_doc, mock_enqueue, client_trial, auth_ok):
    resp = client_trial.post("/trial/jobs", json={"text": "Patient has hypertension."}, headers=auth_ok)
    assert resp.status_code == 202
    assert "job_id" in resp.get_json()

    payload = mock_create_doc.call_args.kwargs["payload"]
    assert payload["is_trial"] is True
    assert payload["expires_at"] > datetime.now(timezone.utc)
    assert payload["grading_enabled"] is True
    assert payload["input_version"] == "v1-2"
    assert payload["input_doc_id"] is None

    enqueue_kwargs = mock_enqueue.call_args.kwargs
    assert enqueue_kwargs["queue_name"] == "trial-queue"


@patch.dict("os.environ", {**TRIAL_ENV, "GCP_BUCKET_NAME": "test-bucket"})
@patch("services.care_plan_input.get_gcs_bucket")
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
def test_post_multipart_upload_within_limit_returns_202(
    mock_create_doc, mock_enqueue, mock_get_gcs_bucket, client_trial, auth_ok
):
    # "note.txt" is mergeable into a combined PDF by resolve_uploaded_files
    # (real, unmocked pdf-merge logic — unchanged main-app behavior), so the
    # route's is_trial=True upload_combined_pdf call reaches real GCS bucket
    # access; mock only that boundary, not the merge/text-extraction logic.
    bucket = mock_get_gcs_bucket.return_value
    bucket.blob.return_value = MagicMock()

    data = {"files": (BytesIO(b"hello world"), "note.txt")}
    resp = client_trial.post(
        "/trial/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
    )
    assert resp.status_code == 202
    mock_create_doc.assert_called_once()
    payload = mock_create_doc.call_args.kwargs["payload"]
    assert payload["input_pdf_gcs_uri"].startswith("gs://test-bucket/care_plan_trial/")


@patch.dict("os.environ", {**TRIAL_ENV, "GCP_BUCKET_NAME": "test-bucket"})
@patch("services.care_plan_input.get_gcs_bucket")
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
@patch(
    "services.care_plan_input.extract_text_from_image",
    side_effect=JunoError(
        ErrorCode.EMPTY_DOCUMENT,
        detail="Image contained no readable text (model returned NO_TEXT_FOUND).",
    ),
)
def test_post_blurry_image_returns_422_empty_document(
    mock_extract_image, mock_create_doc, mock_enqueue, mock_get_gcs_bucket, client_trial, auth_ok
):
    """Regression test: extract_text_from_image raising JunoError(EMPTY_DOCUMENT)
    for an unreadable/blurry image must surface as 422 EMPTY_DOCUMENT, not fall
    through the generic `except Exception` to a 500 INTERNAL_ERROR."""
    data = {"files": (BytesIO(b"fake-jpeg-bytes"), "photo.jpg")}
    resp = client_trial.post(
        "/trial/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["error"]["code"] == "EMPTY_DOCUMENT"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
def test_post_more_than_5_files_returns_400(mock_create_doc, mock_enqueue, client_trial, auth_ok):
    data = {"files": [(BytesIO(b"x"), f"f{i}.txt") for i in range(6)]}
    resp = client_trial.post(
        "/trial/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()


@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.create_job_doc")
def test_post_no_input_returns_400(mock_create_doc, client_trial, auth_ok):
    resp = client_trial.post("/trial/jobs", json={}, headers=auth_ok)
    assert resp.status_code == 400
    mock_create_doc.assert_not_called()


def test_post_unauthenticated_returns_401(client_trial):
    resp = client_trial.post("/trial/jobs", json={"text": "hi"})
    assert resp.status_code == 401


@patch.dict("os.environ", {}, clear=True)
@patch("routes.trial.create_job_doc")
def test_post_missing_cloud_tasks_config_returns_500_and_no_doc_created(mock_create_doc, client_trial, auth_ok):
    resp = client_trial.post("/trial/jobs", json={"text": "hi"}, headers=auth_ok)
    assert resp.status_code == 500
    # Regression guard for the orphan-doc bug (§9 Q9) — this route validates
    # Cloud Tasks config BEFORE writing to Firestore, unlike care_plan_jobs.py.
    mock_create_doc.assert_not_called()


@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.create_job_doc")
def test_post_ignores_client_supplied_grading_and_version_and_doc_id(mock_create_doc, client_trial, auth_ok):
    with patch("routes.trial.enqueue_job_safe", return_value=None):
        resp = client_trial.post(
            "/trial/jobs",
            json={"text": "hi", "grading_enabled": False, "version": "v9-9", "doc_id": "some-doc"},
            headers=auth_ok,
        )
    assert resp.status_code == 202
    payload = mock_create_doc.call_args.kwargs["payload"]
    assert payload["grading_enabled"] is True
    assert payload["input_version"] == "v1-2"
    assert payload["input_doc_id"] is None


def test_rate_limit_429_blocks_before_auth(client_trial, monkeypatch):
    """With the real (non-bypassed) rate_limit_trial decorator, a blocked IP
    gets 429 even with no Authorization header at all.

    Deviation from TASKS.md's verbatim test: the autouse `_allow_rate_limit`
    fixture monkeypatches the module-level name `routes.trial.rate_limit_trial`,
    but `create_trial_job` was already wrapped by the *real* `rate_limit_trial`
    at import/decoration time (decorators bind once, at module load) — so that
    monkeypatch never actually reaches the already-decorated route. What makes
    every other POST test in this file pass regardless is that the real
    `rate_limit_trial` fails OPEN whenever `check_rate_limit()` raises (no
    Firebase app initialized in this unit-test process), not the autouse
    fixture. This test exercises that same real, still-attached decorator
    directly: patch `check_rate_limit` at its home module
    (`utils.rate_limit`, where `rate_limit_trial`'s wrapper looks it up at
    call time) rather than a `routes.trial.check_rate_limit` name that was
    never imported there in the first place.
    """
    monkeypatch.setattr("utils.rate_limit.check_rate_limit", lambda: False)
    resp = client_trial.post("/trial/jobs", json={"text": "hi"})
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# DELETE /trial/jobs/<job_id>
# ---------------------------------------------------------------------------

def _mock_doc(exists, data=None):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data or {}
    return doc


@patch("routes.trial.delete_gcs_object")
@patch("routes.trial.firestore_client")
def test_delete_owned_trial_job_returns_204_and_deletes_gcs(mock_fs, mock_delete_gcs, client_trial, auth_ok):
    doc = _mock_doc(True, {"uid": "user-1", "is_trial": True, "input_pdf_gcs_uri": "gs://b/p.pdf"})
    ref = MagicMock()
    ref.get.return_value = doc
    mock_fs.return_value.collection.return_value.document.return_value = ref

    resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
    assert resp.status_code == 204
    mock_delete_gcs.assert_called_once_with("gs://b/p.pdf")
    ref.delete.assert_called_once()


@patch("routes.trial.firestore_client")
def test_delete_nonexistent_job_returns_404(mock_fs, client_trial, auth_ok):
    ref = MagicMock()
    ref.get.return_value = _mock_doc(False)
    mock_fs.return_value.collection.return_value.document.return_value = ref

    resp = client_trial.delete("/trial/jobs/nope", headers=auth_ok)
    assert resp.status_code == 404


@patch("routes.trial.firestore_client")
def test_delete_wrong_uid_returns_403(mock_fs, client_trial, auth_ok):
    doc = _mock_doc(True, {"uid": "someone-else", "is_trial": True})
    ref = MagicMock()
    ref.get.return_value = doc
    mock_fs.return_value.collection.return_value.document.return_value = ref

    resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
    assert resp.status_code == 403
    ref.delete.assert_not_called()


@patch("routes.trial.firestore_client")
def test_delete_non_trial_doc_returns_403_even_with_matching_uid(mock_fs, client_trial, auth_ok):
    doc = _mock_doc(True, {"uid": "user-1", "is_trial": False})
    ref = MagicMock()
    ref.get.return_value = doc
    mock_fs.return_value.collection.return_value.document.return_value = ref

    resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
    assert resp.status_code == 403
    ref.delete.assert_not_called()


def test_delete_unauthenticated_returns_401(client_trial):
    resp = client_trial.delete("/trial/jobs/job-1")
    assert resp.status_code == 401


@patch("routes.trial.firestore_client")
def test_delete_is_not_rate_limited(mock_fs, client_trial, auth_ok):
    """DELETE has no rate_limit_trial decorator at all (§9 Q2) — calling it
    many times in a row never returns 429."""
    doc = _mock_doc(True, {"uid": "user-1", "is_trial": True, "input_pdf_gcs_uri": None})
    ref = MagicMock()
    ref.get.return_value = doc
    mock_fs.return_value.collection.return_value.document.return_value = ref

    for _ in range(10):
        resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
        assert resp.status_code in (204, 404)  # never 429


# ---------------------------------------------------------------------------
# Anonymous callers (Finding 1) — /trial routes must keep working for them
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_anonymous(monkeypatch):
    monkeypatch.setattr(
        "utils.firebase.auth.verify_id_token",
        lambda *a, **k: {"uid": "anon-1", "firebase": {"sign_in_provider": "anonymous", "identities": {}}},
    )
    return {"Authorization": "Bearer anon-token"}


@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
def test_post_anonymous_token_accepted_on_trial_jobs(mock_create_doc, mock_enqueue, client_trial, auth_anonymous):
    resp = client_trial.post("/trial/jobs", json={"text": "Patient has hypertension."}, headers=auth_anonymous)
    assert resp.status_code == 202
    assert "job_id" in resp.get_json()
    mock_create_doc.assert_called_once()
    assert mock_create_doc.call_args.kwargs["user_id"] == "anon-1"


# ---------------------------------------------------------------------------
# Server-side max text length (Finding 2)
# ---------------------------------------------------------------------------

@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
def test_post_text_at_max_length_is_accepted(mock_create_doc, mock_enqueue, client_trial, auth_ok):
    from utils.constants import Constants
    text = "a" * Constants.Uploads.MAX_TEXT_LENGTH
    resp = client_trial.post("/trial/jobs", json={"text": text}, headers=auth_ok)
    assert resp.status_code == 202
    mock_create_doc.assert_called_once()


@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
def test_post_text_over_max_length_returns_400(mock_create_doc, mock_enqueue, client_trial, auth_ok):
    from utils.constants import Constants
    text = "a" * (Constants.Uploads.MAX_TEXT_LENGTH + 1)
    resp = client_trial.post("/trial/jobs", json={"text": text}, headers=auth_ok)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", TRIAL_ENV)
@patch("routes.trial.enqueue_job_safe", return_value=None)
@patch("routes.trial.create_job_doc")
def test_post_uploaded_file_extracted_text_over_max_length_returns_400(
    mock_create_doc, mock_enqueue, client_trial, auth_ok
):
    """Regression: the uploaded-file path never checked extracted text length
    (only the pasted-text path did), so an over-limit uploaded document used
    to sail through every pipeline step before failing late with a
    misleading MAX_TOKENS error. Must now be rejected up front, before any
    job is created or enqueued -- the whole point of the fix."""
    from utils.constants import Constants
    oversized_text = "a" * (Constants.Uploads.MAX_TEXT_LENGTH + 1)
    data = {"files": (BytesIO(oversized_text.encode("utf-8")), "note.txt")}
    resp = client_trial.post(
        "/trial/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()
