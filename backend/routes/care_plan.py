"""
care_plan.py - V1.2 care plan pipeline utilities.

Shared utilities for the async job workflow (care_plan_jobs.py, worker.py, batch.py).
The SSE streaming route (POST /care_plan) has been removed; use POST /care_plan/jobs instead.
"""

import io
import json
import logging
import os
import uuid
from typing import Generator

from flask import Blueprint, g, request
from google.cloud import storage as gcs

from utils.constants import Constants

from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
from utils.pdf import merge_pdfs, extract_text_from_pdf
from utils.scoring import score_text
from utils.term_detection import build_glossary_from_simplified_text, detect_terms
from models.metrics import Metrics
from models.grading import Grading, build_grading, GRADING_VERSION
from models.care_plan import CarePlan, CARE_PLAN_VERSION
from models.care_plan.envelope import CarePlanInternal
from models.input import INPUT_VERSION, ResolvedInput
from utils.markers import Markers, JunoContext

from errors import make_error_response, ErrorCode, build_error_data_from_exc, JunoError
from observability.telemetry import get_tracer

logger = logging.getLogger(__name__)
# Secondary error logger routed to utils.juno_logger for compatibility with existing
# log-assertion tests that predate the Markers migration.
_juno_error_logger = logging.getLogger("utils.juno_logger")

care_plan_bp = Blueprint("care_plan", __name__)


@care_plan_bp.route("/care_plan", methods=["POST"])
def care_plan_sse_deprecated():
    """Deprecated SSE endpoint — use POST /care_plan/jobs instead."""
    from flask import jsonify
    return jsonify({
        "error": "This SSE endpoint has been removed. Use POST /care_plan/jobs instead."
    }), 410


def upload_combined_pdf(pdf_bytes: bytes, user_id: str) -> str:
    """Upload combined input PDF bytes and return a gs:// URI."""
    bucket_name = os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")
    if not bucket_name:
        raise RuntimeError("GCP_BUCKET_NAME is not configured")

    project_id = os.environ.get("GCP_PROJECT_ID", "") or None
    object_id = str(uuid.uuid4())
    blob_name = f"care_plan/{user_id}/inputs/{object_id}.pdf"

    client = gcs.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")
    return f"gs://{bucket_name}/{blob_name}"


def _sse(payload: dict) -> str:
    """Format a Python dict as an SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _sse_error(code: ErrorCode, path: str, details_vars: dict | None = None) -> str:
    resp = make_error_response(code, path=path, details_vars=details_vars)
    return _sse({"step": "error", "error_data": resp.error.to_dict()})


def _sse_error_rich(exc: Exception) -> str:
    """Emit a structured SSE error event using the rich error catalog.

    Classifies *exc* via ``build_error_data_from_exc`` (which checks for
    JunoError, Google API errors, and legacy RuntimeErrors), then emits an
    SSE payload whose ``error_data`` contains the new rich fields:
    ``code``, ``message``, ``user_hint``, ``retryable``, ``detail``.
    The worker captures this and writes it directly to Firestore via fail_job.
    """
    return _sse({"step": "error", "error_data": build_error_data_from_exc(exc)})


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Constants.ALLOWED_EXTENSIONS


def _extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, TXT, DOCX, or HTML bytes."""
    ext = filename.rsplit(".", 1)[1].lower()

    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")

    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)

    if ext == "docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError(
                "python-docx is not installed. Add 'python-docx' to requirements.txt."
            ) from exc

        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if ext in {"html", "htm"}:
        from utils.html import extract_text_from_html
        return extract_text_from_html(file_bytes)

    raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")


def _source_separator(filename: str) -> str:
    return f"\n\n--- Source: {filename} ---\n"


def _text_artifact_filename(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem}.txt"


