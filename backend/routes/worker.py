"""POST /internal/jobs/execute/<job_id> — worker endpoint for Cloud Tasks."""

# ── Imports & blueprint setup ──────────────────────────────────────────────────
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, request

from utils.firebase import (
    get_job_doc,
    update_job_stage,
    complete_job,
    fail_job,
    verify_oidc_token,
)
from services.care_plan_pipeline import run_care_plan_pipeline
from services.care_plan_input import (
    resolve_input_from_job_doc,
    extract_text_from_downloaded,
)
from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError
from models.care_plan.envelope import CarePlanInternal
from models.job import JobDoc
from models.input import TextInput, DocIdInput
from models.metrics import Metrics
from utils.constants import Constants
from utils.misc import derive_output_name
from utils.markers import Markers, JunoContext
from utils.job_helpers import canonical_input_type, is_batch_item
from errors import ErrorCode, build_error_data, build_error_data_from_exc

logger = logging.getLogger(__name__)
worker_bp = Blueprint("worker", __name__)

PIPELINES = {Constants.Pipeline.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}


# ── Job execution handler ──────────────────────────────────────────────────────
@worker_bp.route("/internal/jobs/execute/<job_id>", methods=["POST"])
def execute_job(job_id: str):
    queue_name_header = request.headers.get("X-CloudTasks-QueueName", "").strip()
    if not queue_name_header:
        logger.warning("worker: rejected request without X-CloudTasks-QueueName")
        return "", 403

    if not verify_oidc_token():
        return "", 403

    def _run(scope):
        JunoContext.from_g(function="execute_job").apply(scope)
        scope.add("job_id", job_id)

        gcs_temp_dir: Path | None = None
        is_gcs_dataset_job = False
        job: JobDoc | None = None

        try:
            job_doc = get_job_doc(job_id)
            if job_doc is None:
                logger.warning("worker: job doc not found for job_id=%s — skipping", job_id)
                return "", 200

            job = JobDoc.from_firestore(job_doc)
            is_trial = getattr(job, "is_trial", False)

            if job.status in ("completed", "error"):
                logger.info("worker: job %s already in terminal state %s — idempotent return", job_id, job.status)
                return "", 200

            # Computed here (before the processing-lease check below needs it)
            # rather than after the "processing" transition further down --
            # purely a reorder, is_batch_item(job) doesn't depend on anything
            # set in between.
            deadline_s = (
                Constants.Deadlines.BATCH_ITEM_INTERNAL_DEADLINE_S
                if is_batch_item(job)
                else Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S
            )

            if job.status == "processing" and job.started_at is not None:
                lease_elapsed_s = (datetime.now(timezone.utc) - job.started_at).total_seconds()
                if lease_elapsed_s < deadline_s:
                    # A prior attempt is still within its own timeout budget --
                    # Cloud Tasks' at-least-once delivery redelivered this task
                    # while that attempt may still legitimately be in flight
                    # (or may have crashed without reaching a terminal state).
                    # Re-running the pipeline here would re-execute the whole
                    # 5-stage LLM pipeline a second time, double-billing every
                    # Vertex AI call it already made (edge-case review Finding
                    # 7). Treat this delivery as a no-op: the original attempt
                    # (or its own _check_timeout below) will reach a terminal
                    # state on its own. Returning 200 tells Cloud Tasks not to
                    # retry again.
                    logger.info(
                        "worker: job %s already processing (leased %.1fs ago, "
                        "budget %ds) — skipping redelivery", job_id, lease_elapsed_s, deadline_s,
                    )
                    return "", 200
                # Lease expired: the original attempt almost certainly crashed
                # or was killed before reaching a terminal state (a healthy
                # attempt would have hit its own _check_timeout well before
                # this). Deliberately does NOT give up on the job -- it's
                # allowed to run again, exactly like a first attempt, so a
                # transient crash doesn't permanently strand it.
                logger.warning(
                    "worker: job %s stuck in processing since %s (%.1fs, exceeds "
                    "%ds budget) — treating as abandoned and allowing retry",
                    job_id, job.started_at.isoformat(), lease_elapsed_s, deadline_s,
                )

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

            start = time.monotonic()

            def _check_timeout(stage: int) -> bool:
                elapsed = time.monotonic() - start
                if elapsed > deadline_s:
                    fail_job(
                        job_id, build_error_data(ErrorCode.JOB_TIMEOUT, f"Job timed out at stage {stage}"),
                        clear_input_text=is_trial,
                    )
                    logger.warning("worker: job %s timed out at stage %d after %.1fs", job_id, stage, elapsed)
                    return True
                return False

            source_kind = job.input_source_kind

            athena_additional_info: list[str] = []

            if source_kind == "gcs_batch_dataset":
                is_gcs_dataset_job = True
                from utils.gcs import download_dataset_inputs
                gcs_temp_dir = download_dataset_inputs(
                    group=job.dataset_group,
                    input_id=job.dataset_input_id,
                    files=job.dataset_files,
                    job_id=job_id,
                )
                text = extract_text_from_downloaded(
                    gcs_temp_dir,
                    job.dataset_group,
                    job.dataset_input_id,
                    job.dataset_files,
                )
            elif source_kind in ("athena_encounter", "athena_clinical_doc"):
                from services.external_api import athena_client
                from errors import AthenaAPIError
                practice_id = job.athena_practice_id or Constants.Athena.PRACTICE_ID
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
                    fail_job(job_id, build_error_data_from_exc(exc), clear_input_text=is_trial)
                    logger.error("worker: Athena API error for job %s: %s", job_id, exc)
                    return "", 200
                if api_path:
                    athena_additional_info = [api_path]
            else:
                text = resolve_input_from_job_doc(job)

            # Defensive floor (belt-and-suspenders alongside the per-file check
            # in services.care_plan_input.resolve_uploaded_files): reject not
            # just an empty string but anything below a sane minimum of real
            # content, so a document that is technically non-empty but is
            # really just separator scaffolding around a scanned/no-text-layer
            # file (or any other source_kind that doesn't go through
            # resolve_uploaded_files, e.g. gcs_batch_dataset/Athena) can never
            # silently reach the LLM pipeline (edge-case review Finding 2).
            if len(text.strip()) < Constants.Uploads.MIN_MEANINGFUL_CONTENT_CHARS:
                fail_job(job_id, build_error_data(ErrorCode.EMPTY_DOCUMENT), clear_input_text=is_trial)
                return "", 200

            version = job.input_version
            grading_enabled = job.grading_enabled
            is_batch = is_batch_item(job)

            pipeline_fn = PIPELINES.get(version, PIPELINES["v1-2"])

            metrics = Metrics.start(
                session_id=job_id,
                pipeline_version=version,
                input_type=canonical_input_type(source_kind),
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
                # error_data is a rich error dict emitted by the pipeline.
                # Both old SP2 format (code+message+details) and new rich format
                # (code+message+user_hint+retryable+detail) carry a "message" field.
                if pipeline_error_data.get("code") or pipeline_error_data.get("message"):
                    fail_job(job_id, pipeline_error_data, clear_input_text=is_trial)
                else:
                    fail_job(job_id, build_error_data(
                        ErrorCode.UNKNOWN_ERROR, "Pipeline failed without an error message"
                    ), clear_input_text=is_trial)
                return "", 200

            if pipeline_result is None:
                fail_job(job_id, build_error_data(
                    ErrorCode.UNKNOWN_ERROR, "Pipeline returned no result"
                ), clear_input_text=is_trial)
                return "", 200

            care_plan = pipeline_result.care_plan
            grading   = pipeline_result.grading

            if source_kind == "doc_id":
                input_model = DocIdInput(doc_id=job.input_doc_id)
            else:
                input_model = TextInput(text=text)

            # Read back the timeout-check timer (started at `start = time.monotonic()`
            # above) into the field that already exists on Metrics but was never
            # populated anywhere — see PRD §4.2. Purely additive; no gating on is_trial,
            # benefits every caller (trial and main app both).
            metrics.total_duration_ms = (time.monotonic() - start) * 1000.0

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

            name = derive_output_name(output_data.get("care_plan", {}), job.input_source_filename)
            output_data["metrics"]["saved_id"] = job_id

            # Trial jobs are short-lived and their UI never reads raw text/simplified_text/
            # clarified_text, nor the original input text — drop the whole (optional) `raw`
            # key and the (optional) `input.text` key so completed trial docs stay well
            # under Firestore's 1 MiB doc limit and don't risk the ~1500-byte auto-indexed
            # field limit on these full-document-length strings. `input.text` is popped
            # rather than replacing the whole `input` dict so it round-trips cleanly back
            # into TextInput (text: str | None = None) with no model or frontend change.
            if is_trial:
                output_data.get("care_plan", {}).pop("raw", None)
                output_data.get("input", {}).pop("text", None)

                # Trial UI (ResultScreen.tsx) reads only the two `combined` grading
                # entries (before/after); the other 12 non-`combined` method entries
                # are computed (grading is shared with the main app's per-method
                # breakdown UI) but never rendered anywhere in frontend-trial/.
                # Dropping them here, storage-side only, cuts ~38% off output_data
                # (optimization-findings-2026-09-05.md, Finding 1 / PRD §4.1).
                grading_dict = output_data.get("grading")
                if isinstance(grading_dict, dict):
                    entries = grading_dict.get("entries")
                    if isinstance(entries, list):
                        grading_dict["entries"] = [
                            e for e in entries
                            if isinstance(e, dict) and e.get("name") == "combined"
                        ]

            complete_job(job_id, output_data, name, clear_input_text=is_trial)
            logger.info("worker: job %s completed", job_id, extra={"job_id": job_id, "batch_run_id": batch_run_id, "uid": uid, "stage": 5})
            return "", 200

        except Exception as exc:
            scope.mark_failed()
            logger.exception("worker: unexpected error for job %s", job_id, extra={"job_id": job_id})
            # Best-effort: mark the job as failed so the frontend doesn't show it as stuck.
            try:
                fail_job(job_id, build_error_data_from_exc(exc), clear_input_text=getattr(job, "is_trial", False))
            except Exception:
                pass
            return "", 500
        finally:
            if is_gcs_dataset_job:
                from utils.gcs import cleanup_dataset_inputs
                cleanup_dataset_inputs(job_id)
            if job is not None and getattr(job, "is_trial", False) and job.input_pdf_gcs_uri:
                from utils.gcs import delete_gcs_object
                delete_gcs_object(job.input_pdf_gcs_uri)

    return Markers.Worker.JobExecute.execute(_run)
