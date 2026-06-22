import { firebaseAuth } from './firebase';
import type { ApiErrorResponse } from '../types/errors';
import { ApiError } from '../types/errors';

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const user = firebaseAuth.currentUser;
  if (!user) {
    throw new Error('You must be signed in to use Juno.');
  }

  const token = await user.getIdToken();
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${token}`);

  return fetch(input, {
    ...init,
    headers,
  });
}

export async function authenticatedFetchJson<T = Record<string, unknown>>(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<T> {
  const res = await authenticatedFetch(input, init);
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = null; }
    if (
      body &&
      typeof body === 'object' &&
      (body as Record<string, unknown>).status === 'error' &&
      (body as ApiErrorResponse).error
    ) {
      const errBody = body as ApiErrorResponse;
      throw new ApiError(errBody.error, errBody.requestId ?? null);
    }
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}
