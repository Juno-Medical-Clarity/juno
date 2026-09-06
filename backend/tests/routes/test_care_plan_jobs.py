"""TDD tests for POST /care_plan/jobs."""
import io
import pytest
from unittest.mock import patch
from flask import Flask

from errors import ErrorCode, JunoError

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
@patch("services.care_plan_input.extract_text_from_image", return_value="OCR'd image text from the clinical scan")
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
    assert "OCR'd image text from the clinical scan" in payload["input_text"]


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
@patch(
    "services.care_plan_input.extract_text_from_image",
    side_effect=JunoError(
        ErrorCode.EMPTY_DOCUMENT,
        detail="Image contained no readable text (model returned NO_TEXT_FOUND).",
    ),
)
def test_create_care_plan_job_blurry_image_returns_422_empty_document(
    mock_extract_image, mock_create_doc, mock_enqueue, client_jobs, auth_ok
):
    """Regression test: extract_text_from_image raising JunoError(EMPTY_DOCUMENT)
    for an unreadable/blurry image must surface as 422 EMPTY_DOCUMENT, not fall
    through the generic `except Exception` to a 500 INTERNAL_ERROR."""
    resp = client_jobs.post(
        "/care_plan/jobs",
        data={"files": (io.BytesIO(_ONE_PX_PNG), "photo.png")},
        content_type="multipart/form-data",
        headers=auth_ok,
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["error"]["code"] == "EMPTY_DOCUMENT"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


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


# ---------------------------------------------------------------------------
# Anonymous callers (Finding 1) — POST /care_plan/jobs is the primary attack
# surface: an anonymous trial token must never work here.
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_anonymous(monkeypatch):
    monkeypatch.setattr(
        "utils.firebase.auth.verify_id_token",
        lambda *a, **k: {"uid": "anon-1", "firebase": {"sign_in_provider": "anonymous", "identities": {}}},
    )
    return {"Authorization": "Bearer anon-token"}


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_anonymous_token_returns_403(mock_create_doc, mock_enqueue, client_jobs, auth_anonymous):
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "Patient has hypertension."},
        headers=auth_anonymous,
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "ANONYMOUS_ACCESS_FORBIDDEN"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_non_anonymous_token_still_accepted(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    """Regression guard: a normal signed-in user must be unaffected by the
    anonymous-caller deny added for Finding 1."""
    resp = client_jobs.post(
        "/care_plan/jobs",
        json={"text": "Patient has hypertension."},
        headers=auth_ok,
    )
    assert resp.status_code == 202
    mock_create_doc.assert_called_once()


# ---------------------------------------------------------------------------
# Server-side max text length (Finding 2)
# ---------------------------------------------------------------------------

@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_text_at_max_length_is_accepted(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    from utils.constants import Constants
    text = "a" * Constants.Uploads.MAX_TEXT_BYTES
    resp = client_jobs.post("/care_plan/jobs", json={"text": text}, headers=auth_ok)
    assert resp.status_code == 202
    mock_create_doc.assert_called_once()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_text_over_max_length_returns_400(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    from utils.constants import Constants
    text = "a" * (Constants.Uploads.MAX_TEXT_LENGTH + 1)
    resp = client_jobs.post("/care_plan/jobs", json={"text": text}, headers=auth_ok)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_uploaded_file_extracted_text_over_max_length_returns_400(
    mock_create_doc, mock_enqueue, client_jobs, auth_ok
):
    """Regression: same gap as the trial route -- the uploaded-file path never
    checked extracted text length. Must be rejected up front, before any job
    is created or enqueued."""
    from utils.constants import Constants
    oversized_text = "a" * (Constants.Uploads.MAX_TEXT_LENGTH + 1)
    data = {"files": (io.BytesIO(oversized_text.encode("utf-8")), "note.txt")}
    resp = client_jobs.post(
        "/care_plan/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
@patch("routes.care_plan_jobs.fetch_from_gcs")
def test_post_doc_id_extracted_text_over_max_length_returns_400(
    mock_fetch_from_gcs, mock_create_doc, mock_enqueue, client_jobs, auth_ok
):
    """The doc_id (previously-uploaded, referenced by id) path had the same
    gap as the direct-upload path -- extracted text length was never
    checked. Must be rejected up front, before any job is created."""
    from utils.constants import Constants
    oversized_text = "a" * (Constants.Uploads.MAX_TEXT_LENGTH + 1)
    mock_fetch_from_gcs.return_value = (oversized_text.encode("utf-8"), "note.txt")

    resp = client_jobs.post("/care_plan/jobs", json={"doc_id": "some-doc-id"}, headers=auth_ok)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_cjk_text_under_char_cap_but_over_byte_cap_returns_400(mock_create_doc, mock_enqueue, client_jobs, auth_ok):
    """Regression for edge-case review Finding 1, applies to the main app
    too (validate_extracted_text_length is shared): CJK text under the
    500,000-char cap but over the UTF-8 byte cap must be rejected cleanly."""
    from utils.constants import Constants
    char_count = (Constants.Uploads.MAX_TEXT_BYTES // 3) + 100
    assert char_count < Constants.Uploads.MAX_TEXT_LENGTH
    text = "中" * char_count
    resp = client_jobs.post("/care_plan/jobs", json={"text": text}, headers=auth_ok)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_text_with_lone_surrogate_returns_400_not_500(mock_create_doc, client_jobs, auth_ok):
    """Regression for Finding 5, applies to the main app too."""
    resp = client_jobs.post(
        "/care_plan/jobs",
        data='{"text": "hello \\ud800 world"}',
        headers={**auth_ok, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
    mock_create_doc.assert_not_called()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.enqueue_job_safe", return_value=None)
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_multipart_one_blank_file_among_several_still_aborts_main_app(
    mock_create_doc, mock_enqueue, client_jobs, auth_ok
):
    """Regression guard: main-app behavior for Finding 8 is UNCHANGED -- one
    unusable file among several still aborts the whole request (tolerant
    multi-file handling is trial-only)."""
    data = {
        "files": [
            (io.BytesIO(b"This is a perfectly good clinical note about hypertension."), "good.txt"),
            (io.BytesIO(b"   "), "blank.txt"),
        ]
    }
    resp = client_jobs.post(
        "/care_plan/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "EMPTY_DOCUMENT"
    mock_create_doc.assert_not_called()
    mock_enqueue.assert_not_called()


@patch.dict("os.environ", {
    "CLOUD_TASKS_QUEUE": "my-queue",
    "WORKER_URL": "https://worker.run.app",
    "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
})
@patch("routes.care_plan_jobs.create_job_doc")
def test_post_corrupt_pdf_returns_400_not_500(mock_create_doc, client_jobs, auth_ok):
    """Regression for Finding 6, applies to the main app too."""
    data = {"files": (io.BytesIO(b"garbage, not a real pdf"), "notes.pdf")}
    resp = client_jobs.post(
        "/care_plan/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "FILE_PARSE_FAILED"
    mock_create_doc.assert_not_called()


def test_resolve_uploaded_files_main_app_call_site_uses_default_limits():
    """Regression guard: routes.care_plan_jobs must call resolve_uploaded_files
    with NO overrides, so it keeps Constants.Uploads' main-app defaults (10
    files / 10 MB per file / 25 MB aggregate) exactly as before this change."""
    import inspect
    from routes import care_plan_jobs as care_plan_jobs_module

    source = inspect.getsource(care_plan_jobs_module._resolve_input_for_job)
    assert "resolve_uploaded_files(uploads)" in source
