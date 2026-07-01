"""
care_plan.py - V1.2 care plan input/upload utilities.

Shared utilities for the async job workflow (care_plan_jobs.py, worker.py, batch.py):
file upload handling, text extraction, and GCS I/O helpers. The pipeline-execution
adapter (run_care_plan_pipeline) has moved to services/care_plan_pipeline.py.
The SSE streaming route (POST /care_plan) has been removed; use POST /care_plan/jobs instead.
"""

# ── Imports & blueprint setup ──────────────────────────────────────────────────
import io
import logging
import os
import uuid

from flask import Blueprint, g, request  # noqa: F401

from utils.constants import Constants
from utils.gcs import get_gcs_bucket

from utils.pdf import merge_pdfs, extract_text_from_pdf
from models.grading import GRADING_VERSION  # noqa: F401
from models.care_plan import CarePlan, CARE_PLAN_VERSION  # noqa: F401
from models.care_plan.envelope import CarePlanInternal  # noqa: F401
from models.input import INPUT_VERSION, ResolvedInput  # noqa: F401
from errors import make_error_response, ErrorCode, build_error_data_from_exc, JunoError  # noqa: F401

logger = logging.getLogger(__name__)

care_plan_bp = Blueprint("care_plan", __name__)


# ── GCS upload helpers ─────────────────────────────────────────────────────────
def upload_combined_pdf(pdf_bytes: bytes, user_id: str) -> str:
    """Upload combined input PDF bytes and return a gs:// URI."""
    bucket_name = os.environ.get(Constants.Storage.GCS_BUCKET_ENV_VAR, "")
    if not bucket_name:
        raise RuntimeError("GCP_BUCKET_NAME is not configured")

    object_id = str(uuid.uuid4())
    blob_name = f"care_plan/{user_id}/inputs/{object_id}.pdf"

    bucket = get_gcs_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")
    return f"gs://{bucket_name}/{blob_name}"


# ── Input resolution helpers ───────────────────────────────────────────────────
def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Constants.Uploads.ALLOWED_EXTENSIONS


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
        from utils.misc import extract_text_from_html
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
    if len(files) > Constants.Uploads.MAX_FILE_COUNT:
        raise ValueError(f"Upload supports at most {Constants.Uploads.MAX_FILE_COUNT} files")

    text_parts: list[str] = []
    merge_candidates: list[tuple[bytes, str]] = []
    filenames: list[str] = []
    aggregate_bytes = 0

    for upload in files:
        filename = upload.filename
        if not _allowed(filename):
            raise ValueError("File must be PDF, TXT, DOCX, or HTML")

        file_bytes = upload.read()
        if len(file_bytes) > Constants.Uploads.MAX_FILE_BYTES:
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
    _gcs_bucket_name = os.environ.get(Constants.Storage.GCS_BUCKET_ENV_VAR, "")
    if not _gcs_bucket_name:
        raise RuntimeError("GCP_BUCKET_NAME is not configured")

    bucket = get_gcs_bucket(_gcs_bucket_name)
    prefix = f"{Constants.Uploads.UPLOAD_PREFIX}/{doc_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix))

    if not blobs:
        raise JunoError(ErrorCode.RESOURCE_NOT_FOUND, detail=f"doc_id={doc_id}")

    if len(blobs) > 1:
        blobs.sort(key=lambda b: b.updated, reverse=True)
    blob = blobs[0]
    filename = blob.name.split("/")[-1]
    return blob.download_as_bytes(), filename


