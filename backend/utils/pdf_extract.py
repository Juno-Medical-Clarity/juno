import io
import logging
import PyPDF2

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_content: bytes) -> str:
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
    text_parts: list[str] = []
    for page_num, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text.strip())
            logger.debug("pdf_extract: page %d: %d chars", page_num + 1, len(page_text))
    full_text = "\n\n".join(text_parts)
    logger.info("pdf_extract: %d total chars from %d pages", len(full_text), len(reader.pages))
    return full_text
