"""tests/services/test_care_plan_input.py — regression tests for extension parsing
in services/care_plan_input.py.

Covers the dot-less-filename edge case: extension parsing must fail cleanly with
a JunoError rather than raising an unhandled IndexError from rsplit(".", 1)[1].
"""
import io
from unittest.mock import patch

import pytest

from services.care_plan_input import (
    extract_text_from_bytes,
    is_allowed_extension,
    resolve_uploaded_files,
)
from errors import ErrorCode, JunoError

# A minimal, valid 1x1 PNG (no network, no fixture file needed).
_ONE_PX_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


class _FakeUpload:
    """Minimal stand-in for a Werkzeug FileStorage: .filename + .read()."""

    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._buf = io.BytesIO(data)

    def read(self):
        return self._buf.read()


def test_is_allowed_extension_rejects_dotless_filename():
    """A filename with no dot must be rejected, not raise."""
    assert is_allowed_extension("noextension") is False


def test_extract_text_from_bytes_dotless_filename_raises_juno_error():
    """extract_text_from_bytes must raise a clean JunoError (not IndexError)
    when the filename has no extension."""
    with pytest.raises(JunoError) as exc_info:
        extract_text_from_bytes(b"some bytes", "noextension")

    assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_FILE_TYPE


def test_extract_text_from_bytes_still_works_for_txt():
    """Well-formed filenames with extensions are unaffected by the fix."""
    assert extract_text_from_bytes(b"hello world", "notes.txt") == "hello world"


@patch("services.care_plan_input.extract_text_from_image")
def test_extract_text_from_bytes_dispatches_image_extensions_to_ocr(mock_extract_image):
    mock_extract_image.return_value = "ocr text"

    result = extract_text_from_bytes(b"bytes", "photo.png")

    mock_extract_image.assert_called_once_with(b"bytes", "png")
    assert result == "ocr text"


@pytest.mark.parametrize("ext", ["png", "jpg", "jpeg", "webp", "heic"])
def test_is_allowed_extension_accepts_all_image_extensions(ext):
    assert is_allowed_extension(f"x.{ext}") is True


@patch("services.care_plan_input.extract_text_from_image")
def test_resolve_uploaded_files_image_becomes_raw_merge_candidate(mock_extract_image):
    mock_extract_image.return_value = "Known OCR text from image"
    fake_upload = _FakeUpload("photo.png", _ONE_PX_PNG)

    resolved, combined_pdf_bytes = resolve_uploaded_files([fake_upload])

    assert "Known OCR text from image" in resolved.text
    assert combined_pdf_bytes is not None
