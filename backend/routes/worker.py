"""POST /internal/jobs/execute/<job_id> — worker endpoint for Cloud Tasks."""

# ── Imports & blueprint setup ──────────────────────────────────────────────────
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, request

from utils.firebase import get_job_doc, update_job_stage, complete_job, fail_job
from routes.care_plan import (
    run_care_plan_pipeline,
    _fetch_from_gcs,
    _extract_text_from_bytes,
    AdapterStepEvent,
    AdapterResult,
    AdapterError,
)
from models.care_plan.envelope import CarePlanInternal
from models.job import JobDoc
from models.input import TextInput, DocIdInput
from models.metrics import Metrics
from utils.constants import Constants
from errors import ErrorCode, build_error_data, build_error_data_from_exc

logger = logging.getLogger(__name__)
worker_bp = Blueprint("worker", __name__)

PIPELINES = {Constants.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}

# ── Configuration constants ────────────────────────────────────────────────────
# Map job-doc input_source_kind values onto the canonical Metrics.input_type
# allowed values ("file" | "text" | "doc_id").
_INPUT_TYPE_MAP = {
    "upload": "file",
    "batch_dataset": "text",       # legacy, pre-extracted text
    "gcs_batch_dataset": "text",   # new, downloads from GCS at worker time
    "doc_id": "doc_id",
    "text": "text",
    "athena_encounter": "text",    # new SP3 — live Athena encounter fetch
    "athena_clinical_doc": "text", # new SP3 — live Athena clinical doc fetch
}


def _canonical_input_type(source_kind: str) -> str:
    return _INPUT_TYPE_MAP.get(source_kind, "text")


def _is_batch_item(job: JobDoc) -> bool:
    return job.batch_group_id is not None


# ── Input resolution ───────────────────────────────────────────────────────────
def _resolve_input_from_job_doc(job: JobDoc) -> str:
    if job.input_source_kind == "doc_id":
        file_bytes, filename = _fetch_from_gcs(job.input_doc_id)
        return _extract_text_from_bytes(file_bytes, filename)
    return job.input_text or ""


def _build_error_data(code: ErrorCode, detail: str = "") -> dict:
    """Build the rich error_data dict for a worker-originated failure.

    Uses the new error catalog (error_codes.py) to produce a Firestore-ready
    dict with code, message, user_hint, retryable, and detail fields.
    """
    return build_error_data(code, detail)


def _extract_text_from_downloaded(
    base_dir: Path, group: str, input_id: str, files: list[str]
) -> str:
    parts: list[str] = []
    has_text = False
    for filename in files:
        local_path = base_dir / group / input_id / filename
        file_bytes = local_path.read_bytes()
        text = _extract_text_from_bytes(file_bytes, filename).strip()
        has_text = has_text or bool(text)
        parts.append(f"\n\n--- {filename} ---\n\n{text}")
    return "".join(parts) if has_text else ""


