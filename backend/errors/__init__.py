"""errors — unified error package for the Juno backend.

Import from here; do not import directly from errors.codes or errors.exceptions
unless you need an internal symbol not re-exported here.
"""
from errors.codes import ERROR_CATALOG, ErrorCode, ErrorInfo
from errors.exceptions import (
    JunoError,
    make_error_response,
    build_error_data,
    build_error_data_from_exc,
    handle_exception,
    classify_vertex_exception,
    classify_finish_reason,
)
from errors.athena_errors import AthenaAPIError

__all__ = [
    "ERROR_CATALOG", "ErrorCode", "ErrorInfo",
    "JunoError",
    "make_error_response",
    "build_error_data",
    "build_error_data_from_exc",
    "handle_exception",
    "classify_vertex_exception",
    "classify_finish_reason",
    "AthenaAPIError",
]