def _resolve_uploaded_files(uploads) -> tuple[ResolvedInput, bytes | None]:
    files = [upload for upload in uploads if upload and upload.filename]
    if not files:
        raise ValueError("Uploaded file is missing a filename")
    if len(files) > Constants.MAX_FILE_COUNT:
        raise ValueError(f"Upload supports at most {Constants.MAX_FILE_COUNT} files")

    text_parts: list[str] = []
    merge_candidates: list[tuple[bytes, str]] = []
    filenames: list[str] = []
    aggregate_bytes = 0

    for upload in files:
        filename = upload.filename
        if not _allowed(filename):
            raise ValueError("File must be PDF, TXT, DOCX, or HTML")

        file_bytes = upload.read()
        if len(file_bytes) > Constants.MAX_FILE_BYTES:
            raise ValueError("File exceeds 10 MB limit")
        aggregate_bytes += len(file_bytes)
        if aggregate_bytes > Constants.Uploads.MAX_AGGREGATE_FILE_BYTES:
            limit_mb = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES // (1024 * 1024)
            raise ValueError(f"combined upload size exceeds {limit_mb} MB limit")

        filenames.append(filename)
        extracted_text = _extract_text_from_bytes(file_bytes, filename)
        text_parts.append(f"{_source_separator(filename)}{extracted_text.strip()}")

        ext = filename.rsplit(".", 1)[1].lower()
        if ext in {"pdf", "txt"}:
            merge_candidates.append((file_bytes, filename))
        elif ext in {"docx", "html", "htm"} and extracted_text.strip():
            merge_candidates.append(
                (extracted_text.encode("utf-8"), _text_artifact_filename(filename))
            )

    combined_pdf_bytes = None
    if merge_candidates:
        try:
            combined_pdf_bytes = merge_pdfs(merge_candidates)
        except Exception:
            logger.exception("care_plan: failed to merge input files - continuing without combined PDF")

    file_count = len(files)
    file_types = sorted({f.filename.rsplit(".", 1)[1].lower() for f in files if "." in f.filename})

    source_filename = ", ".join(filenames)
    combined_pdf_size = float(len(combined_pdf_bytes)) if combined_pdf_bytes is not None else None
    return ResolvedInput(
        text="\n".join(text_parts).strip(),
        source_description=source_filename,
        source_filename=source_filename,
        combined_pdf_size=combined_pdf_size,
        file_count=file_count,
        file_types=file_types,
    ), combined_pdf_bytes


def _fetch_from_gcs(doc_id: str) -> tuple[bytes, str]:
    """Fetch uploaded file bytes from GCS by doc_id. Returns (bytes, filename)."""
    _gcs_bucket_name = os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")
    if not _gcs_bucket_name:
        raise RuntimeError("GCP_BUCKET_NAME is not configured")

    project_id = os.environ.get("GCP_PROJECT_ID", "")
    client = gcs.Client(project=project_id or None)
    bucket = client.bucket(_gcs_bucket_name)
    prefix = f"{Constants.Uploads.UPLOAD_PREFIX}/{doc_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix))

    if not blobs:
        raise JunoError(ErrorCode.RESOURCE_NOT_FOUND, detail=f"doc_id={doc_id}")

    if len(blobs) > 1:
        blobs.sort(key=lambda b: b.updated, reverse=True)
    blob = blobs[0]
    filename = blob.name.split("/")[-1]
    return blob.download_as_bytes(), filename


def _score_or_none(text: str, label: str) -> dict | None:
    try:
        return score_text(text)
    except Exception:
        logger.exception("care_plan: %s-score failed - continuing without score", label)
        return None


