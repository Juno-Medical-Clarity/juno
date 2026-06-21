import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock firebase before importing anything that depends on it
vi.mock('./firebase', () => ({
  firebaseAuth: {
    currentUser: { getIdToken: async () => 'test-token' },
  },
  API_URL: 'http://localhost:8082',
}));

import { listSavedOutputs, getSavedOutput, renameSavedOutput, deleteSavedOutput } from './savedOutputs';

function makeResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('listSavedOutputs', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls /care_plan/saved with GET and returns parsed outputs array', async () => {
    const mockOutputs = [
      {
        id: 'abc',
        name: 'Test Output',
        source_filename: 'test.pdf',
        created_at: '2026-06-01T00:00:00Z',
        updated_at: '2026-06-01T00:00:00Z',
        batch_group_id: null,
      },
    ];
    fetchSpy.mockResolvedValueOnce(makeResponse({ outputs: mockOutputs }));

    const result = await listSavedOutputs();
    expect(result).toEqual(mockOutputs);

    const [url] = fetchSpy.mock.calls[0] as [string, unknown];
    expect(url).toContain('/care_plan/saved');
  });

  it('throws when server returns non-200', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('Not Found', { status: 404 }));
    await expect(listSavedOutputs()).rejects.toThrow('Failed to list saved outputs: 404');
  });
});

describe('getSavedOutput', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls /care_plan/saved/:id and returns the parsed output', async () => {
    const mockOutput = {
      id: 'xyz',
      name: 'My Output',
      source_filename: 'doc.pdf',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-06-01T00:00:00Z',
      batch_group_id: null,
      output_data: {},
    };
    fetchSpy.mockResolvedValueOnce(makeResponse(mockOutput));

    const result = await getSavedOutput('xyz');
    expect(result.id).toBe('xyz');

    const [url] = fetchSpy.mock.calls[0] as [string, unknown];
    expect(url).toContain('/care_plan/saved/xyz');
  });

  it('throws when server returns non-200', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('Error', { status: 500 }));
    await expect(getSavedOutput('xyz')).rejects.toThrow('Failed to get saved output: 500');
  });
});

describe('renameSavedOutput', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends PATCH with the new name in request body', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 200 }));

    await renameSavedOutput('abc', 'New Name');

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/care_plan/saved/abc');
    expect((init as RequestInit).method).toBe('PATCH');
    expect((init as RequestInit).body).toBe(JSON.stringify({ name: 'New Name' }));
  });

  it('throws on non-200 response', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('Error', { status: 400 }));
    await expect(renameSavedOutput('abc', 'Name')).rejects.toThrow('Failed to rename: 400');
  });
});

describe('deleteSavedOutput', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends DELETE to /care_plan/saved/:id', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 200 }));

    await deleteSavedOutput('abc');

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/care_plan/saved/abc');
    expect((init as RequestInit).method).toBe('DELETE');
  });

  it('throws on non-200 response', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('Error', { status: 403 }));
    await expect(deleteSavedOutput('abc')).rejects.toThrow('Failed to delete: 403');
  });
});
