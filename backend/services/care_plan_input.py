"""services/care_plan_input.py — input resolution and storage for the care-plan
pipeline: GCS upload, file-type validation, text extraction, multi-file
resolution, and GCS fetch (moved out of the now-deleted care-plan route module)."""

import io
import logging
import os
import uuid
from pathlib import Path

from utils.constants import Constants
from utils.gcs import get_gcs_bucket
from utils.image_ocr import extract_text_from_image
from utils.misc import extract_text_from_html, source_separator, text_artifact_filename
from utils.pdf import merge_pdfs, extract_text_from_pdf
from models.input import ResolvedInput
from errors import ErrorCode, JunoError

logger = logging.getLogger(__name__)


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


def _get_extension(filename: str) -> str:
    """Return the lowercased extension of filename, or "" if it has no dot.

    Centralizes extension parsing so callers never call ``rsplit(".", 1)[1]``
    directly on a filename that might be dot-less (which raises IndexError).
    """
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def is_allowed_extension(filename: str) -> bool:
    ext = _get_extension(filename)
    return bool(ext) and ext in Constants.Uploads.ALLOWED_EXTENSIONS


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, TXT, DOCX, HTML, or image bytes."""
    ext = _get_extension(filename)

    if not ext:
        raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"filename has no extension: {filename}")

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
        return extract_text_from_html(file_bytes)

    if ext in Constants.Uploads.IMAGE_EXTENSIONS:
        return extract_text_from_image(file_bytes, ext)

    raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")


def resolve_uploaded_files(uploads) -> tuple[ResolvedInput, bytes | None]:
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
        if not is_allowed_extension(filename):
            raise ValueError("File must be PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC)")

        file_bytes = upload.read()
        if len(file_bytes) > Constants.Uploads.MAX_FILE_BYTES:
            raise ValueError("File exceeds 10 MB limit")
        aggregate_bytes += len(file_bytes)
        if aggregate_bytes > Constants.Uploads.MAX_AGGREGATE_FILE_BYTES:
            limit_mb = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES // (1024 * 1024)
            raise ValueError(f"combined upload size exceeds {limit_mb} MB limit")

        filenames.append(filename)
        extracted_text = extract_text_from_bytes(file_bytes, filename)
        text_parts.append(f"{source_separator(filename)}{extracted_text.strip()}")

        ext = _get_extension(filename)
        if ext in {"pdf", "txt"} or ext in Constants.Uploads.IMAGE_EXTENSIONS:
            merge_candidates.append((file_bytes, filename))
        elif ext in {"docx", "html", "htm"} and extracted_text.strip():
            merge_candidates.append(
                (extracted_text.encode("utf-8"), text_artifact_filename(filename))
            )

    combined_pdf_bytes = None
    if merge_candidates:
        try:
            combined_pdf_bytes = merge_pdfs(merge_candidates)
        except Exception:
            logger.exception("care_plan_input: failed to merge input files - continuing without combined PDF")

    file_count = len(files)
    file_types = sorted({ext for f in files if (ext := _get_extension(f.filename))})

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


def fetch_from_gcs(doc_id: str) -> tuple[bytes, str]:
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


def resolve_input_from_job_doc(job) -> str:  # job: models.job.JobDoc
    if job.input_source_kind == "doc_id":
        file_bytes, filename = fetch_from_gcs(job.input_doc_id)
        return extract_text_from_bytes(file_bytes, filename)
    return job.input_text or ""


def extract_text_from_downloaded(
    base_dir: Path, group: str, input_id: str, files: list[str]
) -> str:
    parts: list[str] = []
    has_text = False
    for filename in files:
        local_path = base_dir / group / input_id / filename
        file_bytes = local_path.read_bytes()
        text = extract_text_from_bytes(file_bytes, filename).strip()
        has_text = has_text or bool(text)
        parts.append(f"\n\n--- {filename} ---\n\n{text}")
    return "".join(parts) if has_text else ""
