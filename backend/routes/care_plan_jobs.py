"""POST /care_plan/jobs — create a single async care-plan job."""
import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from utils.firebase import create_job_doc, verify_firebase_token
from utils.cloud_tasks import enqueue_job
from routes.care_plan import (
    _resolve_uploaded_files,
    upload_combined_pdf,
    _fetch_from_gcs,
    _extract_text_from_bytes,
    _grading_enabled_from_request,
    _allowed,
)
from utils.constants import Constants

logger = logging.getLogger(__name__)
care_plan_jobs_bp = Blueprint("care_plan_jobs", __name__)


def _resolve_input_for_job(user_id: str) -> dict:
    json_data = request.get_json(silent=True) or {}
    version = (request.form.get("version") or json_data.get("version") or "v1-2")
    grading_enabled = _grading_enabled_from_request()

    text_input = (request.form.get("text") or json_data.get("text") or "").strip()
    if text_input:
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
        resolved = _resolve_uploaded_files(uploads)
        pdf_gcs_uri = None
        if resolved.combined_pdf_bytes:
            pdf_gcs_uri = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
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
        file_bytes, filename = _fetch_from_gcs(doc_id)
        if not _allowed(filename):
            raise ValueError("Stored file must be PDF, TXT, or DOCX")
        if len(file_bytes) > Constants.MAX_FILE_BYTES:
            raise ValueError("Stored file exceeds 10 MB limit")
        text = _extract_text_from_bytes(file_bytes, filename)
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
    try:
        input_fields = _resolve_input_for_job(user_id)
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    job_doc = {
        "uid": user_id,
        "name": "Processing…",
        "source_filename": input_fields["input_source_filename"],
        "created_at": now,
        "updated_at": now,
        "status": "not_started",
        "stage": None,
        "started_at": None,
        "completed_at": None,
        "output_data": None,
        "error_data": None,
        "batch_run_id": None,
        "batch_group_id": None,
        "dataset_group": None,
        **input_fields,
    }
    create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

    try:
        enqueue_job(
            job_id,
            queue_name=os.environ["CLOUD_TASKS_QUEUE"],
            worker_url=os.environ["WORKER_URL"],
            service_account=os.environ["WORKER_SERVICE_ACCOUNT"],
            deadline_seconds=int(os.environ.get("JOB_TIMEOUT_SECONDS_SINGLE", "300")),
        )
    except Exception:
        logger.exception("care_plan_jobs: failed to enqueue Cloud Task for job %s", job_id)
        return jsonify({"error": "Failed to enqueue job"}), 500

    return jsonify({"job_id": job_id}), 202
