"""errors/athena_errors.py — Athena Health API error type and classification."""
from __future__ import annotations

from errors.codes import ErrorCode
from errors.exceptions import JunoError


class AthenaAPIError(JunoError):
    """Raised when an Athena API call returns a non-200 HTTP status.

    Inherits JunoError so pipeline callers catch it uniformly. status_code
    and body are Athena-specific and remain available directly; the detail
    string also encodes them.

    Status-code -> ErrorCode mapping is centralized in classify(): callers
    that omit `code` get the correct classification automatically, including
    429 -> ATHENA_RATE_LIMIT_ERROR. Endpoint-context failures that can't be
    inferred from the status code alone (e.g. OAuth2 token-fetch failures,
    which must always be ATHENA_AUTH_FAILED regardless of which status code
    Athena happens to return) still pass `code` explicitly to override.
    """

    def __init__(
        self,
        status_code: int,
        body: str,
        code: ErrorCode | None = None,
    ) -> None:
        self.status_code = status_code
        self.body = body
        resolved_code = code if code is not None else self.classify(status_code)
        super().__init__(resolved_code, detail=f"status={status_code} body={body[:200]}")

    @classmethod
    def classify(cls, status_code: int) -> ErrorCode:
        """Single source of truth for Athena status-code -> ErrorCode mapping.

        429 always maps to ATHENA_RATE_LIMIT_ERROR. Everything else (401,
        403, 404, 500, 503, ...) maps to the generic ATHENA_API_ERROR. A
        clinical-document 404 intentionally maps to ATHENA_API_ERROR (502),
        not ATHENA_PATIENT_NOT_FOUND — that code is reserved for a future
        patient-search endpoint and is not wired up by this mapping.
        """
        if status_code == 429:
            return ErrorCode.ATHENA_RATE_LIMIT_ERROR
        return ErrorCode.ATHENA_API_ERROR
