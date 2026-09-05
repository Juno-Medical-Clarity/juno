import { useEffect, useState } from 'react';
import { onAuthStateChanged, signInAnonymously, type User } from 'firebase/auth';
import { firebaseAuth } from '../api/firebase';
import { trackEvent } from '../analytics/ga';

export type AuthState = 'pending' | 'ready' | 'error';

export function useAnonAuth(): { authState: AuthState; user: User | null; retry: () => void } {
  const [authState, setAuthState] = useState<AuthState>('pending');
  const [user, setUser] = useState<User | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setAuthState('pending');

    const unsubscribe = onAuthStateChanged(firebaseAuth, (firebaseUser) => {
      if (cancelled || !firebaseUser) return;
      setUser(firebaseUser);
      setAuthState('ready');
      trackEvent({ name: 'auth_ready', params: {} });
    });

    signInAnonymously(firebaseAuth).catch((err) => {
      if (cancelled) return;
      console.error('useAnonAuth: signInAnonymously failed', err);
      setAuthState('error');
      trackEvent({ name: 'auth_failed', params: {} });
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [attempt]);

  return { authState, user, retry: () => setAttempt(a => a + 1) };
}
