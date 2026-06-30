"""Athena Health API error types."""

from errors import ErrorCode, JunoError


class AthenaAPIError(JunoError):
    """Raised when an Athena API call returns a non-200 status."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        if status_code == 401:
            code = ErrorCode.ATHENA_AUTH_FAILED
        elif status_code == 429:
            code = ErrorCode.ATHENA_RATE_LIMIT_ERROR
        elif status_code == 404:
            code = ErrorCode.ATHENA_PATIENT_NOT_FOUND
        else:
            code = ErrorCode.ATHENA_API_ERROR
        super().__init__(code, detail=f"status={status_code} body={body[:200]}")
