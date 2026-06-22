# TASKS: Firebase Identity Platform Upgrade & Session Inactivity Timeout (SP-10)

Generated from PRD.md (all §9 items are [RESOLVED] or [DEFERRED]).

---

## Dependency Order

```
Task 1 (AuthContext.tsx rewrite)
  └── Task 2 (SessionTimeoutWarning.tsx — new component)
        └── Task 3 (AuthLayout.tsx — render warning)
              └── Task 4 (unit tests for AuthContext)
```

Part A (Identity Platform) has no code changes. See "Summary of what requires you" at the end.

---

## Task 1 — Rewrite `AuthContext.tsx` to add session inactivity timeout

**Purpose:** Replace the current minimal `AuthContext.tsx` with one that tracks user inactivity,
fires a 28-minute warning state, and signs the user out at 30 minutes. This is the core HIPAA
§164.312(a)(2)(ii) change.

### Files

- `frontend/src/auth/AuthContext.tsx` — full replacement

### Current state (lines 1–49)

```typescript
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { onAuthStateChanged, type User } from 'firebase/auth';
import { firebaseAuth } from '../api/firebase';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  getIdToken: () => Promise<string>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    return onAuthStateChanged(firebaseAuth, currentUser => {
      setUser(currentUser);
      setLoading(false);
    });
  }, []);

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
    }),
    [user, loading],
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
```

### After state — replace the entire file with

```typescript
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

  // Start/stop timers based on auth state
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

  // Reset timer on any user activity (only while logged in)
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

  // Clean up timers on unmount
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
```

### Acceptance criteria

1. `npx tsc --noEmit` (run from `frontend/`) produces no new TypeScript errors related to
   `AuthContext.tsx`.
2. The file exports `AuthProvider` and `useAuth` (unchanged names — existing callers still compile).
3. `AuthContextValue` now has `sessionWarning: boolean` and `extendSession: () => void` in addition
   to the original three fields.
4. The import line for `firebase/auth` now includes `signOut` alongside `onAuthStateChanged` and
   `type User`.
5. The import line from `react` now includes `useCallback`, `useRef` alongside the original imports.
6. `SESSION_TIMEOUT_MS` defaults to `30 * 60 * 1000` (1 800 000) when `VITE_SESSION_TIMEOUT_MS`
   is not set.
7. `SESSION_WARNING_MS` equals `SESSION_TIMEOUT_MS - 2 * 60 * 1000`.
8. `ACTIVITY_EVENTS` contains exactly: `'mousemove'`, `'mousedown'`, `'keydown'`, `'touchstart'`,
   `'scroll'`.

---

## Task 2 — Create `SessionTimeoutWarning.tsx` component

**Purpose:** New component that renders a visible banner when `sessionWarning` is `true`, with a
"Stay logged in" button that calls `extendSession()`. Returns `null` when `sessionWarning` is
`false` (no DOM overhead). Depends on Task 1 because it consumes `sessionWarning` and
`extendSession` from the updated context.

### Files

- `frontend/src/auth/SessionTimeoutWarning.tsx` — **new file** (placed alongside `AuthContext.tsx`
  and `SignOutButton.tsx` in the `auth/` directory)

### Create this file with the following content

```typescript
import { useAuth } from './AuthContext';

export default function SessionTimeoutWarning() {
  const { sessionWarning, extendSession } = useAuth();

  if (!sessionWarning) return null;

  return (
    <div className="session-warning-banner" role="alert" aria-live="assertive">
      <span>Your session will expire in 2 minutes due to inactivity.</span>
      <button type="button" onClick={extendSession}>
        Stay logged in
      </button>
    </div>
  );
}
```

### Notes on placement

The file lives at `frontend/src/auth/SessionTimeoutWarning.tsx` — the same directory as
`AuthContext.tsx`. This keeps auth-related files together and matches the existing pattern
(`SignOutButton.tsx` also lives in `frontend/src/auth/`).

Do NOT add it to `frontend/src/components/index.ts`. The component is auth-specific and imported
directly by `AuthLayout.tsx` in Task 3.

Styling (`session-warning-banner` class) is left to the implementer. A fixed top/bottom banner or
a modal are both acceptable. The class name is the hook for CSS — add styles to an existing CSS
file or a new `SessionTimeoutWarning.css` co-located in `frontend/src/auth/`.

### Acceptance criteria

1. File exists at `frontend/src/auth/SessionTimeoutWarning.tsx`.
2. `npx tsc --noEmit` (from `frontend/`) produces no errors involving this file.
3. The component imports `useAuth` from `'./AuthContext'` (relative, not absolute).
4. When `sessionWarning` is `false`, the component returns `null` — no DOM element is rendered.
5. The rendered `<div>` has `role="alert"` and `aria-live="assertive"`.
6. The `<button>` has `type="button"` and its `onClick` is `extendSession`.
7. The button label is exactly: `Stay logged in`.

---

## Task 3 — Add `<SessionTimeoutWarning />` to `AuthLayout.tsx`

**Purpose:** Make the warning banner visible across all authenticated routes by rendering it inside
`AuthLayout`, which already wraps the authenticated subtree in `App.tsx`. Depends on Task 2.

### Files

- `frontend/src/components/AuthLayout.tsx` — add import and one JSX element

### Current state (`frontend/src/components/AuthLayout.tsx`, lines 1–11)

```typescript
import { Outlet } from 'react-router-dom';
import NavBar from './NavBar';

export default function AuthLayout() {
  return (
    <>
      <NavBar />
      <Outlet />
    </>
  );
}
```

### Changes

1. Add an import for `SessionTimeoutWarning`:

```typescript
import SessionTimeoutWarning from '../auth/SessionTimeoutWarning';
```

