"""
simplify_v1_1.py - V1.1 simplification route.

POST /simplify/v1-1
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

from flask import Blueprint, Response, request, stream_with_context
from google.cloud import storage as gcs

from simplify.v1_1.pipeline import V1_1Pipeline
from utils.pdf_extract import extract_text_from_pdf
from utils.scoring import score_text
from utils.term_detection import build_glossary_from_simplified_text, detect_terms

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


def _generate_stream():
    try:
        yield _sse({"step": 1, "status": "active", "label": STEPS[1]})
        try:
            text, source = _resolve_input()
        except Exception as exc:
            logger.exception("simplify_v1_1: input resolution failed")
            yield _sse({"step": "error", "error": f"Could not read input: {exc}"})
            return

        if not text.strip():
            yield _sse({"step": "error", "error": "Input appears to be empty or unreadable."})
            return

        yield _sse({"step": 1, "status": "done", "label": STEPS[1]})
        logger.info("simplify_v1_1: processing source=%s (%d chars)", source, len(text))

        pipeline = V1_1Pipeline()

        # Step 2: Term detection (deterministic; no LLM)
        yield _sse({"step": 2, "status": "active", "label": STEPS[2]})
        try:
            term_data = detect_terms(text)
        except Exception:
            logger.exception("simplify_v1_1: term detection failed - continuing with empty terms")
            term_data = {
                "substitution_candidates": [],
                "preserve_and_define_terms": [],
                "abbreviations": [],
            }
        yield _sse({"step": 2, "status": "done", "label": STEPS[2]})

        # Step 3: Simplify language
        yield _sse({"step": 3, "status": "active", "label": STEPS[3]})
        try:
            simplified = pipeline.simplify_language_with_term_plan(
                text,
                term_data["substitution_candidates"],
                term_data["preserve_and_define_terms"],
                term_data["abbreviations"],
            )
        except Exception as exc:
            logger.exception("simplify_v1_1: simplification failed")
            yield _sse({"step": "error", "error": f"Simplification failed: {exc}"})
            return
        yield _sse({"step": 3, "status": "done", "label": STEPS[3]})

        # Step 4: Clarify actions and numbers
        yield _sse({"step": 4, "status": "active", "label": STEPS[4]})
        try:
            clarified = pipeline.clarify_and_action(simplified, term_data["abbreviations"])
        except Exception:
            logger.exception("simplify_v1_1: clarify step failed - using simplified text")
            clarified = simplified
        yield _sse({"step": 4, "status": "done", "label": STEPS[4]})

        # Step 5: Structure appointment note
        yield _sse({"step": 5, "status": "active", "label": STEPS[5]})
        try:
            structured = pipeline.structure_appointment_note(clarified)
        except Exception as exc:
            logger.exception("simplify_v1_1: structuring failed")
            yield _sse({"step": "error", "error": f"Structuring failed: {exc}"})
            return
        yield _sse({"step": 5, "status": "done", "label": STEPS[5]})

        terms_glossary = build_glossary_from_simplified_text(
            clarified,
            term_data["preserve_and_define_terms"],
        )
        before_score = _score_or_none(text, "before")
        after_score = _score_or_none(clarified, "after")

        result = {
            **structured,
            "terms": terms_glossary,
            "raw": {
                "text": text,
                "simplified_text": simplified,
                "clarified_text": clarified,
            },
        }
        if before_score is not None:
            result["before_score"] = before_score
        if after_score is not None:
            result["after_score"] = after_score
        result.pop("questions", None)

        yield _sse({"step": "result", "data": result})

    except Exception as exc:
        logger.exception("simplify_v1_1: unexpected pipeline error")
        yield _sse({"step": "error", "error": f"Pipeline error: {exc}"})


@simplify_v1_1_bp.route("/simplify/v1-1", methods=["POST"])
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
