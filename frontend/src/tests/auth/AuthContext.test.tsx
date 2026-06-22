import { render, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { AuthProvider, useAuth } from '../../auth/AuthContext';

vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
}));

vi.mock('firebase/auth', () => ({
  onAuthStateChanged: vi.fn((auth, cb) => {
    cb({ uid: 'test' });
    return () => {};
  }),
  signOut: vi.fn(),
}));

describe('session timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('calls signOut after SESSION_TIMEOUT_MS with no activity', async () => {
    const { signOut } = await import('firebase/auth');
    render(<AuthProvider><div /></AuthProvider>);
    await act(async () => {
      vi.advanceTimersByTime(30 * 60 * 1000 + 1);
    });
    expect(signOut).toHaveBeenCalledOnce();
  });

  it('resets timer on activity and does not sign out early', async () => {
    const { signOut } = await import('firebase/auth');
    render(<AuthProvider><div /></AuthProvider>);
    await act(async () => {
      vi.advanceTimersByTime(20 * 60 * 1000);
    });
    document.dispatchEvent(new Event('mousemove'));
    await act(async () => {
      vi.advanceTimersByTime(20 * 60 * 1000);
    });
    expect(signOut).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(10 * 60 * 1000 + 1);
    });
    expect(signOut).toHaveBeenCalledOnce();
  });

  it('sets sessionWarning to true at SESSION_WARNING_MS', async () => {
    let capturedWarning: boolean | undefined;

    function WarningSpy() {
      const { sessionWarning } = useAuth();
      capturedWarning = sessionWarning;
      return null;
    }

    render(
      <AuthProvider>
        <WarningSpy />
      </AuthProvider>,
    );

    expect(capturedWarning).toBe(false);

    await act(async () => {
      vi.advanceTimersByTime(28 * 60 * 1000 + 1);
    });
    expect(capturedWarning).toBe(true);
  });

  it('clears sessionWarning after extendSession', async () => {
    let capturedWarning: boolean | undefined;
    let capturedExtend: (() => void) | undefined;

    function SessionSpy() {
      const { sessionWarning, extendSession } = useAuth();
      capturedWarning = sessionWarning;
      capturedExtend = extendSession;
      return null;
    }

    render(
      <AuthProvider>
        <SessionSpy />
      </AuthProvider>,
    );

    await act(async () => {
      vi.advanceTimersByTime(28 * 60 * 1000 + 1);
    });
    expect(capturedWarning).toBe(true);

    await act(async () => {
      capturedExtend?.();
    });
    expect(capturedWarning).toBe(false);
  });
});
