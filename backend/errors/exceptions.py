"""
errors/exceptions.py — Unified exception classes, classifiers, and response builder.

This is the LOGIC layer for the Juno error system. It merges:
  - backend/utils/pipeline_errors.py (JunoError, classifiers, build_error_data*, handle_exception)
  - backend/utils/error_codes.py (_SafeDict, _safe_format, make_error_response ApiResponse version)

Provides:
  - _SafeDict, _safe_format: safe template formatting helpers
  - JunoError: structured pipeline exception carrying an ErrorCode
  - classify_vertex_exception: map google.api_core exceptions → ErrorCode
  - classify_finish_reason: map FinishReason strings → ErrorCode
  - _classify_exc: internal classifier (JunoError → Vertex → fallback)
  - make_error_response: canonical ApiResponse builder (the ONE response builder)
  - build_error_data: Firestore-ready error_data dict for fail_job calls
  - build_error_data_from_exc: classify any exception → Firestore error_data dict
  - handle_exception: classify any exception → Flask-ready (response_dict, status_code)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from errors.codes import ERROR_CATALOG, ErrorCode, ErrorInfo
from models.api_response import ApiResponse, ErrorDetail, StatusEnum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# _SafeDict / _safe_format — safe template formatting helpers
# ---------------------------------------------------------------------------

class _SafeDict(dict):
    """Substitute missing keys with their placeholder text to avoid KeyError."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _safe_format(template: str, vars: dict) -> str:
    return template.format_map(_SafeDict(vars))


# ---------------------------------------------------------------------------
# JunoError — structured pipeline exception
# ---------------------------------------------------------------------------

class JunoError(Exception):
    """
    Structured pipeline exception carrying an ErrorCode.

    Raised by the LLM client and pipeline stages to signal a known failure
    class (e.g. token-limit hit, Vertex quota exceeded) with rich metadata.
    The error_code drives the user_hint, retryable flag, and HTTP status
    surfaced to the client.
    """

    def __init__(
        self,
        error_code: ErrorCode,
        detail: str = "",
        original: Exception | None = None,
    ) -> None:
        self.error_code = error_code
        self.info: ErrorInfo = ERROR_CATALOG[error_code]
        self.detail = detail
        self.original = original
        super().__init__(self.info.message)


# ---------------------------------------------------------------------------
# classify_vertex_exception — map google.api_core exceptions → ErrorCode
# ---------------------------------------------------------------------------

def classify_vertex_exception(exc: Exception) -> ErrorCode:
    """
    Map a ``google.api_core.exceptions.*`` instance to the matching ErrorCode.

    Returns ``ErrorCode.UNKNOWN_ERROR`` if google-api-core is not installed
    or the exception type is not in the mapping.
    """
    try:
        from google.api_core import exceptions as _gexc
    except ImportError:
        return ErrorCode.UNKNOWN_ERROR

    _TYPE_MAP = [
        (_gexc.ResourceExhausted,   ErrorCode.VERTEX_QUOTA_EXCEEDED),
        (_gexc.DeadlineExceeded,    ErrorCode.VERTEX_DEADLINE_EXCEEDED),
        (_gexc.InvalidArgument,     ErrorCode.VERTEX_INVALID_ARGUMENT),
        (_gexc.PermissionDenied,    ErrorCode.VERTEX_PERMISSION_DENIED),
        (_gexc.NotFound,            ErrorCode.VERTEX_NOT_FOUND),
        (_gexc.ServiceUnavailable,  ErrorCode.VERTEX_SERVICE_UNAVAILABLE),
        (_gexc.InternalServerError, ErrorCode.VERTEX_INTERNAL_ERROR),
        (_gexc.Unauthenticated,     ErrorCode.VERTEX_UNAUTHENTICATED),
        (_gexc.Aborted,             ErrorCode.VERTEX_ABORTED),
    ]
    for exc_type, code in _TYPE_MAP:
        if isinstance(exc, exc_type):
            return code
    return ErrorCode.UNKNOWN_ERROR


# ---------------------------------------------------------------------------
# classify_finish_reason — map FinishReason strings → ErrorCode
# ---------------------------------------------------------------------------

