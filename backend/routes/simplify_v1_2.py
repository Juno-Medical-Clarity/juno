"""
simplify_v1_2.py - V1.2 simplification route.

POST /simplify/v1-2
  Accepts one of:
    A) multipart/form-data with 'file' field (PDF, TXT, DOCX)
    B) multipart/form-data or application/json with 'text' field
    C) multipart/form-data or application/json with 'doc_id' field - fetches from GCS

  Returns: text/event-stream (SSE) with per-step progress + final result.

SSE steps for V1.2:
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
from dataclasses import dataclass

from flask import Blueprint, Response, request, stream_with_context
from google.cloud import storage as gcs

from simplify.v1_2.pipeline import V1_2Pipeline
from utils.pdf_merge import merge_pdfs
from utils.pdf_extract import extract_text_from_pdf
from utils.save_output import save_simplify_output, upload_combined_pdf
from utils.scoring import score_text
from utils.term_detection import build_glossary_from_simplified_text, detect_terms
from utils.auth import verify_firebase_token

logger = logging.getLogger(__name__)

simplify_v1_2_bp = Blueprint("simplify_v1_2", __name__)

STEPS = {
    1: "Reading your note",
    2: "Finding difficult and medical terms",
    3: "Simplifying language",
    4: "Clarifying actions and numbers",
    5: "Organizing your care plan",
}

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_FILE_COUNT = 10
MAX_AGGREGATE_FILE_BYTES = 25 * 1024 * 1024  # 25 MB
_GCS_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "")
_UPLOAD_PREFIX = "simplify-uploads"


@dataclass
class ResolvedInput:
    text: str
    source_description: str
    source_filename: str
    combined_pdf_bytes: bytes | None = None
    source_kind: str = "upload"


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


def _source_separator(filename: str) -> str:
    return f"\n\n--- Source: {filename} ---\n"


def _text_artifact_filename(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem}.txt"


def _resolve_uploaded_files(uploads) -> ResolvedInput:
    files = [upload for upload in uploads if upload and upload.filename]
    if not files:
        raise ValueError("Uploaded file is missing a filename")
    if len(files) > MAX_FILE_COUNT:
        raise ValueError(f"Upload supports at most {MAX_FILE_COUNT} files")

    text_parts: list[str] = []
    merge_candidates: list[tuple[bytes, str]] = []
    filenames: list[str] = []
    aggregate_bytes = 0

    for upload in files:
        filename = upload.filename
        if not _allowed(filename):
            raise ValueError("File must be PDF, TXT, or DOCX")

        file_bytes = upload.read()
        if len(file_bytes) > MAX_FILE_BYTES:
            raise ValueError("File exceeds 10 MB limit")
        aggregate_bytes += len(file_bytes)
        if aggregate_bytes > MAX_AGGREGATE_FILE_BYTES:
            limit_mb = MAX_AGGREGATE_FILE_BYTES // (1024 * 1024)
            raise ValueError(f"combined upload size exceeds {limit_mb} MB limit")

        filenames.append(filename)
        extracted_text = _extract_text_from_bytes(file_bytes, filename)
        text_parts.append(f"{_source_separator(filename)}{extracted_text.strip()}")

        ext = filename.rsplit(".", 1)[1].lower()
        if ext in {"pdf", "txt"}:
            merge_candidates.append((file_bytes, filename))
        elif ext == "docx" and extracted_text.strip():
            merge_candidates.append(
                (extracted_text.encode("utf-8"), _text_artifact_filename(filename))
            )

    combined_pdf_bytes = None
    if merge_candidates:
        try:
            combined_pdf_bytes = merge_pdfs(merge_candidates)
        except Exception:
            logger.exception("simplify_v1_2: failed to merge input files - continuing without combined PDF")

    source_filename = ", ".join(filenames)
    return ResolvedInput(
        text="\n".join(text_parts).strip(),
        source_description=source_filename,
        source_filename=source_filename,
        combined_pdf_bytes=combined_pdf_bytes,
    )


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

    if len(blobs) > 1:
        blobs.sort(key=lambda b: b.updated, reverse=True)
    blob = blobs[0]
    filename = blob.name.split("/")[-1]
    return blob.download_as_bytes(), filename


def _resolve_input() -> ResolvedInput:
    """
    Resolve input from the request.

    Priority: text field > files/file field > doc_id.
    """
    json_data = request.get_json(silent=True) or {}

    text_input = (request.form.get("text") or json_data.get("text") or "").strip()
    if text_input:
        return ResolvedInput(
            text=text_input,
            source_description="text_input",
            source_filename="text_input",
            source_kind="text",
        )

    uploads = request.files.getlist("files")
    if not uploads and "file" in request.files:
        uploads = [request.files["file"]]
    if uploads:
        return _resolve_uploaded_files(uploads)

    doc_id = (request.form.get("doc_id") or json_data.get("doc_id") or "").strip()
    if doc_id:
        file_bytes, filename = _fetch_from_gcs(doc_id)
        if not _allowed(filename):
            raise ValueError("Stored file must be PDF, TXT, or DOCX")
        if len(file_bytes) > MAX_FILE_BYTES:
            raise ValueError("Stored file exceeds 10 MB limit")

        combined_pdf_bytes = None
        ext = filename.rsplit(".", 1)[1].lower()
        if ext in {"pdf", "txt"}:
            try:
                combined_pdf_bytes = merge_pdfs([(file_bytes, filename)])
            except Exception:
                logger.exception("simplify_v1_2: failed to merge stored input - continuing without combined PDF")

        return ResolvedInput(
            text=_extract_text_from_bytes(file_bytes, filename),
            source_description=f"doc:{doc_id}",
            source_filename=filename,
            combined_pdf_bytes=combined_pdf_bytes,
            source_kind="doc_id",
        )

    raise ValueError("Request must include 'files', 'file', 'text', or 'doc_id'")


def _score_or_none(text: str, label: str) -> dict | None:
    try:
        return score_text(text)
    except Exception:
        logger.exception("simplify_v1_2: %s-score failed - continuing without score", label)
        return None


def _generate_stream(user_id: str):
    try:
        yield _sse({"step": 1, "status": "active", "label": STEPS[1]})
        try:
            resolved = _resolve_input()
        except Exception as exc:
            logger.exception("simplify_v1_2: input resolution failed")
            yield _sse({"step": "error", "error": f"Could not read input: {exc}"})
            return

        text = resolved.text
        if not text.strip():
            yield _sse({"step": "error", "error": "Input appears to be empty or unreadable."})
            return

        yield _sse({"step": 1, "status": "done", "label": STEPS[1]})
        logger.info("simplify_v1_2: processing source=%s (%d chars)", resolved.source_description, len(text))

        try:
            pipeline = V1_2Pipeline()
        except Exception as e:
            yield _sse({"step": "error", "error": f"Failed to initialize pipeline: {e}"})
            return

        # Step 2: Term detection (deterministic; no LLM)
        yield _sse({"step": 2, "status": "active", "label": STEPS[2]})
        try:
            term_data = detect_terms(text)
        except Exception:
            logger.exception("simplify_v1_2: term detection failed - continuing with empty terms")
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
            logger.exception("simplify_v1_2: simplification failed")
            yield _sse({"step": "error", "error": f"Simplification failed: {exc}"})
            return
        yield _sse({"step": 3, "status": "done", "label": STEPS[3]})

        # Step 4: Clarify actions and numbers
        yield _sse({"step": 4, "status": "active", "label": STEPS[4]})
        try:
            clarified = pipeline.clarify_and_action(simplified, term_data["abbreviations"])
        except Exception:
            logger.exception("simplify_v1_2: clarify step failed - using simplified text")
            clarified = simplified
        yield _sse({"step": 4, "status": "done", "label": STEPS[4]})

        # Step 5: Structure appointment note
        yield _sse({"step": 5, "status": "active", "label": STEPS[5]})
        try:
            structured = pipeline.structure_appointment_note(clarified)
        except Exception as exc:
            logger.exception("simplify_v1_2: structuring failed")
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

        if resolved.source_kind == "doc_id":
            yield _sse({"step": "result", "data": result})
            return

        try:
            input_pdf_gcs = None
            if resolved.combined_pdf_bytes:
                input_pdf_gcs = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)

            saved_id = save_simplify_output(
                user_id=user_id,
                name=resolved.source_description,
                source_filename=resolved.source_filename,
                input_pdf_gcs=input_pdf_gcs,
                output_data=result,
            )
            result["saved_id"] = saved_id
        except Exception:
            logger.exception("simplify_v1_2: failed to save output - continuing without saved_id")

        yield _sse({"step": "result", "data": result})

    except Exception as exc:
        logger.exception("simplify_v1_2: unexpected pipeline error")
        yield _sse({"step": "error", "error": f"Pipeline error: {exc}"})


@simplify_v1_2_bp.route("/simplify/v1-2", methods=["POST"])
@verify_firebase_token
def simplify_v1_2(user_id: str):
    """Stream V1.2 simplification pipeline via SSE."""
    return Response(
        stream_with_context(_generate_stream(user_id)),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
