// Mirrors backend models/errors.py — keep in sync with StatusEnum and ErrorDetail.

export type ApiStatus = 'error' | 'success' | 'not_started' | 'processing' | 'completed';

export interface ApiErrorDetail {
  code: string;           // ErrorCode value, e.g. "RESOURCE_NOT_FOUND"
  message: string;        // human-readable summary
  details: string | null; // specific detail string
  timestamp: string;      // ISO-8601 UTC
  path: string | null;    // request path; null for worker-originated errors
  user_hint: string | null;    // new
  retryable: boolean;          // new
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
  readonly details: string | null;
  readonly requestId: string | null;
  readonly path: string | null;
  readonly userHint: string | null;   // new
  readonly retryable: boolean;        // new

  constructor(detail: ApiErrorDetail, requestId: string | null) {
    super(detail.message);
    this.name = 'ApiError';
    this.code = detail.code;
    this.details = detail.details;
    this.requestId = requestId;
    this.path = detail.path;
    this.userHint = detail.user_hint;
    this.retryable = detail.retryable;
  }
}

// Mirrors the Firestore error_data dict written by worker.py's fail_job() call.
// Does NOT include path or requestId — those are HTTP-only fields.
export interface FirestoreJobError {
  code: string;
  message: string;
  user_hint: string | null;
  retryable: boolean;
  details: string | null;
  timestamp: string;            // ISO-8601 UTC
}
