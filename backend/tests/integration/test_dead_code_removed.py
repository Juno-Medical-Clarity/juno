"""
tests/integration/test_dead_code_removed.py — Guard against re-introduction of deleted modules.

Each test asserts that the corresponding module raises ModuleNotFoundError on
import, confirming it has been permanently removed from the codebase.
"""

import sys
import pytest


def _assert_module_not_found(module_name: str) -> None:
    # Remove any cached reference so the import is attempted fresh.
    sys.modules.pop(module_name, None)
    with pytest.raises(ModuleNotFoundError):
        __import__(module_name)


def test_utils_vertex_ai_not_importable():
    _assert_module_not_found("utils.vertex_ai")


def test_utils_ocr_not_importable():
    _assert_module_not_found("utils.ocr")


def test_utils_storage_not_importable():
    _assert_module_not_found("utils.storage")


def test_utils_pdf_extract_not_importable():
    _assert_module_not_found("utils.pdf_extract")


def test_utils_pdf_merge_not_importable():
    _assert_module_not_found("utils.pdf_merge")


def test_utils_gemini_client_not_importable():
    _assert_module_not_found("utils.gemini_client")


def test_utils_auth_not_importable():
    _assert_module_not_found("utils.auth")


def test_utils_save_output_not_importable():
    _assert_module_not_found("utils.save_output")


def test_utils_gcs_not_importable():
    _assert_module_not_found("utils.gcs")
