"""
OCR utility using Google Cloud Vision API.

Provides text extraction from:
- Images (PNG, JPG, JPEG) via synchronous document_text_detection
- PDFs (scanned/screenshot) via synchronous batch_annotate_files (≤5 pages)
  with automatic fallback to async GCS-based processing for larger PDFs.
"""

import json
import logging
import time

from google.cloud import vision

logger = logging.getLogger(__name__)

# Maximum pages supported by the synchronous batch_annotate_files API
_SYNC_PDF_MAX_PAGES = 5


def ocr_image(image_bytes: bytes) -> str:
    """
    Extract text from a single image using Cloud Vision document_text_detection.

    Args:
        image_bytes: Raw image content (PNG, JPG, JPEG).

    Returns:
        Extracted text string (may be empty if no text detected).
    """
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)

    logger.info("[OCR] Running document_text_detection on image (%d bytes)", len(image_bytes))
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise Exception(f"Vision API error: {response.error.message}")

    text = response.full_text_annotation.text if response.full_text_annotation else ""
    logger.info("[OCR] Image OCR extracted %d characters", len(text))
    return text


def ocr_pdf(pdf_bytes: bytes) -> str:
    """
    Extract text from a PDF using Cloud Vision batch_annotate_files (synchronous).

    Handles PDFs up to 5 pages synchronously. For PDFs with more pages, only the
    first 5 pages are processed (Cloud Vision sync limit). Use ``ocr_pdf_gcs``
    for larger documents.

    Args:
        pdf_bytes: Raw PDF content in bytes.

    Returns:
        Extracted text string (may be empty if no text detected).
    """
    client = vision.ImageAnnotatorClient()

    input_config = vision.InputConfig(
        content=pdf_bytes,
        mime_type="application/pdf",
    )
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

    # batch_annotate_files processes up to 5 pages synchronously
    file_request = vision.AnnotateFileRequest(
        input_config=input_config,
        features=[feature],
        pages=list(range(1, _SYNC_PDF_MAX_PAGES + 1)),  # pages 1-5
    )

    logger.info("[OCR] Running batch_annotate_files on PDF (%d bytes)", len(pdf_bytes))
    response = client.batch_annotate_files(requests=[file_request])

    text_parts: list[str] = []
    for file_response in response.responses:
        if file_response.error.message:
            logger.error("[OCR] Vision API file-level error: %s", file_response.error.message)
            raise Exception(f"Vision API error: {file_response.error.message}")

        for page_idx, page_response in enumerate(file_response.responses):
            if page_response.error.message:
                logger.warning("[OCR] Vision API page %d error: %s", page_idx + 1, page_response.error.message)
                continue

            if page_response.full_text_annotation:
                page_text = page_response.full_text_annotation.text
                text_parts.append(page_text)
                logger.info("[OCR] PDF page %d: extracted %d characters", page_idx + 1, len(page_text))

    full_text = "\n".join(text_parts)
    logger.info("[OCR] PDF OCR total: %d characters from %d pages", len(full_text), len(text_parts))
    return full_text


def ocr_pdf_gcs(gcs_uri: str, output_gcs_prefix: str) -> str:
    """
    Extract text from a large PDF stored in GCS using the async batch API.

    This handles PDFs with more than 5 pages by using
    ``async_batch_annotate_files`` which reads from and writes to GCS.

    Args:
        gcs_uri:            GCS URI of the source PDF (gs://bucket/path/file.pdf).
        output_gcs_prefix:  GCS URI prefix for output JSON
                            (e.g. gs://bucket/ocr-output/job123/).

    Returns:
        Extracted text string.
    """
    client = vision.ImageAnnotatorClient()

    gcs_source = vision.GcsSource(uri=gcs_uri)
    input_config = vision.InputConfig(gcs_source=gcs_source, mime_type="application/pdf")

    gcs_destination = vision.GcsDestination(uri=output_gcs_prefix)
    output_config = vision.OutputConfig(gcs_destination=gcs_destination, batch_size=5)

    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

    async_request = vision.AsyncAnnotateFileRequest(
        features=[feature],
        input_config=input_config,
        output_config=output_config,
    )

    logger.info("[OCR] Starting async PDF OCR for: %s", gcs_uri)
    operation = client.async_batch_annotate_files(requests=[async_request])

    # Wait for the operation to complete (timeout: 5 minutes)
    logger.info("[OCR] Waiting for async OCR operation to complete...")
    result = operation.result(timeout=300)
    logger.info("[OCR] Async OCR operation completed")

    # Read output JSON files from GCS
    from google.cloud import storage as gcs_storage

    # Parse bucket and prefix from output URI
    # Format: gs://bucket-name/prefix/
    output_uri = result.responses[0].output_config.gcs_destination.uri
    parts = output_uri.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""

    storage_client = gcs_storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))

    text_parts: list[str] = []
    for blob in blobs:
        if not blob.name.endswith(".json"):
            continue
        json_content = json.loads(blob.download_as_bytes())
        for resp in json_content.get("responses", []):
            annotation = resp.get("fullTextAnnotation", {})
            page_text = annotation.get("text", "")
            if page_text:
                text_parts.append(page_text)

    full_text = "\n".join(text_parts)
    logger.info("[OCR] Async PDF OCR total: %d characters", len(full_text))

    # Clean up output files
    for blob in blobs:
        try:
            blob.delete()
        except Exception:
            pass

    return full_text
