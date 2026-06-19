"""
simplify_v1_1.py - V1.1 simplification handler.

Invoked by POST /simplify with version=v1-1.
  Accepts one of:
    A) multipart/form-data with 'file' field (PDF, TXT, DOCX)
    B) multipart/form-data or application/json with 'text' field
    C) multipart/form-data or application/json with 'doc_id' field - fetches from GCS

  Returns: text/event-stream (SSE) with per-step progress + final result.

SSE steps for V1.1:
  1. Reading your note
  2. Finding difficult and medical terms
  3. Simplifying language
  4. Clarifying actions and numbers
  5. Organizing your care plan
"""

import io
import json
import logging
import os
from typing import Generator

from flask import Blueprint, Response, g, request, stream_with_context
from google.cloud import storage as gcs

from simplify.v1_1.pipeline import V1_1Pipeline
from utils.pdf_extract import extract_text_from_pdf
from utils.scoring import score_text
from utils.term_detection import build_glossary_from_simplified_text, detect_terms
from utils.juno_logger import JunoLogger, monotonic_ms
from utils.juno_metrics import JunoMetrics
from models.metrics import Metrics
from models.input import Input
from models.grading import Grading, build_grading
from models.care_plan import SimplifiedCarePlan
from models.envelope import SimplifyOutput

logger = logging.getLogger(__name__)

simplify_v1_1_bp = Blueprint("simplify_v1_1", __name__)

STEPS = {
    1: "Reading your note",
    2: "Finding difficult and medical terms",
    3: "Simplifying language",
    4: "Clarifying actions and numbers",
    5: "Organizing your care plan",
}

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
_GCS_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "")
_UPLOAD_PREFIX = "simplify-uploads"


def _sse(payload: dict) -> str:
    """Format a Python dict as an SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, TXT, or DOCX bytes."""
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

    raise ValueError(f"Unsupported file extension: {ext}")


def _fetch_from_gcs(doc_id: str) -> tuple[bytes, str]:
    """Fetch uploaded file bytes from GCS by doc_id. Returns (bytes, filename)."""
    if not _GCS_BUCKET_NAME:
        raise RuntimeError("GCP_BUCKET_NAME is not configured")

    project_id = os.environ.get("GCP_PROJECT_ID", "")
    client = gcs.Client(project=project_id or None)
    bucket = client.bucket(_GCS_BUCKET_NAME)
    prefix = f"{_UPLOAD_PREFIX}/{doc_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix))

    if not blobs:
        raise FileNotFoundError(f"No file found for doc_id={doc_id}")

    blob = blobs[0]
    filename = blob.name.split("/")[-1]
    return blob.download_as_bytes(), filename


def _resolve_input() -> tuple[str, str]:
    """
    Resolve input from the request. Returns (text, source_description).

    Priority: text field > file field > doc_id.
    """
    json_data = request.get_json(silent=True) or {}

    text_input = (request.form.get("text") or json_data.get("text") or "").strip()
    if text_input:
        return text_input, "text_input"

    if "file" in request.files:
        upload = request.files["file"]
        if not upload.filename:
            raise ValueError("Uploaded file is missing a filename")
        if not _allowed(upload.filename):
            raise ValueError("File must be PDF, TXT, or DOCX")

        file_bytes = upload.read()
        if len(file_bytes) > MAX_FILE_BYTES:
            raise ValueError("File exceeds 10 MB limit")

        return _extract_text_from_bytes(file_bytes, upload.filename), upload.filename

    doc_id = (request.form.get("doc_id") or json_data.get("doc_id") or "").strip()
    if doc_id:
        file_bytes, filename = _fetch_from_gcs(doc_id)
        if not _allowed(filename):
            raise ValueError("Stored file must be PDF, TXT, or DOCX")
        if len(file_bytes) > MAX_FILE_BYTES:
            raise ValueError("Stored file exceeds 10 MB limit")
        return _extract_text_from_bytes(file_bytes, filename), f"doc:{doc_id}"

    raise ValueError("Request must include 'file', 'text', or 'doc_id'")


def _score_or_none(text: str, label: str) -> dict | None:
    try:
        return score_text(text)
    except Exception:
        logger.exception("simplify_v1_1: %s-score failed - continuing without score", label)
        return None


