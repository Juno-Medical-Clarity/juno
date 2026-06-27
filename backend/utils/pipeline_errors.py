"""
utils/pipeline_errors.py — Exception classification and structured error helpers.

This is the LOGIC layer. It imports from error_codes.py (the pure data catalog)
and provides:
  - JunoError: structured pipeline exception carrying an ErrorCode
  - classify_vertex_exception: map google.api_core exceptions → ErrorCode
  - classify_finish_reason: map FinishReason strings → ErrorCode
  - make_error_response: Flask-ready (response_dict, status_code) tuple
  - build_error_data: Firestore-ready error_data dict for fail_job calls
  - build_error_data_from_exc: classify any exception → Firestore error_data dict
  - handle_exception: classify any exception → Flask-ready (response_dict, status_code)
"""

from __future__ import annotations

from datetime import datetime, timezone

from error_codes import ERROR_CATALOG, ErrorCode, ErrorInfo


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
    3. RuntimeError with "MAX_TOKENS" or "SAFETY" in message (legacy path).
    4. Everything else → UNKNOWN_ERROR.
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

    # Legacy RuntimeError classification (pre-JunoError path)
    if isinstance(exc, RuntimeError):
        msg = str(exc)
        if "MAX_TOKENS" in msg:
            return ErrorCode.LLM_MAX_TOKENS, msg
        if "SAFETY" in msg:
            return ErrorCode.LLM_SAFETY_BLOCKED, msg

    return ErrorCode.UNKNOWN_ERROR, str(exc)


# ---------------------------------------------------------------------------
# make_error_response — Flask-ready (response_dict, status_code)
# ---------------------------------------------------------------------------

def make_error_response(
    error_code: ErrorCode,
    detail: str = "",
    http_status_override: int | None = None,
) -> tuple[dict, int]:
    """
    Build a Flask-ready ``(response_dict, status_code)`` tuple for an error.

    The response dict shape:
        {
            "error": True,
            "code": "LLM_MAX_TOKENS",
            "message": "<developer-facing description>",
            "user_hint": "<user-facing actionable message>",
            "detail": "<extra context, e.g. exception string>",
            "retryable": False,
            "http_status": 500,
        }
    """
    info = ERROR_CATALOG[error_code]
    status = http_status_override if http_status_override is not None else info.http_status
    return {
        "error": True,
        "code": info.code,
        "message": info.message,
        "user_hint": info.user_hint,
        "detail": detail,
        "retryable": info.retryable,
        "http_status": info.http_status,
    }, status


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
        "timestamp": datetime.now(timezone.utc).isoformat(),  # new field
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

    Equivalent to ``make_error_response(*_classify_exc(exc))``.
    """
    error_code, detail = _classify_exc(exc)
    return make_error_response(error_code, detail=detail)
