from __future__ import annotations
import logging
from datetime import datetime, timezone
from enum import StrEnum
from flask import g

from models.errors import ApiResponse, ErrorDetail, StatusEnum

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    # Auth
    UNAUTHORIZED            = "UNAUTHORIZED"
    MISSING_AUTH_HEADER     = "MISSING_AUTH_HEADER"
    MALFORMED_AUTH_HEADER   = "MALFORMED_AUTH_HEADER"
    # Resource
    RESOURCE_NOT_FOUND      = "RESOURCE_NOT_FOUND"
    RESOURCE_FORBIDDEN      = "RESOURCE_FORBIDDEN"
    # Input
    INPUT_VALIDATION_ERROR  = "INPUT_VALIDATION_ERROR"
    INPUT_EMPTY             = "INPUT_EMPTY"
    UNSUPPORTED_FILE_TYPE   = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE          = "FILE_TOO_LARGE"
    UNKNOWN_VERSION         = "UNKNOWN_VERSION"
    # Pipeline / processing
    PIPELINE_ERROR          = "PIPELINE_ERROR"
    PIPELINE_INIT_ERROR     = "PIPELINE_INIT_ERROR"
    SIMPLIFICATION_FAILED   = "SIMPLIFICATION_FAILED"
    STRUCTURING_FAILED      = "STRUCTURING_FAILED"
    # Timeout
    TIMEOUT                 = "TIMEOUT"
    JOB_TIMEOUT             = "JOB_TIMEOUT"
    # Batch
    BATCH_TOO_LARGE         = "BATCH_TOO_LARGE"
    BATCH_INVALID_SELECTION = "BATCH_INVALID_SELECTION"
    DATASET_NOT_FOUND       = "DATASET_NOT_FOUND"
    DATASET_DOWNLOAD_ERROR  = "DATASET_DOWNLOAD_ERROR"
    # Grading / saving
    NO_SOURCE_TEXT          = "NO_SOURCE_TEXT"
    SAVE_FAILED             = "SAVE_FAILED"
    PDF_URL_UNAVAILABLE     = "PDF_URL_UNAVAILABLE"
    # General
    INTERNAL_ERROR          = "INTERNAL_ERROR"
    ENDPOINT_NOT_FOUND      = "ENDPOINT_NOT_FOUND"
    # Athena Health
    ATHENA_AUTH_FAILED       = "ATHENA_AUTH_FAILED"
    ATHENA_API_ERROR         = "ATHENA_API_ERROR"
    ATHENA_RATE_LIMIT_ERROR  = "ATHENA_RATE_LIMIT_ERROR"
    ATHENA_PATIENT_NOT_FOUND = "ATHENA_PATIENT_NOT_FOUND"
    ATHENA_TIMEOUT           = "ATHENA_TIMEOUT"


