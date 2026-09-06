"""POST /care_plan/jobs — create a single async care-plan job."""
import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from opentelemetry import trace as otel_trace
from werkzeug.exceptions import HTTPException

from models.batch_requests import SingleJobRequest
from models.job import JobDoc
from utils.firebase import create_job_doc, verify_firebase_token
from utils.cloud_tasks import enqueue_job_safe, require_env, MissingJobConfigError
from utils.markers.markers import Markers
from utils.markers.marker import Scope
from services.care_plan_input import (
    resolve_uploaded_files,
    upload_combined_pdf,
    fetch_from_gcs,
    extract_text_from_bytes,
    is_allowed_extension,
    validate_extracted_text_length,
)
from utils.constants import Constants
from errors import make_error_response, ErrorCode, JunoError

logger = logging.getLogger(__name__)
care_plan_jobs_bp = Blueprint("care_plan_jobs", __name__)


def _resolve_input_for_job(user_id: str) -> dict:
    json_data = request.get_json(silent=True) or {}
    raw = {
        k: v for k, v in {
            "version": request.form.get("version") or json_data.get("version"),
            "grading_enabled": (
                request.form.get("grading_enabled")
                if request.form.get("grading_enabled") is not None
                else json_data.get("grading_enabled")
            ),
        }.items()
        if v is not None
    }
    req = SingleJobRequest.model_validate(raw)
    version = req.version
    grading_enabled = req.grading_enabled

    text_input = (request.form.get("text") or json_data.get("text") or "").strip()
    if text_input:
        # Shared with routes/trial.py's identical pasted-text check -- enforces
        # the char cap, the UTF-8 byte cap (Finding 1), and rejects unstorable
        # text such as a lone UTF-16 surrogate (Finding 5).
        validate_extracted_text_length(text_input)
        return {
            "input_source_kind": "text",
            "input_text": text_input,
            "input_doc_id": None,
            "input_source_filename": "text_input",
            "input_pdf_gcs_uri": None,
            "input_version": version,
            "grading_enabled": grading_enabled,
        }

    uploads = request.files.getlist("files")
    if not uploads and "file" in request.files:
        uploads = [request.files["file"]]
    if uploads:
        resolved, raw_pdf_bytes = resolve_uploaded_files(uploads)
        pdf_gcs_uri = None
        if raw_pdf_bytes:
            pdf_gcs_uri = upload_combined_pdf(raw_pdf_bytes, user_id)
        return {
            "input_source_kind": "upload",
            "input_text": resolved.text,
            "input_doc_id": None,
            "input_source_filename": resolved.source_filename,
            "input_pdf_gcs_uri": pdf_gcs_uri,
            "input_version": version,
            "grading_enabled": grading_enabled,
        }

    doc_id = (request.form.get("doc_id") or json_data.get("doc_id") or "").strip()
    if doc_id:
        file_bytes, filename = fetch_from_gcs(doc_id)
        if not is_allowed_extension(filename):
            raise ValueError("Stored file must be PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC)")
        if len(file_bytes) > Constants.Uploads.MAX_FILE_BYTES:
            raise ValueError(f"Stored file exceeds {Constants.Uploads.MAX_FILE_BYTES // (1024 * 1024)} MB limit")
        text = extract_text_from_bytes(file_bytes, filename)
        validate_extracted_text_length(text)
        return {
            "input_source_kind": "doc_id",
            "input_text": text,
            "input_doc_id": doc_id,
            "input_source_filename": filename,
            "input_pdf_gcs_uri": None,
            "input_version": version,
            "grading_enabled": grading_enabled,
        }

    raise ValueError("Request must include 'files', 'file', 'text', or 'doc_id'")


@care_plan_jobs_bp.route("/care_plan/jobs", methods=["POST"])
@verify_firebase_token
def create_care_plan_job(user_id: str):
    def _handler(scope: Scope):
        try:
            try:
                input_fields = _resolve_input_for_job(user_id)
            except (ValueError, FileNotFoundError) as exc:
                return make_error_response(
                    ErrorCode.INPUT_VALIDATION_ERROR,
                    request.path,
                    {"field": "input", "reason": str(exc)},
                ).to_dict(), 400
            except JunoError as exc:
                # e.g. EMPTY_DOCUMENT from image OCR finding no text — a known,
                # already-classified failure. Use its own error_code/http_status
                # rather than letting it fall through to the generic 500 below.
                return make_error_response(exc.error_code, request.path).to_dict(), exc.info.http_status

            scope.add_many({
                "grading_enabled": input_fields.get("grading_enabled"),
                "version": input_fields.get("input_version"),
            })

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            span_ctx = otel_trace.get_current_span().get_span_context()
            trace_id = format(span_ctx.trace_id, '032x') if span_ctx.trace_id else None

            job_doc = JobDoc.for_single(
                user_id=user_id,
                now=now,
                trace_id=trace_id,
                input_fields=input_fields,
            )
            create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc.to_firestore())

            try:
                queue_name = require_env("CLOUD_TASKS_QUEUE")
                worker_url = require_env("WORKER_URL")
                service_account = require_env("WORKER_SERVICE_ACCOUNT")
            except MissingJobConfigError:
                logger.exception("care_plan_jobs: missing Cloud Tasks config; cannot enqueue job %s", job_id)
                return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
            if err := enqueue_job_safe(
                job_id,
                queue_name=queue_name,
                worker_url=worker_url,
                service_account=service_account,
                deadline_seconds=Constants.Deadlines.JOB_TIMEOUT_SECONDS_SINGLE,
                path=request.path,
            ):
                return err

            return jsonify({"job_id": job_id}), 202

        except HTTPException:
            # e.g. werkzeug.exceptions.RequestEntityTooLarge raised lazily by
            # request.form/request.get_json() the first time the body is read,
            # once it exceeds app.config["MAX_CONTENT_LENGTH"] -- a bare
            # `except Exception` below would swallow this and misreport it as
            # a generic 500 instead of letting Flask's own @app.errorhandler
            # (413, 404, etc.) produce the correct, standard JSON envelope.
            raise
        except Exception:
            logger.exception("create_care_plan_job: unexpected error")
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

    return Markers.Batch.CreateSingleJob.execute(_handler)
