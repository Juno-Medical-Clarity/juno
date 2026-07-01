"""POST /care_plan/batch/jobs — create async batch care-plan jobs."""
import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from utils.firebase import create_job_doc, verify_firebase_token
from utils.cloud_tasks import enqueue_job, require_env, MissingJobConfigError
from utils.batch import resolve_requested_runs, batch_timestamp
from utils.constants import Constants
from errors import make_error_response, ErrorCode
from models.batch_requests import (
    BatchJobsRequest,
    AthenaEncounterSelection,
    AthenaClinicalDocSelection,
    GcsDatasetSelection,
)
from models.job import JobDoc
from utils.markers.markers import Markers
from utils.markers.marker import Scope

logger = logging.getLogger(__name__)
batch_jobs_bp = Blueprint("batch_jobs", __name__)


def _source_kind_label(athena_n: int, gcs_n: int) -> str:
    if athena_n == 0 and gcs_n == 0:
        return "empty"
    if athena_n == 0:
        return "all_gcs"
    if gcs_n == 0:
        return "all_athena"
    return "mixed"


@batch_jobs_bp.route("/care_plan/batch/jobs", methods=["POST"])
@verify_firebase_token
def create_care_plan_batch_jobs(user_id: str):
    def _handler(scope: Scope):
        try:
            # ── Parse and validate request ────────────────────────────────────
            try:
                req = BatchJobsRequest.model_validate(request.get_json(silent=True) or {})
            except ValidationError as exc:
                return make_error_response(
                    ErrorCode.INPUT_VALIDATION_ERROR,
                    request.path,
                    {"detail": str(exc)},
                ).to_dict(), 400

            # ── Partition selections ──────────────────────────────────────────
            athena_selections = [
                s for s in req.selections
                if isinstance(s, (AthenaEncounterSelection, AthenaClinicalDocSelection))
            ]
            gcs_selections = [
                s for s in req.selections
                if isinstance(s, GcsDatasetSelection)
            ]

            # ── Resolve GCS runs ──────────────────────────────────────────────
            runs: list[tuple[str, str, list[str]]] = []
            if gcs_selections:
                try:
                    runs = resolve_requested_runs([s.model_dump() for s in gcs_selections])
                except (ValueError, FileNotFoundError) as exc:
                    return make_error_response(
                        ErrorCode.BATCH_INVALID_SELECTION,
                        request.path,
                        {"detail": str(exc)},
                    ).to_dict(), 400

            # ── Check total job count ─────────────────────────────────────────
            total_count = len(runs) + len(athena_selections)
            if total_count > Constants.Batch.MAX_BATCH_RUNS:
                return make_error_response(
                    ErrorCode.BATCH_TOO_LARGE,
                    request.path,
                    {"count": total_count, "max_runs": Constants.Batch.MAX_BATCH_RUNS},
                ).to_dict(), 400

            scope.add_many({
                "batch_size": total_count,
                "athena_count": len(athena_selections),
                "gcs_count": len(runs),
                "grading_enabled": req.grading_enabled,
                "version": req.version,
                "source_kind": _source_kind_label(len(athena_selections), len(runs)),
            })

            batch_run_id = str(uuid.uuid4())
            timestamp = batch_timestamp()
            now = datetime.now(timezone.utc)
            job_ids: list[str] = []
            deadline_s = Constants.Deadlines.JOB_TIMEOUT_SECONDS_BATCH

            # ── GCS dataset job docs ──────────────────────────────────────────
            gcs_groups = sorted({group for group, _, _ in runs})
            batch_group_ids = {group: f"{group}-{timestamp}" for group in gcs_groups}

            for group, input_id, files in runs:
                job_id = str(uuid.uuid4())
                batch_group_id = batch_group_ids[group]
                source_filename = ", ".join(files)

                job_doc = JobDoc.for_gcs_dataset(
                    user_id=user_id,
                    now=now,
                    version=req.version,
                    grading_enabled=req.grading_enabled,
                    batch_run_id=batch_run_id,
                    batch_group_id=batch_group_id,
                    dataset_group=group,
                    dataset_input_id=input_id,
                    dataset_files=files,
                    source_filename=source_filename,
                )
                create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc.to_firestore())

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

            # ── Athena job docs ───────────────────────────────────────────────
            athena_batch_group_id = f"athena-{timestamp}"
            AthenaSourceKind = Constants.Athena.AthenaSourceKind

            for sel in athena_selections:
                if isinstance(sel, AthenaEncounterSelection):
                    source_kind = AthenaSourceKind.ATHENA_ENCOUNTER
                    source_filename = f"athena_encounter_{sel.athena_encounter_id}"
                else:
                    source_kind = AthenaSourceKind.ATHENA_CLINICAL_DOC
                    source_filename = f"athena_doc_{sel.athena_document_id}"

                job_id = str(uuid.uuid4())
                job_doc = JobDoc.for_athena(
                    user_id=user_id,
                    now=now,
                    version=req.version,
                    grading_enabled=req.grading_enabled,
                    batch_run_id=batch_run_id,
                    batch_group_id=athena_batch_group_id,
                    source_kind=source_kind,
                    source_filename=source_filename,
                    practice_id=sel.athena_practice_id,
                    patient_id=sel.athena_patient_id,
                    encounter_id=sel.athena_encounter_id,
                    document_id=sel.athena_document_id,
                    api_path=sel.athena_api_path,
                )
                create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc.to_firestore())

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

        except Exception:
            logger.exception("create_care_plan_batch_jobs: unexpected error")
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

    return Markers.Batch.CreateJobs.execute(_handler)