2. Add `<SessionTimeoutWarning />` inside the JSX fragment, between `<NavBar />` and `<Outlet />`:

```typescript
export default function AuthLayout() {
  return (
    <>
      <NavBar />
      <SessionTimeoutWarning />
      <Outlet />
    </>
  );
}
```

### Full after state

```typescript
import { Outlet } from 'react-router-dom';
import NavBar from './NavBar';
import SessionTimeoutWarning from '../auth/SessionTimeoutWarning';

export default function AuthLayout() {
  return (
    <>
      <NavBar />
      <SessionTimeoutWarning />
      <Outlet />
    </>
  );
}
```

### Acceptance criteria

1. `npx tsc --noEmit` (from `frontend/`) produces no errors involving `AuthLayout.tsx`.
2. The file imports `SessionTimeoutWarning` from `'../auth/SessionTimeoutWarning'`.
3. `<SessionTimeoutWarning />` appears in the JSX between `<NavBar />` and `<Outlet />`.
4. No other lines in the file change.
5. The `components/index.ts` barrel is NOT changed — `SessionTimeoutWarning` is not added there.

---

## Task 4 — Add unit tests for session timeout logic

**Purpose:** Verify timer lifecycle, `signOut` call timing, and `sessionWarning` state transitions
using Vitest fake timers. Depends on Task 1 (the updated `AuthContext.tsx`).

### Files

- `frontend/src/tests/auth/AuthContext.test.tsx` — **new file** (create the `auth/` subdirectory
  under `frontend/src/tests/` if it does not already exist)

### Create this file with the following content

```typescript
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
    // Advance 20 min — no signOut yet
    await act(async () => {
      vi.advanceTimersByTime(20 * 60 * 1000);
    });
    // User activity resets the 30-min clock
    document.dispatchEvent(new Event('mousemove'));
    // Advance another 20 min (total 40 min, but only 20 min since last activity)
    await act(async () => {
      vi.advanceTimersByTime(20 * 60 * 1000);
    });
    expect(signOut).not.toHaveBeenCalled();
    // Advance the remaining 10 min + 1 ms to cross the 30-min mark from last activity
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

    // Trigger warning
    await act(async () => {
      vi.advanceTimersByTime(28 * 60 * 1000 + 1);
    });
    expect(capturedWarning).toBe(true);

    // Extend session
    await act(async () => {
      capturedExtend?.();
    });
    expect(capturedWarning).toBe(false);
  });
});
```

### Notes on test directory structure

The existing test tree is:
```
frontend/src/tests/
  api/
  components/
  pages/
  utils/
```

There is no `auth/` subdirectory yet. Create it and place `AuthContext.test.tsx` inside it. This
follows the same `tests/<category>/` pattern used for `tests/components/`, `tests/api/`, etc.

### Acceptance criteria

1. File exists at `frontend/src/tests/auth/AuthContext.test.tsx`.
2. `npx vitest run src/tests/auth/AuthContext.test.tsx` (from `frontend/`) exits 0 with all 4
   tests passing.
3. The test for "calls signOut after SESSION_TIMEOUT_MS" passes without modifying
   `SESSION_TIMEOUT_MS` in the source — `vi.advanceTimersByTime(30 * 60 * 1000 + 1)` is the
   trigger.
4. The test for "resets timer on activity" dispatches a real DOM event
   (`document.dispatchEvent(new Event('mousemove'))`) and verifies `signOut` is NOT called at the
   original 30-min mark but IS called 30 min after the event.
5. The `sessionWarning` tests use a child component spy pattern (not
   `renderHook`) to read context state — consistent with the existing test pattern in this project.
6. `vi.clearAllMocks()` is called in `afterEach` so tests do not bleed into each other.

---

## Summary of what requires you (not a dev agent)

These are the GCP Console manual steps from §8 of the PRD. They cannot be automated and require a
human with GCP Console access to project `juno-medical-clarity`.

**Step 1 — Enable Identity Platform (the upgrade)**

- GCP Console > APIs & Services > Library > search "Identity Platform API" > Enable.
- Alternatively: GCP Console > Identity Platform > click "Upgrade" if shown.
- This is in-place and non-destructive. All existing Firebase Auth users, UIDs, and credentials
  are automatically preserved. No migration script is needed.

**Step 2 — Verify existing users post-upgrade**

- GCP Console > Identity Platform > Users tab.
- Confirm existing clinician accounts appear.
- Log in to the Juno app with a test account and confirm the login succeeds (no browser console
  errors).

**Step 3 — Execute (or verify) the HIPAA BAA with Google**

- GCP Console > IAM & Admin > Data Protection > HIPAA.
- If SP-09 has already executed the BAA for this GCP project, this step is verify-only.
- If not yet signed, follow the prompts to sign it for project `juno-medical-clarity`.
- The BAA is per-GCP-project and needs to be signed only once — coordinate with SP-09 to avoid
  duplicate submissions.

**Step 4 — Verify Cloud Run service account permissions**

- GCP Console > IAM & Admin > IAM.
- Filter by the Cloud Run service account used by the backend (the account referenced in
  `FIREBASE_SERVICE_ACCOUNT_JSON`).
- Confirm it has at minimum `roles/firebase.admin` or `roles/identityplatform.admin`.
- If missing, add the appropriate role.

**Step 5 (optional) — Review Identity Platform advanced settings**

- GCP Console > Identity Platform > Settings.
- Not required for this SP, but relevant for future MFA enforcement.

**Post-upgrade smoke test (can be delegated to a dev)**

1. Log in to the Juno app with a known clinician account. Confirm login succeeds.
2. Make any authenticated API call (e.g. load saved outputs list). Confirm a 200 response, not 401.
   This verifies `firebase_admin.auth.verify_id_token()` is compatible with Identity Platform
   tokens.