def run_v1_1_pipeline(text: str, metrics: Metrics, grading_enabled: bool) -> Generator[str, None, None]:
    juno_logger = JunoLogger(api_version="v1-1")
    juno_metrics = JunoMetrics()
    pipeline_start = monotonic_ms()

    # Per-step duration accumulators (populated as each step completes)
    find_medical_terms_ms: float | None = None
    simplify_language_ms: float = 0.0
    clarify_actions_ms: float | None = None
    structure_note_ms: float = 0.0

    try:
        pipeline = V1_1Pipeline()

        # Step 2: Term detection (deterministic; no LLM)
        yield _sse({"step": 2, "status": "active", "label": STEPS[2]})
        juno_logger.log_step("find_medical_terms", "start")
        t0 = monotonic_ms()
        try:
            term_data = detect_terms(text)
        except Exception as exc:
            juno_logger.exception("simplify_v1_1: term detection failed - continuing with empty terms")
            juno_logger.log_step("find_medical_terms", "error", extra={"error": str(exc)})
            juno_metrics.record_error(type(exc).__name__, "find_medical_terms", labels={"version": "v1-1"})
            term_data = {
                "substitution_candidates": [],
                "preserve_and_define_terms": [],
                "abbreviations": [],
            }
        else:
            find_medical_terms_ms = monotonic_ms() - t0
            juno_logger.log_step("find_medical_terms", "done", duration_ms=find_medical_terms_ms)
        yield _sse({"step": 2, "status": "done", "label": STEPS[2]})

        # Step 3: Simplify language
        yield _sse({"step": 3, "status": "active", "label": STEPS[3]})
        juno_logger.log_step("simplify_language", "start")
        t0 = monotonic_ms()
        try:
            simplified = pipeline.simplify_language_with_term_plan(
                text,
                term_data["substitution_candidates"],
                term_data["preserve_and_define_terms"],
                term_data["abbreviations"],
            )
        except Exception as exc:
            juno_logger.exception("simplify_v1_1: simplification failed")
            juno_logger.log_step("simplify_language", "error", extra={"error": str(exc)})
            juno_metrics.record_error(type(exc).__name__, "simplify_language", labels={"version": "v1-1"})
            yield _sse({"step": "error", "error": f"Simplification failed: {exc}"})
            return
        simplify_language_ms = monotonic_ms() - t0
        juno_logger.log_step("simplify_language", "done", duration_ms=simplify_language_ms)
        yield _sse({"step": 3, "status": "done", "label": STEPS[3]})

        # Step 4: Clarify actions and numbers
        yield _sse({"step": 4, "status": "active", "label": STEPS[4]})
        juno_logger.log_step("clarify_actions", "start")
        t0 = monotonic_ms()
        try:
            clarified = pipeline.clarify_and_action(simplified, term_data["abbreviations"])
        except Exception as exc:
            juno_logger.exception("simplify_v1_1: clarify step failed - using simplified text")
            juno_logger.log_step("clarify_actions", "error", extra={"error": str(exc)})
            juno_metrics.record_error(type(exc).__name__, "clarify_actions", labels={"version": "v1-1"})
            clarified = simplified
        else:
            clarify_actions_ms = monotonic_ms() - t0
            juno_logger.log_step("clarify_actions", "done", duration_ms=clarify_actions_ms)
        yield _sse({"step": 4, "status": "done", "label": STEPS[4]})

        # Step 5: Structure appointment note
        yield _sse({"step": 5, "status": "active", "label": STEPS[5]})
        juno_logger.log_step("structure_note", "start")
        t0 = monotonic_ms()
        try:
            structured = pipeline.structure_appointment_note(clarified)
        except Exception as exc:
            juno_logger.exception("simplify_v1_1: structuring failed")
            juno_logger.log_step("structure_note", "error", extra={"error": str(exc)})
            juno_metrics.record_error(type(exc).__name__, "structure_note", labels={"version": "v1-1"})
            yield _sse({"step": "error", "error": f"Structuring failed: {exc}"})
            return
        structure_note_ms = monotonic_ms() - t0
        juno_logger.log_step("structure_note", "done", duration_ms=structure_note_ms)
        yield _sse({"step": 5, "status": "done", "label": STEPS[5]})

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

        result_payload = {
            **structured,
            "terms": terms_glossary,
            "raw": {
                "text": text,
                "simplified_text": simplified,
                "clarified_text": clarified,
            },
        }
        result_payload.pop("questions", None)

        total_ms = monotonic_ms() - pipeline_start
        juno_metrics.record_latency("simplify_pipeline", total_ms,
                                    labels={"version": "v1-1", "input_type": metrics.input_type})
        juno_metrics.record_counter("simplify_request", labels={"version": "v1-1"})

        metrics.total_duration_ms = total_ms
        if find_medical_terms_ms is not None:
            metrics.step_durations_ms["find_medical_terms"] = find_medical_terms_ms
        metrics.step_durations_ms["simplify_language"] = simplify_language_ms
        if clarify_actions_ms is not None:
            metrics.step_durations_ms["clarify_actions"] = clarify_actions_ms
        metrics.step_durations_ms["structure_note"] = structure_note_ms
        if grading_enabled:
            grading = build_grading(before_score, text, after_score, clarified)
        else:
            grading = Grading(enabled=False)
        care_plan = SimplifiedCarePlan.from_pipeline_result("1.1", result_payload)
        output = SimplifyOutput(
            metrics=metrics,
            input=Input.from_text(text),
            grading=grading,
            simplified_care_plan=care_plan,
        )
        yield _sse({"step": "result", "data": output.to_dict()})

    except Exception as exc:
        total_ms = monotonic_ms() - pipeline_start
        juno_logger.exception("simplify_v1_1: unexpected pipeline error")
        juno_metrics.record_error(type(exc).__name__, "simplify_pipeline", labels={"version": "v1-1"})
        juno_metrics.record_latency("simplify_pipeline", total_ms, labels={"version": "v1-1", "status": "error"})
        yield _sse({"step": "error", "error": f"Pipeline error: {exc}"})


