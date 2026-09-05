"""utils/image_ocr.py — image → clinical text extraction via Gemini vision (Vertex AI)."""

import io

import PIL.Image

from utils.constants import Constants
from utils.llm import LLMClient
from errors import ErrorCode, JunoError

_NO_TEXT_SENTINEL = "NO_TEXT_FOUND"
_MAX_LONG_EDGE_PX = 2048

IMAGE_EXT_TO_MIME: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "heic": "image/heic",
}


def _maybe_downscale(image_bytes: bytes, ext: str) -> bytes:
    """Resize an image to a max long-edge dimension before sending to Vertex.
    Best-effort: on any decode error, returns the original bytes unchanged."""
    try:
        image = PIL.Image.open(io.BytesIO(image_bytes))
        if max(image.size) <= _MAX_LONG_EDGE_PX:
            return image_bytes
        image.thumbnail((_MAX_LONG_EDGE_PX, _MAX_LONG_EDGE_PX))
        buf = io.BytesIO()
        image.save(buf, format=image.format or "JPEG")
        return buf.getvalue()
    except Exception:
        return image_bytes


def extract_text_from_image(image_bytes: bytes, ext: str) -> str:
    """Extract clinical text from image bytes via Gemini vision on Vertex AI.

    `ext` is the already-lowercased file extension (as produced by
    care_plan_input._get_extension); mapped to a MIME type here so the
    dispatcher in care_plan_input.py stays format-agnostic.
    """
    mime_type = IMAGE_EXT_TO_MIME.get(ext)
    if mime_type is None:
        raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")

    image_bytes = _maybe_downscale(image_bytes, ext)

    client = LLMClient()
    text = client.generate_text_from_image(
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=Constants.Llm.IMAGE_OCR_PROMPT,
        temperature=Constants.Llm.TEMPERATURE_TEXT,
        max_tokens=Constants.Llm.MAX_TOKENS,
    )
    if text.strip().upper() == _NO_TEXT_SENTINEL:
        raise JunoError(
            ErrorCode.EMPTY_DOCUMENT,
            detail="Image contained no readable text (model returned NO_TEXT_FOUND).",
        )
    return text