_REGISTRY: dict[ErrorCode, tuple[str, str]] = {
    ErrorCode.UNAUTHORIZED:            ("Authentication failed",                        "Invalid or expired token: {detail}"),
    ErrorCode.MISSING_AUTH_HEADER:     ("No authorization header",                      "Request must include an Authorization: Bearer <token> header"),
    ErrorCode.MALFORMED_AUTH_HEADER:   ("Malformed Authorization header",               "Expected format: Authorization: Bearer <token>"),
    ErrorCode.RESOURCE_NOT_FOUND:      ("Resource not found",                           "{collection} document {doc_id} does not exist"),
    ErrorCode.RESOURCE_FORBIDDEN:      ("Access denied",                                "You do not own {collection} document {doc_id}"),
    ErrorCode.INPUT_VALIDATION_ERROR:  ("Invalid request input",                        "{field}: {reason}"),
    ErrorCode.INPUT_EMPTY:             ("Input appears to be empty or unreadable",      "Extracted text was empty after parsing"),
    ErrorCode.UNSUPPORTED_FILE_TYPE:   ("Unsupported file type",                        "File must be PDF, TXT, or DOCX; got {ext}"),
    ErrorCode.FILE_TOO_LARGE:          ("File exceeds size limit",                      "File size {size_mb}MB exceeds {limit_mb}MB limit"),
    ErrorCode.UNKNOWN_VERSION:         ("Unknown pipeline version",                     "Version {version} is not supported. Allowed: {allowed}"),
    ErrorCode.PIPELINE_ERROR:          ("Pipeline error",                               "Unexpected error during processing: {detail}"),
    ErrorCode.PIPELINE_INIT_ERROR:     ("Pipeline initialization failed",               "Could not initialize pipeline: {detail}"),
    ErrorCode.SIMPLIFICATION_FAILED:   ("Simplification step failed",                   "LLM simplification error: {detail}"),
    ErrorCode.STRUCTURING_FAILED:      ("Structuring step failed",                      "LLM structuring error: {detail}"),
    ErrorCode.TIMEOUT:                 ("Request timed out",                            "Operation exceeded time limit"),
    ErrorCode.JOB_TIMEOUT:             ("Job timed out",                                "Job exceeded the worker time limit at stage {stage}"),
    ErrorCode.BATCH_TOO_LARGE:         ("Batch request too large",                      "Requested {count} runs; maximum is {max_runs}"),
    ErrorCode.BATCH_INVALID_SELECTION: ("Invalid batch selection",                      "{detail}"),
    ErrorCode.DATASET_NOT_FOUND:       ("Dataset not found",                            "Dataset {group}/{input_id} does not exist"),
    ErrorCode.DATASET_DOWNLOAD_ERROR:  ("GCS dataset download failed",                  "Failed to download {group}/{input_id} from GCS: {detail}"),
    ErrorCode.NO_SOURCE_TEXT:          ("No source text available",                     "Saved output {saved_id} has no raw text to re-grade"),
    ErrorCode.SAVE_FAILED:             ("Failed to save output",                        "Firestore write failed: {detail}"),
    ErrorCode.PDF_URL_UNAVAILABLE:     ("No input PDF stored for this output",          "Output {doc_id} has no associated PDF"),
    ErrorCode.INTERNAL_ERROR:          ("Internal server error",                        "An unexpected error occurred"),
    ErrorCode.ENDPOINT_NOT_FOUND:      ("Endpoint not found",                           "No route matches {method} {path}"),
    # Athena Health
    ErrorCode.ATHENA_AUTH_FAILED:       ("Athena Health authentication failed",          "OAuth2 token request failed: {detail}"),
    ErrorCode.ATHENA_API_ERROR:         ("Athena Health API error",                      "Athena API returned an error for {athena_api_path}: {detail}"),
    ErrorCode.ATHENA_RATE_LIMIT_ERROR:  ("Athena Health rate limit exceeded",            "Rate limit hit on {athena_api_path}; retry after {retry_after}s"),
    ErrorCode.ATHENA_PATIENT_NOT_FOUND: ("Athena Health patient not found",              "No patient found for practiceId={practice_id} patientId={patient_id}"),
    ErrorCode.ATHENA_TIMEOUT:           ("Athena Health API request timed out",          "Request to {athena_api_path} exceeded the timeout of {timeout_s}s"),
}


def make_error_response(
    code: ErrorCode,
    path: str | None = None,
    details_vars: dict | None = None,
    requestId: str | None = None,
    user_hint: str | None = None,
    retryable: bool = False,
) -> ApiResponse:
    """Build a structured ApiResponse for an error and log it."""
    message, details_template = _REGISTRY.get(code, ("Unknown error", "{detail}"))
    details = _safe_format(details_template, details_vars or {})

    if requestId is None:
        try:
            requestId = getattr(g, "session_id", None)
        except RuntimeError:
            requestId = None

    timestamp = datetime.now(timezone.utc).isoformat()

    error_detail = ErrorDetail(
        code=code.value,
        message=message,
        details=details or None,        # convert empty string to None
        timestamp=timestamp,
        path=path,
        user_hint=user_hint,
        retryable=retryable,
    )

    logger.error(
        "error_response",
        extra={
            "error_code": code.value,
            "error_message": message,
            "error_details": details,
            "request_id": requestId,
            "path": path,
            "timestamp": timestamp,
        },
    )

    return ApiResponse(
        status=StatusEnum.error,
        error=error_detail,
        requestId=requestId,
    )


class _SafeDict(dict):
    """Substitute missing keys with their placeholder text to avoid KeyError."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _safe_format(template: str, vars: dict) -> str:
    return template.format_map(_SafeDict(vars))
