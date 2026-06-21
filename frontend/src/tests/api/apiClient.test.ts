import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock firebase before importing apiClient so the module initializes with the mock
vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

import { authenticatedFetch } from '../../api/apiClient';
import * as firebaseModule from '../../api/firebase';

describe('authenticatedFetch', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Reset currentUser to null between tests
    (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = null;
  });

  it('throws when there is no signed-in user', async () => {
    (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = null;

    await expect(authenticatedFetch('/care_plan/saved')).rejects.toThrow(
      'You must be signed in to use Juno.',
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('sets Authorization header with Bearer token when signed in', async () => {
    const mockUser = { getIdToken: vi.fn().mockResolvedValue('test-token-abc') };
    (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;

    await authenticatedFetch('/care_plan/saved');

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [, initArg] = fetchSpy.mock.calls[0] as [unknown, RequestInit];
    const headers = initArg.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer test-token-abc');
  });

  it('passes through the request URL unchanged', async () => {
    const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok') };
    (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;

    await authenticatedFetch('http://localhost:8082/care_plan/saved');

    const [urlArg] = fetchSpy.mock.calls[0] as [string, unknown];
    expect(urlArg).toBe('http://localhost:8082/care_plan/saved');
  });

  it('passes through additional init options (method, body)', async () => {
    const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok') };
    (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;

    await authenticatedFetch('/care_plan/grade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ saved_id: 'abc' }),
    });

    const [, initArg] = fetchSpy.mock.calls[0] as [unknown, RequestInit];
    expect((initArg as RequestInit).method).toBe('POST');
    expect((initArg as RequestInit).body).toBe(JSON.stringify({ saved_id: 'abc' }));
  });

  it('merges caller-provided headers with Authorization', async () => {
    const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok') };
    (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;

    await authenticatedFetch('/care_plan/saved', {
      headers: { 'X-Custom': 'value' },
    });

    const [, initArg] = fetchSpy.mock.calls[0] as [unknown, RequestInit];
    const headers = initArg.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer tok');
    expect(headers.get('X-Custom')).toBe('value');
  });
});
