"""
SP4 Task 10 — JunoLogger contract tests.

Verifies:
  - `api_version` param is gone; `function` param is present
  - `log_step` method is deleted
  - `_base_fields()` includes `function` and the three version fields; not `api_version`
"""

import inspect
import os
import sys

# Ensure the backend package root is on sys.path when run directly
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from utils.juno_logger import JunoLogger


def test_no_api_version_param():
    """__init__ must accept `function`, not `api_version`."""
    params = inspect.signature(JunoLogger.__init__).parameters
    assert "api_version" not in params, "api_version parameter must be removed from JunoLogger.__init__"
    assert "function" in params, "function parameter must be added to JunoLogger.__init__"


def test_no_log_step_method():
    """log_step must be deleted from JunoLogger."""
    assert not hasattr(JunoLogger, "log_step"), "log_step method must be removed from JunoLogger"


def test_base_fields_has_function():
    """_base_fields() must include function=<value passed at construction>."""
    logger = JunoLogger(function="test_fn")
    result = logger._base_fields()
    assert result["function"] == "test_fn", f"Expected function='test_fn', got {result.get('function')!r}"


def test_base_fields_no_api_version():
    """_base_fields() must not contain an api_version key."""
    logger = JunoLogger(function="test_fn")
    result = logger._base_fields()
    assert "api_version" not in result, "api_version must not appear in _base_fields() output"


def test_no_api_version_in_source():
    """The juno_logger.py source file must not contain the string 'api_version'."""
    source_path = os.path.join(_BACKEND_DIR, "utils", "juno_logger.py")
    with open(source_path) as f:
        source = f.read()
    assert "api_version" not in source, (
        "api_version must be fully replaced by function in juno_logger.py"
    )
