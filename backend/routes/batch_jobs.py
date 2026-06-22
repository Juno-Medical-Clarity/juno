"""POST /care_plan/batch/jobs — create async batch care-plan jobs."""
import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from utils.firebase import create_job_doc, verify_firebase_token
from utils.cloud_tasks import enqueue_job
from routes.batch import _resolve_requested_runs, _combined_text_for_dataset_input, _batch_timestamp
from utils.constants import Constants

logger = logging.getLogger(__name__)
batch_jobs_bp = Blueprint("batch_jobs", __name__)


@batch_jobs_bp.route("/care_plan/batch/jobs", methods=["POST"])
@verify_firebase_token
def create_care_plan_batch_jobs(user_id: str):
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    selections = body.get("selections")
    if not isinstance(selections, list) or not selections:
        return jsonify({"error": "Request must include selections"}), 400

    version = body.get("version", "v1-2")
    grading_enabled_raw = body.get("grading_enabled", False)
    grading_enabled = grading_enabled_raw if isinstance(grading_enabled_raw, bool) \
        else str(grading_enabled_raw).strip().lower() in {"1", "true", "yes", "on"}

    try:
        runs = _resolve_requested_runs(selections)
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400

    if len(runs) > Constants.MAX_BATCH_RUNS:
        return jsonify({"error": f"Batch request exceeds maximum of {Constants.MAX_BATCH_RUNS} runs"}), 400

    batch_run_id = str(uuid.uuid4())
    timestamp = _batch_timestamp()
    batch_group_ids = {
        group: f"{group}-{timestamp}"
        for group in sorted({group for group, _, _ in runs})
    }

    now = datetime.now(timezone.utc)
    job_ids: list[str] = []
    deadline_s = int(os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900"))

    for group, input_id, files in runs:
        try:
            text = _combined_text_for_dataset_input(group, input_id, files)
        except Exception as exc:
            logger.exception("batch_jobs: failed to read dataset input %s/%s", group, input_id)
            return jsonify({"error": f"Could not read dataset input {group}/{input_id}: {exc}"}), 400

        job_id = str(uuid.uuid4())
        batch_group_id = batch_group_ids[group]
        source_filename = ", ".join(files)

        job_doc = {
            "uid": user_id,
            "name": "Processing…",
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
            "input_source_kind": "batch_dataset",
            "input_text": text,
            "input_doc_id": None,
            "input_source_filename": source_filename,
            "input_pdf_gcs_uri": None,
            "input_version": version,
            "grading_enabled": grading_enabled,
        }
        create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

        try:
            enqueue_job(
                job_id,
                queue_name=os.environ["CLOUD_TASKS_QUEUE"],
                worker_url=os.environ["WORKER_URL"],
                service_account=os.environ["WORKER_SERVICE_ACCOUNT"],
                deadline_seconds=deadline_s,
                batch_run_id=batch_run_id,
            )
        except Exception:
            logger.exception("batch_jobs: failed to enqueue Cloud Task for job %s", job_id)
            return jsonify({"error": f"Failed to enqueue job {job_id}"}), 500

        job_ids.append(job_id)

    return jsonify({"batch_run_id": batch_run_id, "job_ids": job_ids}), 202