_FINISH_REASON_MAP: dict[str, ErrorCode] = {
    "MAX_TOKENS":              ErrorCode.LLM_MAX_TOKENS,
    "SAFETY":                  ErrorCode.LLM_SAFETY_BLOCKED,
    "RECITATION":              ErrorCode.LLM_RECITATION_BLOCKED,
    "OTHER":                   ErrorCode.LLM_FINISH_OTHER,
    "BLOCKLIST":               ErrorCode.LLM_BLOCKLIST,
    "PROHIBITED_CONTENT":      ErrorCode.LLM_PROHIBITED_CONTENT,
    "SPII":                    ErrorCode.LLM_SPII,
    "MALFORMED_FUNCTION_CALL": ErrorCode.LLM_MALFORMED_FUNCTION_CALL,
}


def classify_finish_reason(finish_reason_str: str) -> ErrorCode:
    """
    Map a FinishReason string to an ErrorCode.

    Accepts either the enum ``.name`` (e.g. ``"MAX_TOKENS"``) or the
    string value — both are compared case-insensitively.
    Falls back to ``ErrorCode.LLM_FINISH_OTHER`` for unrecognised values.
    """
    return _FINISH_REASON_MAP.get(finish_reason_str.upper(), ErrorCode.LLM_FINISH_OTHER)


# ---------------------------------------------------------------------------
# Internal classifier
# ---------------------------------------------------------------------------

def _classify_exc(exc: Exception) -> tuple[ErrorCode, str]:
    """
    Return ``(error_code, detail_str)`` for any exception.

    Priority:
    1. JunoError — already classified; use its error_code and detail.
    2. google.api_core.exceptions.GoogleAPICallError → classify_vertex_exception.
    3. Everything else → UNKNOWN_ERROR.
    """
    if isinstance(exc, JunoError):
        detail = exc.detail or str(exc.original or exc)
        return exc.error_code, detail

    # Google API errors
    try:
        from google.api_core import exceptions as _gexc
        if isinstance(exc, _gexc.GoogleAPICallError):
            return classify_vertex_exception(exc), str(exc)
    except ImportError:
        pass

    return ErrorCode.UNKNOWN_ERROR, str(exc)


# ---------------------------------------------------------------------------
# make_error_response — canonical ApiResponse builder
# ---------------------------------------------------------------------------

def make_error_response(
    code: ErrorCode,
    path: str | None = None,
    details_vars: dict | None = None,
    requestId: str | None = None,
    user_hint: str | None = None,
    retryable: bool | None = None,
) -> ApiResponse:
    """Build a structured ApiResponse for an error and log it."""
    catalog_entry = ERROR_CATALOG[code]
    details = _safe_format(catalog_entry.details_template, details_vars or {})
    if requestId is None:
        try:
            from flask import g
            requestId = getattr(g, "session_id", None)
        except RuntimeError:
            requestId = None
    timestamp = datetime.now(timezone.utc).isoformat()
    error_detail = ErrorDetail(
        code=code.value,
        message=catalog_entry.message,
        details=details or None,
        timestamp=timestamp,
        path=path,
        user_hint=user_hint if user_hint is not None else catalog_entry.user_hint,
        retryable=retryable if retryable is not None else catalog_entry.retryable,
    )
    logger.error("error_response", extra={"error_code": code.value, "path": path, "request_id": requestId})
    return ApiResponse(status=StatusEnum.error, error=error_detail, requestId=requestId)


# ---------------------------------------------------------------------------
# build_error_data — Firestore-ready dict for fail_job
# ---------------------------------------------------------------------------

def build_error_data(error_code: ErrorCode, detail: str = "") -> dict:
    """Build the error_data dict written to Firestore on job failure."""
    info = ERROR_CATALOG[error_code]
    return {
        "code": info.code,
        "message": info.message,
        "user_hint": info.user_hint,
        "retryable": info.retryable,
        "details": detail or None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_error_data_from_exc(exc: Exception) -> dict:
    """
    Classify any exception and return a Firestore-ready ``error_data`` dict.

    Shorthand for ``build_error_data(*_classify_exc(exc))``.
    """
    error_code, detail = _classify_exc(exc)
    return build_error_data(error_code, detail)


# ---------------------------------------------------------------------------
# handle_exception — Flask-ready catch-all
# ---------------------------------------------------------------------------

def handle_exception(exc: Exception) -> tuple[dict, int]:
    """
    Classify any exception and return a Flask-ready ``(response_dict, status_code)`` tuple.
    """
    error_code, detail = _classify_exc(exc)
    info = ERROR_CATALOG[error_code]
    resp = make_error_response(error_code, details_vars={"detail": detail})
    return resp.model_dump(), info.http_status