def _payload_from_sse(chunk: str) -> dict | None:
    if not chunk.startswith("data: "):
        return None
    return json.loads(chunk.removeprefix("data: ").strip())


def _generate_stream():
    juno_logger = JunoLogger(api_version="v1-1")
    juno_metrics = JunoMetrics()

    try:
        yield _sse({"step": 1, "status": "active", "label": STEPS[1]})

        # Step 1: Resolve input
        juno_logger.log_step("read_input", "start")
        t0 = monotonic_ms()
        try:
            text, source = _resolve_input()
        except Exception as exc:
            juno_logger.exception("simplify_v1_1: input resolution failed")
            juno_logger.log_step("read_input", "error", extra={"error": str(exc)})
            juno_metrics.record_error(type(exc).__name__, "read_input", labels={"version": "v1-1"})
            yield _sse({"step": "error", "error": f"Could not read input: {exc}"})
            return

        if not text.strip():
            yield _sse({"step": "error", "error": "Input appears to be empty or unreadable."})
            return

        # Infer source_kind from source string for labelling
        source_kind = "doc_id" if source.startswith("doc:") else (
            "text" if source == "text_input" else "file"
        )

        # Build structured models now that source_kind is known
        metrics = Metrics.start(
            session_id=getattr(g, "session_id", ""),
            pipeline_version="v1-1",
            input_type=source_kind,
        )
        if source_kind == "text":
            input_model = Input.from_text(text)
        elif source_kind == "doc_id":
            raw_doc_id = source.removeprefix("doc:")
            input_model = Input.from_doc_id(raw_doc_id)
        else:
            upload = request.files.get("file")
            if upload:
                try:
                    upload.seek(0)
                except Exception:
                    pass
                input_model = Input.from_file_uploads([upload])
            else:
                input_model = Input(mode="file")

        read_input_ms = monotonic_ms() - t0
        juno_logger.log_step(
            "read_input", "done",
            duration_ms=read_input_ms,
            extra={"source_kind": source_kind, "input_chars": len(text)},
        )
        metrics.step_durations_ms["read_input"] = read_input_ms
        yield _sse({"step": 1, "status": "done", "label": STEPS[1]})
        logger.info("simplify_v1_1: processing source=%s (%d chars)", source, len(text))

        json_data = request.get_json(silent=True) or {}
        raw = request.form.get("grading_enabled")
        if raw is None:
            raw = json_data.get("grading_enabled", True)
        grading_enabled = raw if isinstance(raw, bool) else str(raw).strip().lower() in {"1", "true", "yes", "on"}

        for chunk in run_v1_1_pipeline(text, metrics, grading_enabled=grading_enabled):
            payload = _payload_from_sse(chunk)
            if not payload or payload.get("step") != "result":
                yield chunk
                continue

            result_data = payload["data"]
            result_data["input"] = input_model.to_dict()
            yield _sse({"step": "result", "data": result_data})

    except Exception as exc:
        juno_logger.exception("simplify_v1_1: unexpected pipeline error")
        juno_metrics.record_error(type(exc).__name__, "simplify_pipeline", labels={"version": "v1-1"})
        yield _sse({"step": "error", "error": f"Pipeline error: {exc}"})


def simplify_v1_1():
    """Stream V1.1 simplification pipeline via SSE."""
    return Response(
        stream_with_context(_generate_stream()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
