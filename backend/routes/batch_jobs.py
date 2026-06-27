"""POST /care_plan/batch/jobs — create async batch care-plan jobs."""
import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from utils.firebase import create_job_doc, verify_firebase_token
from utils.cloud_tasks import enqueue_job, require_env, MissingJobConfigError
from routes.batch import _resolve_requested_runs, _batch_timestamp
from utils.constants import Constants
from utils.error_codes import make_error_response, ErrorCode

logger = logging.getLogger(__name__)
batch_jobs_bp = Blueprint("batch_jobs", __name__)


@batch_jobs_bp.route("/care_plan/batch/jobs", methods=["POST"])
@verify_firebase_token
def create_care_plan_batch_jobs(user_id: str):
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return make_error_response(
            ErrorCode.INPUT_VALIDATION_ERROR,
            request.path,
            {"field": "body", "reason": "Request body must be a JSON object"},
        ).to_dict(), 400

    selections = body.get("selections")
    if not isinstance(selections, list) or not selections:
        return make_error_response(
            ErrorCode.INPUT_VALIDATION_ERROR,
            request.path,
            {"field": "selections", "reason": "Request must include a non-empty selections list"},
        ).to_dict(), 400

    version = body.get("version", "v1-2")
    grading_enabled_raw = body.get("grading_enabled", False)
    grading_enabled = grading_enabled_raw if isinstance(grading_enabled_raw, bool) \
        else str(grading_enabled_raw).strip().lower() in {"1", "true", "yes", "on"}

    # ── Partition selections ─────────────────────────────────────────────────
    ATHENA_KINDS = {"athena_encounter", "athena_clinical_doc"}
    athena_selections = [
        s for s in selections
        if isinstance(s, dict) and s.get("input_source_kind") in ATHENA_KINDS
    ]
    gcs_selections = [
        s for s in selections
        if s not in athena_selections
    ]

    # ── Resolve GCS runs ────────────────────────────────────────────────────
    runs: list[tuple[str, str, list[str]]] = []
    if gcs_selections:
        try:
            runs = _resolve_requested_runs(gcs_selections)
        except (ValueError, FileNotFoundError) as exc:
            return make_error_response(
                ErrorCode.BATCH_INVALID_SELECTION,
                request.path,
                {"detail": str(exc)},
            ).to_dict(), 400

    total_count = len(runs) + len(athena_selections)
    if total_count > Constants.MAX_BATCH_RUNS:
        return make_error_response(
            ErrorCode.BATCH_TOO_LARGE,
            request.path,
            {"count": total_count, "max_runs": Constants.MAX_BATCH_RUNS},
        ).to_dict(), 400

    batch_run_id = str(uuid.uuid4())
    timestamp = _batch_timestamp()
    now = datetime.now(timezone.utc)
    job_ids: list[str] = []
    deadline_s = int(os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900"))

    # ── GCS dataset job docs ────────────────────────────────────────────────
    gcs_groups = sorted({group for group, _, _ in runs})
    batch_group_ids = {group: f"{group}-{timestamp}" for group in gcs_groups}

    for group, input_id, files in runs:
        job_id = str(uuid.uuid4())
        batch_group_id = batch_group_ids[group]
        source_filename = ", ".join(files)

        job_doc = {
            "uid": user_id,
            "name": now.strftime("%b %d, %Y %H:%M"),
            "source_filename": source_filename,
            "created_at": now,
            "updated_at": now,
            "status": "not_started",
            "stage": None,
            "started_at": None,
            "completed_at": None,
            "output_data": None,
            "error_data": None,
            "batch_run_id": batch_run_id,
            "batch_group_id": batch_group_id,
            "dataset_group": group,
            "dataset_input_id": input_id,
            "dataset_files": files,
            "input_source_kind": "gcs_batch_dataset",
            "input_text": None,
            "input_doc_id": None,
            "input_source_filename": source_filename,
            "input_pdf_gcs_uri": None,
            "input_version": version,
            "grading_enabled": grading_enabled,
            # Athena fields null for GCS jobs
            "athena_practice_id": None,
            "athena_patient_id": None,
            "athena_encounter_id": None,
            "athena_document_id": None,
            "athena_api_path": None,
        }
        create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

        try:
            enqueue_job(
                job_id,
                queue_name=require_env("CLOUD_TASKS_QUEUE"),
                worker_url=require_env("WORKER_URL"),
                service_account=require_env("WORKER_SERVICE_ACCOUNT"),
                deadline_seconds=deadline_s,
                batch_run_id=batch_run_id,
            )
        except MissingJobConfigError:
            logger.exception(
                "batch_jobs: missing Cloud Tasks config; cannot enqueue job %s", job_id
            )
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
        except Exception:
            logger.exception("batch_jobs: failed to enqueue Cloud Task for job %s", job_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

        job_ids.append(job_id)

    # ── Athena job docs ─────────────────────────────────────────────────────
    athena_batch_group_id = f"athena-{timestamp}"

    for sel in athena_selections:
        source_kind = sel["input_source_kind"]
        practice_id = sel.get("athena_practice_id", "")
        patient_id = sel.get("athena_patient_id", "")
        encounter_id = sel.get("athena_encounter_id")
        document_id = sel.get("athena_document_id")
        api_path = sel.get("athena_api_path", "")

        if source_kind == "athena_encounter":
            if not encounter_id:
                return make_error_response(
                    ErrorCode.BATCH_INVALID_SELECTION,
                    request.path,
                    {"detail": "athena_encounter requires athena_encounter_id"},
                ).to_dict(), 400
            source_filename = f"athena_encounter_{encounter_id}"
        else:  # athena_clinical_doc
            if not document_id:
                return make_error_response(
                    ErrorCode.BATCH_INVALID_SELECTION,
                    request.path,
                    {"detail": "athena_clinical_doc requires athena_document_id"},
                ).to_dict(), 400
            source_filename = f"athena_doc_{document_id}"

        job_id = str(uuid.uuid4())
        job_doc = {
            "uid": user_id,
            "name": now.strftime("%b %d, %Y %H:%M"),
            "source_filename": source_filename,
            "created_at": now,
            "updated_at": now,
            "status": "not_started",
            "stage": None,
            "started_at": None,
            "completed_at": None,
            "output_data": None,
            "error_data": None,
            "batch_run_id": batch_run_id,
            "batch_group_id": athena_batch_group_id,
            # GCS dataset fields null for Athena jobs
            "dataset_group": None,
            "dataset_input_id": None,
            "dataset_files": None,
            "input_source_kind": source_kind,
            "input_text": None,
            "input_doc_id": None,
            "input_source_filename": source_filename,
            "input_pdf_gcs_uri": None,
            "input_version": version,
            "grading_enabled": grading_enabled,
            # Athena-specific fields
            "athena_practice_id": practice_id,
            "athena_patient_id": patient_id,
            "athena_encounter_id": encounter_id,
            "athena_document_id": document_id,
            "athena_api_path": api_path,
        }
        create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

        try:
            enqueue_job(
                job_id,
                queue_name=require_env("CLOUD_TASKS_QUEUE"),
                worker_url=require_env("WORKER_URL"),
                service_account=require_env("WORKER_SERVICE_ACCOUNT"),
                deadline_seconds=deadline_s,
                batch_run_id=batch_run_id,
            )
        except MissingJobConfigError:
            logger.exception(
                "batch_jobs: missing Cloud Tasks config; cannot enqueue Athena job %s", job_id
            )
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
        except Exception:
            logger.exception("batch_jobs: failed to enqueue Athena Cloud Task for job %s", job_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

        job_ids.append(job_id)

    return jsonify({"batch_run_id": batch_run_id, "job_ids": job_ids}), 202
