import { onAuthStateChanged, signInAnonymously, type User } from 'firebase/auth';
import { firebaseAuth } from './firebase';
import { API_URL } from './firebase';
import { ApiError } from '@main/types/errors';
import type { ApiErrorResponse } from '@main/types/errors';

export interface CreateTrialJobResponse {
  job_id: string;
}

// How long we're willing to wait for the anonymous auth session to resolve before
// treating it as unavailable. This is a no-login trial app — a "please sign in" style
// error must never reach the user, so every path below tolerates a missing user for a
// while before giving up.
const AUTH_WAIT_TIMEOUT_MS = 5000;

/**
 * Resolves with the first non-null Firebase auth user, or `null` if none shows up
 * within `timeoutMs`. Covers the startup race where a request is made before
 * `signInAnonymously` (kicked off by useAnonAuth on mount) has completed, and any
 * transient window where the anonymous session is momentarily lost.
 */
function waitForAuthUser(timeoutMs: number): Promise<User | null> {
  return new Promise((resolve) => {
    if (firebaseAuth.currentUser) {
      resolve(firebaseAuth.currentUser);
      return;
    }

    let settled = false;
    const finish = (user: User | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      unsubscribe();
      resolve(user);
    };

    const timer = setTimeout(() => finish(firebaseAuth.currentUser), timeoutMs);
    const unsubscribe = onAuthStateChanged(firebaseAuth, (user) => {
      if (user) finish(user);
    });
  });
}

/**
 * Resolves the current anonymous Firebase user, self-healing where possible instead of
 * failing fast. Order of resolution:
 *   1. `firebaseAuth.currentUser`, if already set.
 *   2. Wait briefly for `onAuthStateChanged` to fire with a user (covers the startup race).
 *   3. Attempt `signInAnonymously` once as a self-heal, then wait again briefly.
 * Only once all of that fails do we throw — and even then the message must never mention
 * "signing in", since that's not something a trial user can act on.
 */
async function getCurrentUser(): Promise<User> {
  let user = firebaseAuth.currentUser ?? (await waitForAuthUser(AUTH_WAIT_TIMEOUT_MS));

  if (!user) {
    try {
      await signInAnonymously(firebaseAuth);
    } catch (err) {
      console.error('trialApi: self-heal signInAnonymously failed', err);
    }
    user = firebaseAuth.currentUser ?? (await waitForAuthUser(AUTH_WAIT_TIMEOUT_MS));
  }

  if (!user) {
    throw new Error("Couldn't start your session. Please refresh and try again.");
  }
  return user;
}

async function getAuthHeader(): Promise<Record<string, string>> {
  const user = await getCurrentUser();
  let token: string;
  try {
    token = await user.getIdToken();
  } catch (err) {
    // getIdToken() can reject with a raw Firebase SDK error (e.g. "Firebase:
    // Error (auth/network-request-failed)."), which would otherwise reach
    // UploadScreen's catch-all `err instanceof Error` branch and be shown to
    // the trial visitor verbatim (edge-case review #8). Log the real error,
    // surface a plain-English one -- and, per the no-login requirement, this
    // must never mention "signing in".
    console.error('trialApi: user.getIdToken() failed', err);
    throw new Error('Something went wrong starting your session. Please try again.');
  }
  return { Authorization: `Bearer ${token}` };
}

export async function createTrialJob(formData: FormData): Promise<CreateTrialJobResponse> {
  const headers = await getAuthHeader();
  const res = await fetch(`${API_URL}/trial/jobs`, { method: 'POST', headers, body: formData });
  if (!res.ok) {
    let parsed: unknown;
    try { parsed = await res.json(); } catch { parsed = null; }
    if (parsed && typeof parsed === 'object' && (parsed as ApiErrorResponse).error) {
      const errBody = parsed as ApiErrorResponse;
      throw new ApiError(errBody.error, errBody.requestId ?? null);
    }
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Best-effort, fire-and-forget cleanup call — see PRD §4.13 for when this is
 * invoked and why fetch(keepalive) is used instead of navigator.sendBeacon.
 * Waits briefly for the anonymous session (same helper as getCurrentUser) but, unlike
 * createTrialJob, never self-heals or throws — if no user shows up in time, this is
 * simply a no-op, since there's nothing meaningful to clean up without a session. */
export async function deleteTrialJob(jobId: string): Promise<void> {
  const user = firebaseAuth.currentUser ?? (await waitForAuthUser(AUTH_WAIT_TIMEOUT_MS));
  if (!user) return;
  const token = await user.getIdToken();
  await fetch(`${API_URL}/trial/jobs/${jobId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
    keepalive: true,
  });
}
