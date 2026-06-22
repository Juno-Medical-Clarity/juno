"""POST /internal/jobs/execute/<job_id> — worker endpoint for Cloud Tasks."""
import json
import logging
import time
from datetime import datetime, timezone

from flask import Blueprint, request

from utils.firebase import get_job_doc, update_job_stage, complete_job, fail_job
from routes.care_plan import (
    run_care_plan_pipeline,
    _fetch_from_gcs,
    _extract_text_from_bytes,
)
from models.envelope import CarePlanInternal
from models.input import TextInput, DocIdInput
from models.metrics import Metrics
from utils.constants import Constants

logger = logging.getLogger(__name__)
worker_bp = Blueprint("worker", __name__)

SINGLE_JOB_INTERNAL_DEADLINE_S = 270
BATCH_ITEM_INTERNAL_DEADLINE_S = 870

PIPELINES = {Constants.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}


def _is_batch_item(job_doc: dict) -> bool:
    return job_doc.get("batch_group_id") is not None


def _resolve_input_from_job_doc(job_doc: dict) -> str:
    source_kind = job_doc.get("input_source_kind", "text")
    if source_kind == "doc_id":
        doc_id = job_doc["input_doc_id"]
        file_bytes, filename = _fetch_from_gcs(doc_id)
        return _extract_text_from_bytes(file_bytes, filename)
    return job_doc.get("input_text") or ""


def _build_error_data(code: str, message: str) -> dict:
    return {"code": code, "message": message}


@worker_bp.route("/internal/jobs/execute/<job_id>", methods=["POST"])
def execute_job(job_id: str):
    queue_name_header = request.headers.get("X-CloudTasks-QueueName", "").strip()
    if not queue_name_header:
        logger.warning("worker: rejected request without X-CloudTasks-QueueName")
        return "", 403

    try:
        job_doc = get_job_doc(job_id)
        if job_doc is None:
            logger.warning("worker: job doc not found for job_id=%s — skipping", job_id)
            return "", 200

        if job_doc.get("status") in ("completed", "error"):
            logger.info("worker: job %s already in terminal state %s — idempotent return", job_id, job_doc["status"])
            return "", 200

        uid = job_doc.get("uid")
        batch_run_id = job_doc.get("batch_run_id")

        from utils.firebase import firestore_client
        now = datetime.now(timezone.utc)
        firestore_client().collection("care_plan_outputs").document(job_id).update({
            "status": "processing",
            "started_at": now,
            "stage": 1,
            "updated_at": now,
        })

        deadline_s = (
            BATCH_ITEM_INTERNAL_DEADLINE_S
            if _is_batch_item(job_doc)
            else SINGLE_JOB_INTERNAL_DEADLINE_S
        )
        start = time.monotonic()

        def _check_timeout(stage: int) -> bool:
            elapsed = time.monotonic() - start
            if elapsed > deadline_s:
                fail_job(job_id, _build_error_data("JOB_TIMEOUT", "Job timed out"))
                logger.warning("worker: job %s timed out at stage %d after %.1fs", job_id, stage, elapsed)
                return True
            return False

        text = _resolve_input_from_job_doc(job_doc)
        if not text.strip():
            fail_job(job_id, _build_error_data("PIPELINE_ERROR", "Input text is empty"))
            return "", 200

        version = job_doc.get("input_version", "v1-2")
        grading_enabled = job_doc.get("grading_enabled", False)
        source_kind = job_doc.get("input_source_kind", "text")
        is_batch = _is_batch_item(job_doc)

        pipeline_fn = PIPELINES.get(version, PIPELINES["v1-2"])

        metrics = Metrics.start(
            session_id=job_id,
            pipeline_version=version,
            input_type=source_kind,
        )

        current_stage = 1
        pipeline_result = None
        pipeline_error: str | None = None

        for chunk in pipeline_fn(text, metrics, grading_enabled, source_kind=source_kind, is_batch=is_batch):
            if isinstance(chunk, tuple) and chunk and chunk[0] == Constants.RESULT_SENTINEL:
                pipeline_result = chunk
                continue

            if isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    payload = json.loads(chunk.removeprefix("data: ").strip())
                except Exception:
                    continue

                if payload.get("step") == "error":
                    pipeline_error = payload.get("error") or "Pipeline failed"
                    break

                step = payload.get("step")
                status = payload.get("status")
                if isinstance(step, int) and status == "active" and step != current_stage:
                    current_stage = step
                    if _check_timeout(current_stage):
                        return "", 200
                    update_job_stage(job_id, current_stage)

        if pipeline_error is not None:
            fail_job(job_id, _build_error_data("PIPELINE_ERROR", pipeline_error))
            return "", 200

        if pipeline_result is None:
            fail_job(job_id, _build_error_data("PIPELINE_ERROR", "Pipeline returned no result"))
            return "", 200

        _, care_plan, grading, _raw_text, _clarified_text = pipeline_result

        if source_kind == "doc_id":
            input_model = DocIdInput(doc_id=job_doc["input_doc_id"])
        else:
            input_model = TextInput(text=text)

        envelope = CarePlanInternal(
            metrics=metrics,
            input=input_model,
            grading=grading,
            care_plan=care_plan,
        )
        output_data = envelope.to_dict()

        name = _derive_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))
        output_data["metrics"]["saved_id"] = job_id

        complete_job(job_id, output_data, name)
        logger.info("worker: job %s completed", job_id, extra={"job_id": job_id, "batch_run_id": batch_run_id, "uid": uid, "stage": 5})
        return "", 200

    except Exception:
        logger.exception("worker: unexpected error for job %s", job_id, extra={"job_id": job_id})
        return "", 500


def _derive_name(care_plan_data: dict, source_filename: str) -> str:
    try:
        rfv = care_plan_data.get("reason_for_visit")
        if rfv and isinstance(rfv, list):
            reason = (rfv[0].get("reason") or "").strip()
            if reason:
                return reason.title()[:60]
        diagnosis = care_plan_data.get("diagnosis") or {}
        main = (diagnosis.get("main_conclusion") or "").strip()
        if main:
            first_sentence = main.split(".")[0].strip()
            if first_sentence:
                return first_sentence[:60]
    except Exception:
        pass
    filename = source_filename or ""
    if filename and filename != "text_input":
        stem = filename.split(",")[0].strip()
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        stem = stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return stem.title()[:60]
    return "Appointment"
