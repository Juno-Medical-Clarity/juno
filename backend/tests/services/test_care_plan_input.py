"""tests/services/test_care_plan_input.py — regression tests for extension parsing
in services/care_plan_input.py.

Covers the dot-less-filename edge case: extension parsing must fail cleanly with
a JunoError rather than raising an unhandled IndexError from rsplit(".", 1)[1].
"""
import pytest

from services.care_plan_input import extract_text_from_bytes, is_allowed_extension
from errors import ErrorCode, JunoError


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