# ── OIDC token verification ────────────────────────────────────────────────────
def _verify_oidc_token() -> bool:
    """Verify the Google-signed OIDC token Cloud Tasks attaches to worker requests.

    Cloud Tasks signs each dispatch with an OIDC JWT issued for the worker service
    account, using the full execute URL as the token audience (see
    ``utils/cloud_tasks.enqueue_job``). This validates that signed token so the
    publicly-reachable worker route cannot be invoked by arbitrary callers.

    Returns True if the request is authorized, False otherwise. Callers should
    translate a False result into an HTTP 403. Never logs token contents.

    Behavior:
      - Kill-switch: if ``WORKER_VERIFY_OIDC`` is false/0/no, verification is
        skipped (for local/dev/tests). Verification is ENABLED by default.
      - Requires an ``Authorization: Bearer <token>`` header.
      - Verifies the JWT signature/issuer/expiry via google-auth.
      - Requires ``email_verified`` to be truthy.
      - If ``WORKER_SERVICE_ACCOUNT`` is set, requires the token ``email`` to match.
      - Requires the token ``aud`` to equal the (proxy-aware) request URL.
    """
    if os.environ.get("WORKER_VERIFY_OIDC", "true").lower() in ("false", "0", "no"):
        return True

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("worker: rejected request without Bearer Authorization header")
        return False
    token = auth_header[len("Bearer "):].strip()
    if not token:
        logger.warning("worker: rejected request with empty Bearer token")
        return False

    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

    try:
        claims = google_id_token.verify_oauth2_token(token, google_requests.Request())
    except Exception as exc:
        logger.warning("worker: OIDC token verification failed: %s", type(exc).__name__)
        return False

    if not claims.get("email_verified"):
        logger.warning("worker: rejected OIDC token with unverified email")
        return False

    expected_email = os.environ.get("WORKER_SERVICE_ACCOUNT")
    if expected_email and claims.get("email") != expected_email:
        logger.warning(
            "worker: rejected OIDC token with service-account email mismatch "
            "(got=%s expected=%s)", claims.get("email"), expected_email
        )
        return False

    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    expected_aud = f"{proto}://{request.host}{request.path}"
    if claims.get("aud") != expected_aud:
        logger.warning(
            "worker: rejected OIDC token with audience mismatch (got=%s expected=%s)",
            claims.get("aud"), expected_aud
        )
        return False

    return True


