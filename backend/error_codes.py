"""
error_codes.py — Single source of truth for Juno backend error code metadata.

This file is PURE DATA. No logic, no imports of Flask/Firestore/Vertex SDK.
It defines:
  - ErrorCode enum: canonical short uppercase identifiers for every error class
  - ErrorInfo dataclass: per-error metadata (http_status, message, user_hint, retryable)
  - ERROR_CATALOG: the lookup dict tying ErrorCode -> ErrorInfo

Usage by callers:
    from error_codes import ERROR_CATALOG, ErrorCode
    info = ERROR_CATALOG[ErrorCode.LLM_MAX_TOKENS]
    # info.http_status  -> 500
    # info.user_hint    -> "The document was too long..."
    # info.retryable    -> False

Categories
----------
1. LLM generation errors   — Vertex AI FinishReason variants + JSON parse failure
2. Vertex AI API errors     — google.api_core.exceptions mapped to HTTP semantics
3. Pipeline/processing      — file parsing, validation, document-level failures
4. System                   — catch-all unknown error
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


# ---------------------------------------------------------------------------
# ErrorInfo — metadata for a single error class
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorInfo:
    """Immutable metadata bundle for one error class."""

    code: str
    """
    Canonical short uppercase string, e.g. ``"LLM_MAX_TOKENS"``.
    Matches the ErrorCode member name exactly so callers can round-trip it.
    """

    http_status: int
    """HTTP status code the API layer should return for this error."""

    message: str
    """
    Developer-facing description.
    Explains the root cause in technical terms.
    """

    user_hint: str
    """
    Actionable plain-English message suitable for display in the client UI.
    Written for a non-technical end user.
    """

    retryable: bool
    """
    True if the same request is likely to succeed on a subsequent attempt
    (e.g., transient network error, quota reset). False for permanent failures.
    """


# ---------------------------------------------------------------------------
# ErrorCode — canonical identifiers
# ---------------------------------------------------------------------------

class ErrorCode(StrEnum):
    """
    All recognized error codes, grouped by category.

    Each member's string value equals its name so ErrorCode.LLM_MAX_TOKENS == "LLM_MAX_TOKENS".
    """

    # ------------------------------------------------------------------
    # 1. LLM Generation — Vertex AI FinishReason variants
    #    Source: vertexai.preview.generative_models.FinishReason
    # ------------------------------------------------------------------

    LLM_MAX_TOKENS = "LLM_MAX_TOKENS"
    """Generation stopped because the output hit the max_output_tokens limit."""

    LLM_SAFETY_BLOCKED = "LLM_SAFETY_BLOCKED"
    """Generation stopped because the response triggered a safety filter (FinishReason.SAFETY)."""

    LLM_RECITATION_BLOCKED = "LLM_RECITATION_BLOCKED"
    """Generation stopped due to potential verbatim recitation of training data (FinishReason.RECITATION)."""

    LLM_FINISH_OTHER = "LLM_FINISH_OTHER"
    """Generation ended for an unspecified reason (FinishReason.OTHER)."""

    LLM_BLOCKLIST = "LLM_BLOCKLIST"
    """Content matched an operator-configured term blocklist (FinishReason.BLOCKLIST)."""

    LLM_PROHIBITED_CONTENT = "LLM_PROHIBITED_CONTENT"
    """Content was flagged as prohibited by platform policy (FinishReason.PROHIBITED_CONTENT)."""

    LLM_SPII = "LLM_SPII"
    """
    Generation blocked because the response contained sensitive personally
    identifiable information (FinishReason.SPII).
    """

    LLM_MALFORMED_FUNCTION_CALL = "LLM_MALFORMED_FUNCTION_CALL"
    """
    Model emitted a function call that did not conform to the declared schema
    (FinishReason.MALFORMED_FUNCTION_CALL).
    """

    LLM_NO_CANDIDATES = "LLM_NO_CANDIDATES"
    """Model returned an empty candidates list; generation produced no output."""

    LLM_INVALID_JSON = "LLM_INVALID_JSON"
    """Model output could not be parsed as valid JSON after fence-stripping."""

    # ------------------------------------------------------------------
    # 2. Vertex AI API Errors
    #    Source: google.api_core.exceptions (gRPC/HTTP mapped)
    # ------------------------------------------------------------------

    VERTEX_QUOTA_EXCEEDED = "VERTEX_QUOTA_EXCEEDED"
    """API quota or rate limit exceeded (ResourceExhausted / HTTP 429)."""

    VERTEX_DEADLINE_EXCEEDED = "VERTEX_DEADLINE_EXCEEDED"
    """Vertex AI API call timed out server-side (DeadlineExceeded / HTTP 504)."""

    VERTEX_INVALID_ARGUMENT = "VERTEX_INVALID_ARGUMENT"
    """Request payload was rejected by the API as invalid (InvalidArgument / HTTP 400)."""

    VERTEX_PERMISSION_DENIED = "VERTEX_PERMISSION_DENIED"
    """Caller lacks IAM permission to invoke the Vertex AI endpoint (PermissionDenied / HTTP 403)."""

    VERTEX_NOT_FOUND = "VERTEX_NOT_FOUND"
    """Requested model or resource does not exist in the project/region (NotFound / HTTP 404)."""

    VERTEX_SERVICE_UNAVAILABLE = "VERTEX_SERVICE_UNAVAILABLE"
    """Vertex AI service is temporarily unavailable (ServiceUnavailable / HTTP 503)."""

    VERTEX_INTERNAL_ERROR = "VERTEX_INTERNAL_ERROR"
    """Vertex AI returned an internal server error (InternalServerError / HTTP 500->502)."""

    VERTEX_UNAUTHENTICATED = "VERTEX_UNAUTHENTICATED"
    """Request lacked valid credentials for the Vertex AI API (Unauthenticated / HTTP 401)."""

    VERTEX_ABORTED = "VERTEX_ABORTED"
    """Vertex AI aborted the operation, typically due to a concurrency conflict (Aborted / HTTP 503)."""

    # ------------------------------------------------------------------
    # 3. Pipeline / Processing Errors
    # ------------------------------------------------------------------

    FILE_PARSE_FAILED = "FILE_PARSE_FAILED"
    """An uploaded file could not be read or its text could not be extracted."""

    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    """The file extension or MIME type is not accepted by the pipeline."""

    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    """The document produced no extractable text after parsing."""

    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    """The LLM output or pipeline input is missing one or more required structured fields."""

    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"
    """The pipeline worker exceeded its allocated wall-clock time limit."""

    JOB_TIMEOUT = "JOB_TIMEOUT"
    """The individual job exceeded its allocated processing time."""

    PIPELINE_VALIDATION_FAILED = "PIPELINE_VALIDATION_FAILED"
    """Pydantic (or equivalent) validation of the LLM-structured output failed."""

    # ------------------------------------------------------------------
    # 4. System / Catch-all
    # ------------------------------------------------------------------

    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    """An unexpected error with no more specific classification."""


# ---------------------------------------------------------------------------
# ERROR_CATALOG — main lookup table
# ---------------------------------------------------------------------------

ERROR_CATALOG: dict[ErrorCode, ErrorInfo] = {

    # ------------------------------------------------------------------
    # LLM Generation
    # ------------------------------------------------------------------

    ErrorCode.LLM_MAX_TOKENS: ErrorInfo(
        code="LLM_MAX_TOKENS",
        http_status=500,
        message=(
            "LLM generation stopped at the output token limit (FinishReason.MAX_TOKENS) "
            "before the response was complete. Prompt may be too large or max_tokens too low."
        ),
        user_hint=(
            "The document was too long to process in full. "
            "Try uploading a shorter document or splitting it into smaller sections."
        ),
        retryable=False,
    ),

    ErrorCode.LLM_SAFETY_BLOCKED: ErrorInfo(
        code="LLM_SAFETY_BLOCKED",
        http_status=422,
        message=(
            "LLM output was blocked by a Vertex AI safety filter (FinishReason.SAFETY). "
            "The prompt or generated content matched a configured harm category threshold."
        ),
        user_hint=(
            "The document could not be processed because it triggered a content safety check. "
            "Remove any flagged content and try again."
        ),
        retryable=False,
    ),

    ErrorCode.LLM_RECITATION_BLOCKED: ErrorInfo(
        code="LLM_RECITATION_BLOCKED",
        http_status=422,
        message=(
            "LLM output was stopped due to potential verbatim recitation of training data "
            "(FinishReason.RECITATION)."
        ),
        user_hint=(
            "The document could not be processed due to a content policy restriction. "
            "Contact support if this continues."
        ),
        retryable=False,
    ),

    ErrorCode.LLM_FINISH_OTHER: ErrorInfo(
        code="LLM_FINISH_OTHER",
        http_status=500,
        message=(
            "LLM generation ended for an unspecified reason (FinishReason.OTHER). "
            "No content was returned."
        ),
        user_hint=(
            "The AI model stopped unexpectedly. Please try again. "
            "If the problem persists, contact support."
        ),
        retryable=True,
    ),

    ErrorCode.LLM_BLOCKLIST: ErrorInfo(
        code="LLM_BLOCKLIST",
        http_status=422,
        message=(
            "LLM output matched a term in the operator-configured blocklist "
            "(FinishReason.BLOCKLIST)."
        ),
        user_hint=(
            "The document contains restricted content and could not be processed. "
            "Contact support if you believe this is an error."
        ),
        retryable=False,
    ),

    ErrorCode.LLM_PROHIBITED_CONTENT: ErrorInfo(
        code="LLM_PROHIBITED_CONTENT",
        http_status=422,
        message=(
            "LLM output was blocked because it was classified as prohibited content "
            "(FinishReason.PROHIBITED_CONTENT)."
        ),
        user_hint=(
            "The document contains content that cannot be processed under our usage policy. "
            "Contact support if you believe this is in error."
        ),
        retryable=False,
    ),

    ErrorCode.LLM_SPII: ErrorInfo(
        code="LLM_SPII",
        http_status=422,
        message=(
            "LLM generation was blocked because the response contained sensitive personally "
            "identifiable information (FinishReason.SPII)."
        ),
        user_hint=(
            "The document could not be processed because the response contained sensitive "
            "personal information. Please review the document contents and try again."
        ),
        retryable=False,
    ),

    ErrorCode.LLM_MALFORMED_FUNCTION_CALL: ErrorInfo(
        code="LLM_MALFORMED_FUNCTION_CALL",
        http_status=500,
        message=(
            "LLM emitted a function/tool call that did not conform to the declared schema "
            "(FinishReason.MALFORMED_FUNCTION_CALL). This is an internal prompt engineering issue."
        ),
        user_hint=(
            "An internal error occurred during AI processing. Please try again. "
            "If the problem persists, contact support."
        ),
        retryable=True,
    ),

    ErrorCode.LLM_NO_CANDIDATES: ErrorInfo(
        code="LLM_NO_CANDIDATES",
        http_status=500,
        message=(
            "The Vertex AI model response contained no candidates. "
            "The generation may have been fully blocked before producing any output."
        ),
        user_hint=(
            "The AI model did not produce a response. Please try again. "
            "If the problem persists, contact support."
        ),
        retryable=True,
    ),

    ErrorCode.LLM_INVALID_JSON: ErrorInfo(
        code="LLM_INVALID_JSON",
        http_status=500,
        message=(
            "The LLM returned output that could not be parsed as valid JSON after "
            "markdown fence-stripping. The model may have deviated from the required schema."
        ),
        user_hint=(
            "An internal error occurred while processing the AI response. "
            "Please try again."
        ),
        retryable=True,
    ),

    # ------------------------------------------------------------------
    # Vertex AI API Errors
    # ------------------------------------------------------------------

    ErrorCode.VERTEX_QUOTA_EXCEEDED: ErrorInfo(
        code="VERTEX_QUOTA_EXCEEDED",
        http_status=429,
        message=(
            "Vertex AI API quota or rate limit exceeded (google.api_core.exceptions.ResourceExhausted). "
            "Too many requests in a short window or the project QPM/TPM quota is exhausted."
        ),
        user_hint=(
            "The system is temporarily busy. Please wait a moment and try again."
        ),
        retryable=True,
    ),

    ErrorCode.VERTEX_DEADLINE_EXCEEDED: ErrorInfo(
        code="VERTEX_DEADLINE_EXCEEDED",
        http_status=504,
        message=(
            "The Vertex AI API call timed out before a response was received "
            "(google.api_core.exceptions.DeadlineExceeded)."
        ),
        user_hint=(
            "The request timed out. Please try again. "
            "If the document is very long, consider uploading a shorter version."
        ),
        retryable=True,
    ),

    ErrorCode.VERTEX_INVALID_ARGUMENT: ErrorInfo(
        code="VERTEX_INVALID_ARGUMENT",
        http_status=400,
        message=(
            "The Vertex AI API rejected the request as invalid "
            "(google.api_core.exceptions.InvalidArgument). "
            "Likely a malformed prompt, unsupported parameter, or schema mismatch."
        ),
        user_hint=(
            "The request could not be processed due to an invalid parameter. "
            "Contact support if this continues."
        ),
        retryable=False,
    ),

    ErrorCode.VERTEX_PERMISSION_DENIED: ErrorInfo(
        code="VERTEX_PERMISSION_DENIED",
        http_status=403,
        message=(
            "The service account lacks IAM permission to call the Vertex AI endpoint "
            "(google.api_core.exceptions.PermissionDenied). "
            "Check roles/aiplatform.user on the GCP project."
        ),
        user_hint=(
            "A configuration error prevented the system from processing your request. "
            "Contact support."
        ),
        retryable=False,
    ),

    ErrorCode.VERTEX_NOT_FOUND: ErrorInfo(
        code="VERTEX_NOT_FOUND",
        http_status=404,
        message=(
            "The requested Vertex AI model or resource was not found in the configured "
            "project/region (google.api_core.exceptions.NotFound). "
            "Check VERTEX_AI_MODEL and GCP_LOCATION environment variables."
        ),
        user_hint=(
            "A configuration error prevented the system from reaching the AI model. "
            "Contact support."
        ),
        retryable=False,
    ),

    ErrorCode.VERTEX_SERVICE_UNAVAILABLE: ErrorInfo(
        code="VERTEX_SERVICE_UNAVAILABLE",
        http_status=503,
        message=(
            "The Vertex AI service is temporarily unavailable "
            "(google.api_core.exceptions.ServiceUnavailable)."
        ),
        user_hint=(
            "The AI service is temporarily unavailable. Please try again in a few minutes."
        ),
        retryable=True,
    ),

    ErrorCode.VERTEX_INTERNAL_ERROR: ErrorInfo(
        code="VERTEX_INTERNAL_ERROR",
        http_status=502,
        message=(
            "Vertex AI returned an internal server error "
            "(google.api_core.exceptions.InternalServerError)."
        ),
        user_hint=(
            "The AI service encountered an internal error. Please try again."
        ),
        retryable=True,
    ),

    ErrorCode.VERTEX_UNAUTHENTICATED: ErrorInfo(
        code="VERTEX_UNAUTHENTICATED",
        http_status=401,
        message=(
            "The Vertex AI API call was rejected due to missing or invalid credentials "
            "(google.api_core.exceptions.Unauthenticated). "
            "Application Default Credentials may not be configured correctly."
        ),
        user_hint=(
            "A configuration error prevented the system from authenticating. "
            "Contact support."
        ),
        retryable=False,
    ),

    ErrorCode.VERTEX_ABORTED: ErrorInfo(
        code="VERTEX_ABORTED",
        http_status=503,
        message=(
            "The Vertex AI operation was aborted, typically due to a concurrency conflict "
            "(google.api_core.exceptions.Aborted)."
        ),
        user_hint=(
            "The request was interrupted. Please try again."
        ),
        retryable=True,
    ),

    # ------------------------------------------------------------------
    # Pipeline / Processing Errors
    # ------------------------------------------------------------------

    ErrorCode.FILE_PARSE_FAILED: ErrorInfo(
        code="FILE_PARSE_FAILED",
        http_status=422,
        message=(
            "Failed to extract text from the uploaded file. "
            "The file may be corrupt, password-protected, or in an unsupported encoding."
        ),
        user_hint=(
            "Your file could not be read. Make sure it is not password-protected or corrupted "
            "and try uploading it again."
        ),
        retryable=False,
    ),

    ErrorCode.UNSUPPORTED_FILE_TYPE: ErrorInfo(
        code="UNSUPPORTED_FILE_TYPE",
        http_status=415,
        message=(
            "The uploaded file's extension or MIME type is not supported by the pipeline. "
            "Accepted formats: PDF, TXT, DOCX, HTML."
        ),
        user_hint=(
            "The file type you uploaded is not supported. "
            "Please upload a PDF, TXT, DOCX, or HTML file."
        ),
        retryable=False,
    ),

    ErrorCode.EMPTY_DOCUMENT: ErrorInfo(
        code="EMPTY_DOCUMENT",
        http_status=422,
        message=(
            "The document produced no extractable text after parsing. "
            "It may be a scanned image without OCR, an empty file, or all-whitespace content."
        ),
        user_hint=(
            "No readable text was found in the document. "
            "Make sure the file contains selectable text (not just a scanned image) and try again."
        ),
        retryable=False,
    ),

    ErrorCode.MISSING_REQUIRED_FIELDS: ErrorInfo(
        code="MISSING_REQUIRED_FIELDS",
        http_status=422,
        message=(
            "The pipeline input or LLM-structured output is missing one or more required fields. "
            "This may indicate a schema version mismatch or an incomplete model response."
        ),
        user_hint=(
            "The document could not be fully structured. Please try again. "
            "If the problem persists, contact support."
        ),
        retryable=True,
    ),

    ErrorCode.PIPELINE_TIMEOUT: ErrorInfo(
        code="PIPELINE_TIMEOUT",
        http_status=504,
        message=(
            "The pipeline worker exceeded its allocated wall-clock time limit "
            "before all processing stages could complete."
        ),
        user_hint=(
            "Processing took too long and was stopped. "
            "Try uploading a shorter document."
        ),
        retryable=False,
    ),

    ErrorCode.JOB_TIMEOUT: ErrorInfo(
        code="JOB_TIMEOUT",
        http_status=504,
        message=(
            "The job exceeded its allocated processing time "
            "before all pipeline stages could complete."
        ),
        user_hint=(
            "Processing took too long and was stopped. "
            "Try uploading a shorter document."
        ),
        retryable=False,
    ),

    ErrorCode.PIPELINE_VALIDATION_FAILED: ErrorInfo(
        code="PIPELINE_VALIDATION_FAILED",
        http_status=500,
        message=(
            "Pydantic validation of the LLM-structured output failed. "
            "The model response did not conform to the expected output schema."
        ),
        user_hint=(
            "An internal error occurred while validating the AI output. Please try again."
        ),
        retryable=True,
    ),

    # ------------------------------------------------------------------
    # System / Catch-all
    # ------------------------------------------------------------------

    ErrorCode.UNKNOWN_ERROR: ErrorInfo(
        code="UNKNOWN_ERROR",
        http_status=500,
        message=(
            "An unexpected error occurred that does not match any known error class. "
            "See server logs for full traceback."
        ),
        user_hint=(
            "An unexpected error occurred. Please try again. "
            "If the problem persists, contact support."
        ),
        retryable=False,
    ),
}


# ---------------------------------------------------------------------------
# Sanity assertion: every ErrorCode must have a catalog entry
# ---------------------------------------------------------------------------

_missing = [ec for ec in ErrorCode if ec not in ERROR_CATALOG]
if _missing:
    raise AssertionError(
        f"error_codes.py: missing ERROR_CATALOG entries for: {[ec.value for ec in _missing]}"
    )
