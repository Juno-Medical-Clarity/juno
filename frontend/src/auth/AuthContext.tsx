import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { onAuthStateChanged, signOut, type User } from 'firebase/auth';
import { firebaseAuth } from '../api/firebase';

const SESSION_TIMEOUT_MS =
  Number(import.meta.env.VITE_SESSION_TIMEOUT_MS) || 30 * 60 * 1000;
const SESSION_WARNING_MS = SESSION_TIMEOUT_MS - 2 * 60 * 1000;

const ACTIVITY_EVENTS = [
  'mousemove',
  'mousedown',
  'keydown',
  'touchstart',
  'scroll',
] as const;

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  getIdToken: () => Promise<string>;
  sessionWarning: boolean;
  extendSession: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionWarning, setSessionWarning] = useState(false);

  const logoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (logoutTimerRef.current !== null) clearTimeout(logoutTimerRef.current);
    if (warningTimerRef.current !== null) clearTimeout(warningTimerRef.current);
  }, []);

  const resetTimers = useCallback(() => {
    clearTimers();
    setSessionWarning(false);

    warningTimerRef.current = setTimeout(() => {
      setSessionWarning(true);
    }, SESSION_WARNING_MS);

    logoutTimerRef.current = setTimeout(() => {
      setSessionWarning(false);
      void signOut(firebaseAuth);
    }, SESSION_TIMEOUT_MS);
  }, [clearTimers]);

  const extendSession = useCallback(() => {
    resetTimers();
  }, [resetTimers]);

  useEffect(() => {
    return onAuthStateChanged(firebaseAuth, currentUser => {
      setUser(currentUser);
      setLoading(false);

      if (currentUser) {
        resetTimers();
      } else {
        clearTimers();
        setSessionWarning(false);
      }
    });
  }, [resetTimers, clearTimers]);

  useEffect(() => {
    if (!user) return;

    const handleActivity = () => resetTimers();

    for (const event of ACTIVITY_EVENTS) {
      document.addEventListener(event, handleActivity, { passive: true });
    }

    return () => {
      for (const event of ACTIVITY_EVENTS) {
        document.removeEventListener(event, handleActivity);
      }
    };
  }, [user, resetTimers]);

  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      getIdToken: async () => {
        if (!firebaseAuth.currentUser) {
          throw new Error('You must be signed in to use Juno.');
        }
        return firebaseAuth.currentUser.getIdToken();
      },
      sessionWarning,
      extendSession,
    }),
    [user, loading, sessionWarning, extendSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider.');
  }
  return context;
}