# ── Job execution handler ──────────────────────────────────────────────────────
@worker_bp.route("/internal/jobs/execute/<job_id>", methods=["POST"])
def execute_job(job_id: str):
    queue_name_header = request.headers.get("X-CloudTasks-QueueName", "").strip()
    if not queue_name_header:
        logger.warning("worker: rejected request without X-CloudTasks-QueueName")
        return "", 403

    if not _verify_oidc_token():
        return "", 403

    gcs_temp_dir: Path | None = None
    is_gcs_dataset_job = False

    try:
        job_doc = get_job_doc(job_id)
        if job_doc is None:
            logger.warning("worker: job doc not found for job_id=%s — skipping", job_id)
            return "", 200

        job = JobDoc.from_firestore(job_doc)

        if job.status in ("completed", "error"):
            logger.info("worker: job %s already in terminal state %s — idempotent return", job_id, job.status)
            return "", 200

        uid = job.uid
        batch_run_id = job.batch_run_id

        from utils.firebase import firestore_client
        now = datetime.now(timezone.utc)
        firestore_client().collection("care_plan_outputs").document(job_id).update({
            "status": "processing",
            "started_at": now,
            "stage": 1,
            "updated_at": now,
        })

        deadline_s = (
            Constants.Deadlines.BATCH_ITEM_INTERNAL_DEADLINE_S
            if _is_batch_item(job)
            else Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S
        )
        start = time.monotonic()

        def _check_timeout(stage: int) -> bool:
            elapsed = time.monotonic() - start
            if elapsed > deadline_s:
                fail_job(job_id, _build_error_data(ErrorCode.JOB_TIMEOUT, f"Job timed out at stage {stage}"))
                logger.warning("worker: job %s timed out at stage %d after %.1fs", job_id, stage, elapsed)
                return True
            return False

        source_kind = job.input_source_kind

        athena_additional_info: list[str] = []

        if source_kind == "gcs_batch_dataset":
            is_gcs_dataset_job = True
            from utils.gcs_datasets import download_dataset_inputs
            gcs_temp_dir = download_dataset_inputs(
                group=job.dataset_group,
                input_id=job.dataset_input_id,
                files=job.dataset_files,
                job_id=job_id,
            )
            text = _extract_text_from_downloaded(
                gcs_temp_dir,
                job.dataset_group,
                job.dataset_input_id,
                job.dataset_files,
            )
        elif source_kind in ("athena_encounter", "athena_clinical_doc"):
            from services.external_api import athena_client, AthenaAPIError
            practice_id = job.athena_practice_id or Constants.ATHENA_PRACTICE_ID
            api_path = job.athena_api_path or ""
            try:
                if source_kind == "athena_encounter":
                    text = athena_client.fetch_encounter_summary(
                        practice_id, job.athena_encounter_id
                    )
                else:
                    text = athena_client.fetch_clinical_doc(
                        practice_id,
                        job.athena_patient_id,
                        job.athena_document_id,
                    )
            except AthenaAPIError as exc:
                fail_job(job_id, build_error_data_from_exc(exc))
                logger.error("worker: Athena API error for job %s: %s", job_id, exc)
                return "", 200
            if api_path:
                athena_additional_info = [api_path]
        else:
            text = _resolve_input_from_job_doc(job)

        if not text.strip():
            fail_job(job_id, _build_error_data(ErrorCode.EMPTY_DOCUMENT))
            return "", 200

        version = job.input_version
        grading_enabled = job.grading_enabled
        is_batch = _is_batch_item(job)

        pipeline_fn = PIPELINES.get(version, PIPELINES["v1-2"])

        metrics = Metrics.start(
            session_id=job_id,
            pipeline_version=version,
            input_type=_canonical_input_type(source_kind),
        )

        current_stage = 1
        pipeline_result = None
        pipeline_error_data: dict | None = None

        for event in pipeline_fn(text, metrics, grading_enabled, source_kind=source_kind, is_batch=is_batch):
            if isinstance(event, AdapterResult):
                pipeline_result = event
            elif isinstance(event, AdapterError):
                pipeline_error_data = event.error_data
                break
            elif isinstance(event, AdapterStepEvent):
                if event.status == "active" and event.step != current_stage:
                    current_stage = event.step
                    if _check_timeout(current_stage):
                        return "", 200
                    update_job_stage(job_id, current_stage)

        if pipeline_error_data is not None:
            # error_data is a rich error dict from the pipeline SSE stream.
            # Both old SP2 format (code+message+details) and new rich format
            # (code+message+user_hint+retryable+detail) carry a "message" field.
            if pipeline_error_data.get("code") or pipeline_error_data.get("message"):
                fail_job(job_id, pipeline_error_data)
            else:
                fail_job(job_id, _build_error_data(
                    ErrorCode.UNKNOWN_ERROR, "Pipeline failed without an error message"
                ))
            return "", 200

        if pipeline_result is None:
            fail_job(job_id, _build_error_data(
                ErrorCode.UNKNOWN_ERROR, "Pipeline returned no result"
            ))
            return "", 200

        care_plan = pipeline_result.care_plan
        grading   = pipeline_result.grading

        if source_kind == "doc_id":
            input_model = DocIdInput(doc_id=job.input_doc_id)
        else:
            input_model = TextInput(text=text)

        envelope = CarePlanInternal(
            metrics=metrics,
            input=input_model,
            grading=grading,
            care_plan=care_plan,
        )
        output_data = envelope.to_dict()

        # Inject Athena source paths into care_plan.additional_info
        if athena_additional_info:
            care_plan_dict = output_data.get("care_plan", {})
            care_plan_dict["additional_info"] = athena_additional_info
            output_data["care_plan"] = care_plan_dict

        name = _derive_name(output_data.get("care_plan", {}), job.input_source_filename)
        output_data["metrics"]["saved_id"] = job_id

        complete_job(job_id, output_data, name)
        logger.info("worker: job %s completed", job_id, extra={"job_id": job_id, "batch_run_id": batch_run_id, "uid": uid, "stage": 5})
        return "", 200

    except Exception as exc:
        logger.exception("worker: unexpected error for job %s", job_id, extra={"job_id": job_id})
        # Best-effort: mark the job as failed so the frontend doesn't show it as stuck.
        try:
            fail_job(job_id, build_error_data_from_exc(exc))
        except Exception:
            pass
        return "", 500
    finally:
        if is_gcs_dataset_job:
            from utils.gcs_datasets import cleanup_dataset_inputs
            cleanup_dataset_inputs(job_id)


# ── Name derivation ────────────────────────────────────────────────────────────
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
