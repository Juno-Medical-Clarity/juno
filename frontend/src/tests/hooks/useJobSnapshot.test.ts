import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock firebase/firestore
const mockUnsubscribe = vi.fn();
const mockOnSnapshot = vi.fn();
const mockDoc = vi.fn();

vi.mock('firebase/firestore', () => ({
  doc: (...args: unknown[]) => mockDoc(...args),
  onSnapshot: (ref: unknown, successCb: (snap: unknown) => void, errorCb: (err: Error) => void) => {
    mockOnSnapshot(ref, successCb, errorCb);
    return mockUnsubscribe;
  },
}));

vi.mock('../../api/firebase', () => ({
  firebaseDb: {},
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

import { useJobSnapshot } from '../../hooks/useJobSnapshot';

describe('useJobSnapshot', () => {
  beforeEach(() => {
    mockUnsubscribe.mockClear();
    mockOnSnapshot.mockClear();
    mockDoc.mockClear();
  });

  it('starts with loading=true and jobDoc=null when jobId is provided', () => {
    const { result } = renderHook(() => useJobSnapshot('job-1'));
    expect(result.current.loading).toBe(true);
    expect(result.current.jobDoc).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('sets jobDoc and loading=false when snapshot arrives', async () => {
    const { result } = renderHook(() => useJobSnapshot('job-1'));

    await act(async () => {
      const [, successCb] = mockOnSnapshot.mock.calls[0];
      successCb({
        exists: () => true,
        data: () => ({ status: 'processing', stage: 3, output_data: null, error_data: null, name: 'Test', batch_run_id: null }),
      });
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.jobDoc).not.toBeNull();
    expect(result.current.jobDoc?.status).toBe('processing');
    expect(result.current.jobDoc?.stage).toBe(3);
  });

  it('calls unsubscribe on unmount', () => {
    const { unmount } = renderHook(() => useJobSnapshot('job-1'));
    unmount();
    expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
  });

  it('returns loading=false and jobDoc=null when jobId is null', () => {
    const { result } = renderHook(() => useJobSnapshot(null));
    expect(result.current.loading).toBe(false);
    expect(result.current.jobDoc).toBeNull();
    expect(mockOnSnapshot).not.toHaveBeenCalled();
  });

  it('defaults status to "completed" when no status field in snapshot', async () => {
    const { result } = renderHook(() => useJobSnapshot('job-1'));

    await act(async () => {
      const [, successCb] = mockOnSnapshot.mock.calls[0];
      successCb({
        exists: () => true,
        data: () => ({ stage: null, output_data: null, error_data: null, name: '', batch_run_id: null }),
      });
    });

    expect(result.current.jobDoc?.status).toBe('completed');
  });

  it('sets error when onSnapshot errors', async () => {
    const { result } = renderHook(() => useJobSnapshot('job-1'));

    await act(async () => {
      const [, , errorCb] = mockOnSnapshot.mock.calls[0];
      errorCb(new Error('Permission denied'));
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('Permission denied');
  });
});
