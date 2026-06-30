"""Athena Health API error types."""
from errors import ErrorCode, JunoError


class AthenaAPIError(JunoError):
    """Raised when an Athena API call returns a non-200 HTTP status.

    Inherits JunoError so pipeline callers catch it uniformly. The
    status_code and body attributes are Athena-specific and remain
    available directly; the detail string also encodes them.
    """

    def __init__(
        self,
        status_code: int,
        body: str,
        code: ErrorCode = ErrorCode.ATHENA_API_ERROR,
    ) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(code, detail=f"status={status_code} body={body[:200]}")
