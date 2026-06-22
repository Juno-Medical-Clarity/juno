// Mirrors backend models/errors.py — keep in sync with StatusEnum and ErrorDetail.

export type ApiStatus = 'error' | 'success' | 'not_started' | 'processing' | 'completed';

export interface ApiErrorDetail {
  code: string;           // ErrorCode value, e.g. "RESOURCE_NOT_FOUND"
  message: string;        // human-readable summary
  details: string;        // specific detail string
  timestamp: string;      // ISO-8601 UTC
  path: string | null;    // request path; null for worker-originated errors
}

export interface ApiErrorResponse {
  status: 'error';
  error: ApiErrorDetail;
  requestId: string | null;
}

export interface ApiSuccessResponse<T = Record<string, unknown>> {
  status: 'success';
  data: T;
  requestId: string | null;
}

/** Discriminated union for a parsed API response envelope. */
export type ApiResponse<T = Record<string, unknown>> =
  | ApiSuccessResponse<T>
  | ApiErrorResponse;

/** Error thrown by authenticatedFetchJson when the server returns an error body. */
export class ApiError extends Error {
  readonly code: string;
  readonly details: string;
  readonly requestId: string | null;
  readonly path: string | null;

  constructor(detail: ApiErrorDetail, requestId: string | null) {
    super(detail.message);
    this.name = 'ApiError';
    this.code = detail.code;
    this.details = detail.details;
    this.requestId = requestId;
    this.path = detail.path;
  }
}
