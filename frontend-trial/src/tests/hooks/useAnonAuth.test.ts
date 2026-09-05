import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const mockOnAuthStateChanged = vi.fn();
const mockSignInAnonymously = vi.fn();
vi.mock('firebase/auth', () => ({
  onAuthStateChanged: (auth: unknown, cb: (u: unknown) => void) => {
    mockOnAuthStateChanged(auth, cb);
    return vi.fn();
  },
  signInAnonymously: (...args: unknown[]) => mockSignInAnonymously(...args),
}));
vi.mock('../../api/firebase', () => ({ firebaseAuth: {} }));
const trackEventMock = vi.fn();
vi.mock('../../analytics/ga', () => ({ trackEvent: (...a: unknown[]) => trackEventMock(...a) }));

import { useAnonAuth } from '../../hooks/useAnonAuth';

describe('useAnonAuth', () => {
  beforeEach(() => {
    mockOnAuthStateChanged.mockClear();
    mockSignInAnonymously.mockClear();
    trackEventMock.mockClear();
  });

  it('starts pending, becomes ready once onAuthStateChanged fires with a user', async () => {
    mockSignInAnonymously.mockResolvedValue(undefined);
    const { result } = renderHook(() => useAnonAuth());
    expect(result.current.authState).toBe('pending');

    const cb = mockOnAuthStateChanged.mock.calls[0][1];
    act(() => cb({ uid: 'anon-1' }));

    await waitFor(() => expect(result.current.authState).toBe('ready'));
    expect(result.current.user).toEqual({ uid: 'anon-1' });
    expect(trackEventMock).toHaveBeenCalledWith({ name: 'auth_ready', params: {} });
  });

  it('becomes error when signInAnonymously rejects', async () => {
    mockSignInAnonymously.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useAnonAuth());

    await waitFor(() => expect(result.current.authState).toBe('error'));
    expect(trackEventMock).toHaveBeenCalledWith({ name: 'auth_failed', params: {} });
  });

  it('retry() re-invokes signInAnonymously and can recover to ready', async () => {
    mockSignInAnonymously.mockRejectedValueOnce(new Error('down'));
    const { result } = renderHook(() => useAnonAuth());
    await waitFor(() => expect(result.current.authState).toBe('error'));

    mockSignInAnonymously.mockResolvedValueOnce(undefined);
    act(() => result.current.retry());
    const cb = mockOnAuthStateChanged.mock.calls.at(-1)![1];
    act(() => cb({ uid: 'anon-2' }));

    await waitFor(() => expect(result.current.authState).toBe('ready'));
    expect(mockSignInAnonymously).toHaveBeenCalledTimes(2);
  });
});