def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
    source_kind: str = "upload",
    is_batch: bool = False,
) -> Generator[str | tuple, None, None]:
    try:
        try:
            pipeline = CarePlanV1_2Pipeline()
        except Exception as e:
            yield _sse_error(ErrorCode.PIPELINE_INIT_ERROR, "/care_plan", {"detail": str(e)})
            return

        # Step 2: Term detection (deterministic; no LLM)
        yield _sse({"step": 2, "status": "active", "label": Constants.STEPS[2]})
        try:
            def _find(scope):
                JunoContext.from_g(function="find_medical_terms").apply(scope)
                try:
                    result = detect_terms(text)
                except Exception as exc:
                    logger.exception("care_plan: term detection failed - continuing with empty terms")
                    scope.mark_failed()
                    result = {
                        "substitution_candidates": [],
                        "preserve_and_define_terms": [],
                        "abbreviations": [],
                    }
                substitution_count = len(result.get("substitution_candidates", []))
                preserve_count = len(result.get("preserve_and_define_terms", []))
                scope.add("term_count", substitution_count + preserve_count)
                scope.add("substitution_count", substitution_count)
                return result
            term_data = Markers.CarePlan.FindMedicalTerms.execute(_find)
        except Exception as exc:
            logger.exception("care_plan: term detection outer error")
            term_data = {"substitution_candidates": [], "preserve_and_define_terms": [], "abbreviations": []}
        yield _sse({"step": 2, "status": "done", "label": Constants.STEPS[2]})

        # Step 3: Simplify language
        yield _sse({"step": 3, "status": "active", "label": Constants.STEPS[3]})
        try:
            def _simplify(scope):
                JunoContext.from_g(function="simplify_language").apply(scope)
                scope.add("input_chars", len(text))
                with get_tracer().start_as_current_span("care_plan.simplify_language") as span:
                    try:
                        span.set_attribute("session.id", g.session_id)
                    except (AttributeError, RuntimeError):
                        span.set_attribute("session.id", "")
                    return pipeline.simplify_language_with_term_plan(
                        text,
                        term_data["substitution_candidates"],
                        term_data["preserve_and_define_terms"],
                        term_data["abbreviations"],
                    )
            simplified = Markers.CarePlan.SimplifyLanguage.execute(_simplify)
        except Exception as exc:
            logger.exception("care_plan: simplification failed")
            yield _sse_error_rich(exc)
            return
        yield _sse({"step": 3, "status": "done", "label": Constants.STEPS[3]})

        # Step 4: Clarify actions and numbers
        yield _sse({"step": 4, "status": "active", "label": Constants.STEPS[4]})
        try:
            def _clarify(scope):
                JunoContext.from_g(function="clarify_actions").apply(scope)
                with get_tracer().start_as_current_span("care_plan.clarify_actions") as span:
                    try:
                        span.set_attribute("session.id", g.session_id)
                    except (AttributeError, RuntimeError):
                        span.set_attribute("session.id", "")
                    try:
                        return pipeline.clarify_and_action(simplified, term_data["abbreviations"])
                    except Exception as exc:
                        logger.exception("care_plan: clarify step failed - using simplified text")
                        scope.mark_failed()
                        return simplified
            clarified = Markers.CarePlan.ClarifyActions.execute(_clarify)
        except Exception as exc:
            logger.exception("care_plan: clarify outer error")
            clarified = simplified
        yield _sse({"step": 4, "status": "done", "label": Constants.STEPS[4]})

        # Step 5: Structure appointment note
        yield _sse({"step": 5, "status": "active", "label": Constants.STEPS[5]})
        try:
            def _structure(scope):
                JunoContext.from_g(function="structure_note").apply(scope)
                with get_tracer().start_as_current_span("care_plan.structure_note") as span:
                    try:
                        span.set_attribute("session.id", g.session_id)
                    except (AttributeError, RuntimeError):
                        span.set_attribute("session.id", "")
                    return pipeline.structure_appointment_note(clarified)
            structured = Markers.CarePlan.StructureNote.execute(_structure)
        except Exception as exc:
            logger.exception("care_plan: structuring failed")
            yield _sse_error_rich(exc)
            return
        yield _sse({"step": 5, "status": "done", "label": Constants.STEPS[5]})

        terms_glossary = build_glossary_from_simplified_text(
            clarified,
            term_data["preserve_and_define_terms"],
        )
        if grading_enabled:
            before_score = _score_or_none(text, "before")
            after_score = _score_or_none(clarified, "after")
        else:
            before_score = None
            after_score = None

        care_plan = CarePlan.from_pipeline_result("1.2", {
            **structured,
            "terms": terms_glossary,
            "raw": {
                "text": text,
                "simplified_text": simplified,
                "clarified_text": clarified,
            },
        })

        if grading_enabled:
            def _grade(scope):
                JunoContext.from_g(function="grading").apply(scope)
                result = build_grading(before_score, text, after_score, clarified)
                scope.add("before_composite", (before_score or {}).get("composite", 0.0))
                scope.add("after_composite", (after_score or {}).get("composite", 0.0))
                method_names = {e.name for e in result.entries if e.name != "combined"}
                scope.add("grading_method_count", len(method_names))
                return result
            grading = Markers.Grading.Run.execute(_grade)
        else:
            grading = Grading(enabled=False)

        # Record the pipeline-total marker
        def _pipeline_done(scope):
            JunoContext.from_g(function="pipeline").apply(scope)
            scope.add("input_chars", len(text))
            scope.add("source_kind", source_kind)
            scope.add("grading_enabled", grading_enabled)
            scope.add("is_batch", is_batch)
        Markers.CarePlan.Pipeline.execute(_pipeline_done)

        # Non-SSE sentinel: the route intercepts these typed objects and is
        # the only layer that composes/serializes the response envelope.
        yield (Constants.RESULT_SENTINEL, care_plan, grading, text, clarified)

    except Exception as exc:
        def _pipeline_fail(scope):
            JunoContext.from_g(function="pipeline").apply(scope)
            scope.mark_failed()
        Markers.CarePlan.Pipeline.execute(_pipeline_fail)
        logger.exception("care_plan: unexpected pipeline error")
        yield _sse_error_rich(exc)
