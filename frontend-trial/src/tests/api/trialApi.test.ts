import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8080',
}));

import { createTrialJob, deleteTrialJob } from '../../api/trialApi';
import * as firebaseModule from '../../api/firebase';

describe('trialApi', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = null;
  });

  describe('createTrialJob', () => {
    it('POSTs to /trial/jobs with an Authorization header and the given FormData', async () => {
      const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok-abc') };
      (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;
      fetchSpy.mockResolvedValue(new Response(JSON.stringify({ job_id: 'job-1' }), { status: 202 }));

      const fd = new FormData();
      fd.append('text', 'hi');
      const result = await createTrialJob(fd);

      expect(result).toEqual({ job_id: 'job-1' });
      const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe('http://localhost:8080/trial/jobs');
      expect(init.method).toBe('POST');
      expect(init.body).toBe(fd);
      expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-abc');
    });

    it('throws ApiError with the server code/userHint on a 400/429 error envelope', async () => {
      const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok') };
      (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;
      fetchSpy.mockResolvedValue(new Response(JSON.stringify({
        status: 'error',
        error: { code: 'RATE_LIMIT_EXCEEDED', message: 'Trial rate limit exceeded', details: null, timestamp: '2026-01-01T00:00:00Z', path: '/trial/jobs', user_hint: 'Try again later.', retryable: true },
        requestId: 'req-1',
      }), { status: 429 }));

      await expect(createTrialJob(new FormData())).rejects.toMatchObject({
        code: 'RATE_LIMIT_EXCEEDED',
        userHint: 'Try again later.',
      });
    });
  });

  describe('deleteTrialJob', () => {
    it('sends DELETE with keepalive:true and the Authorization header', async () => {
      const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok') };
      (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;
      fetchSpy.mockResolvedValue(new Response(null, { status: 204 }));

      await deleteTrialJob('job-1');

      const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe('http://localhost:8080/trial/jobs/job-1');
      expect(init.method).toBe('DELETE');
      expect(init.keepalive).toBe(true);
      expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
    });

    it('is a no-op (no fetch call) when there is no current user', async () => {
      (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = null;
      await deleteTrialJob('job-1');
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });
});
