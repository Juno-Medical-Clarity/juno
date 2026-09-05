import { firebaseAuth } from './firebase';
import { API_URL } from './firebase';
import { ApiError } from '@main/types/errors';
import type { ApiErrorResponse } from '@main/types/errors';

export interface CreateTrialJobResponse {
  job_id: string;
}

async function getAuthHeader(): Promise<Record<string, string>> {
  const user = firebaseAuth.currentUser;
  if (!user) {
    throw new Error('Not signed in yet — please wait a moment and try again.');
  }
  const token = await user.getIdToken();
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
 * invoked and why fetch(keepalive) is used instead of navigator.sendBeacon. */
export async function deleteTrialJob(jobId: string): Promise<void> {
  const user = firebaseAuth.currentUser;
  if (!user) return;
  const token = await user.getIdToken();
  await fetch(`${API_URL}/trial/jobs/${jobId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
    keepalive: true,
  });
}
