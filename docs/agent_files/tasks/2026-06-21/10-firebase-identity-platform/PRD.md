# PRD: Firebase Identity Platform Upgrade & Session Inactivity Timeout (SP-10)

Sub-project 10 of the Juno HIPAA compliance initiative. It has two independent parts: Part A is
primarily a GCP Console operation that brings user authentication under Google's HIPAA BAA; Part B
is a pure frontend code change that enforces HIPAA §164.312(a)(2)(ii) automatic session logoff.
Neither part requires backend code changes.

---

## 1. Problem

**Part A — Firebase Auth is not covered by Google's HIPAA BAA.**

Juno uses Firebase Authentication (`firebase/auth`) to authenticate clinicians. Firebase Auth is
NOT listed on Google's HIPAA covered services. Any PHI that flows through (or relies on) a
non-covered service breaks HIPAA compliance. Google Cloud Identity Platform is the HIPAA-covered
equivalent — it is the same underlying technology and the same client SDK, but surfaced under the
GCP project and explicitly included in Google's HIPAA Business Associate Agreement.

**Part B — No automatic session logoff.**

HIPAA §164.312(a)(2)(ii) (Technical Safeguard — Automatic Logoff) requires that sessions
terminate after a period of inactivity. Juno's current `AuthContext.tsx` sets up an
`onAuthStateChanged` listener but has no inactivity timer: a clinician who walks away from a
logged-in browser window can access PHI indefinitely.

---

## 2. Goals

1. **[Part A]** Upgrade Firebase Auth to Google Cloud Identity Platform for GCP project
   `juno-medical-clarity` so that user authentication is covered under Google's HIPAA BAA.
2. **[Part A]** Confirm `authDomain` config and backend `firebase_admin` compatibility with
   Identity Platform — document any code changes needed.
3. **[Part B]** Implement automatic session logoff after 30 minutes of user inactivity, meeting
   HIPAA §164.312(a)(2)(ii).
4. **[Part B]** Show a warning to the clinician 2 minutes before the session expires so they can
   extend it without losing work.

---

## 3. Non-Goals

- **MFA enforcement** — deferred to a later SP. Identity Platform supports MFA; enabling it is a
  separate policy decision.
- **Firebase Analytics removal** — Firebase Analytics (`VITE_FIREBASE_MEASUREMENT_ID`) is not on
  the HIPAA covered list either, but removing it is out of scope for this SP and tracked
  separately. No PHI flows through analytics events in Juno today.
- **Firebase Hosting migration** — Juno's frontend is currently served via Firebase Hosting
  (`firebaseapp.com` domain). Migrating to Cloud Run or another HIPAA-covered host is a P4 item
  tracked in a separate future SP.
- **Backend code changes** — `firebase_admin` SDK continues to work with Identity Platform
  unchanged (same token format, same Admin SDK API). No backend file edits are required.
- **Custom auth domain** — Setting up a custom `authDomain` (e.g. `auth.juno.example.com`) is
  not required by this SP. The default Identity Platform domain is HIPAA-covered.
- **Session persistence changes** — Firebase's default `browserLocalPersistence` (tokens survive
  page refresh) is acceptable. Only inactivity logoff is in scope; forced re-login on every page
  load is not required.

---

## 4. Architecture Decisions

### 4.1 Part A — Identity Platform Upgrade: Code vs. Console

**What is a GCP Console-only operation (no code change):**

- Enabling Identity Platform on project `juno-medical-clarity` (GCP Console > Identity Platform >
  Enable). This is an in-place upgrade; all existing Firebase Auth users are automatically
  preserved in the same underlying user store. No user migration script is needed.
- Verifying existing users are accessible post-upgrade (GCP Console > Identity Platform > Users).
- Executing the HIPAA BAA with Google (GCP Console > IAM & Admin > Data Protection > HIPAA BAA).
- Verifying the Cloud Run service account has `roles/identityplatform.admin` or equivalent.

**What changes in code — `authDomain`:**

The current `authDomain` in `.env.production` is:
```
VITE_FIREBASE_AUTH_DOMAIN=juno-medical-clarity.firebaseapp.com
```

After enabling Identity Platform, the Firebase JS SDK (`firebase/auth`) continues to work with the
existing `firebaseapp.com` authDomain. Identity Platform does not require a different authDomain
value. **No change to `VITE_FIREBASE_AUTH_DOMAIN` is needed** (see §9.1 for resolution of this
open question).

**What stays the same in `frontend/src/api/firebase.ts`:**

No code changes are required. The `initializeApp` + `getAuth` pattern works identically against
Identity Platform because the client SDK is shared:

```typescript
// frontend/src/api/firebase.ts — NO CHANGES NEEDED
import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string,  // unchanged
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET as string,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID as string,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string,
};

export const firebaseApp = initializeApp(firebaseConfig);
export const firebaseAuth = getAuth(firebaseApp);
export const API_URL = import.meta.env.VITE_API_PROCESSING_URL as string;
```

**What stays the same in `backend/utils/firebase.py`:**

The backend uses `firebase_admin.auth.verify_id_token(token)` to validate JWTs sent by the
frontend. Identity Platform issues the same JWT format as Firebase Auth (RS256, same JWKS endpoint
at `https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com`).
The `firebase_admin` SDK is Identity Platform-compatible without any change. No edits to
`backend/utils/firebase.py` are required.

**Summary — Part A code changes:**

| File | Change |
|---|---|
| `frontend/src/api/firebase.ts` | None |
| `frontend/.env.production` | None |
| `backend/utils/firebase.py` | None |
| GCP Console | Enable Identity Platform (manual step — see §8) |

---

### 4.2 Part B — Session Inactivity Timeout in `AuthContext.tsx`

**Approach:** Track user activity via `document`-level event listeners (`mousemove`, `mousedown`,
`keydown`, `touchstart`, `scroll`). Use a single `setTimeout` reference stored in a `useRef`. On
any activity event, clear and restart the timeout. When the timeout fires at 30 minutes, call
`signOut(firebaseAuth)`. Show a warning toast/banner at 28 minutes (2 minutes before logoff) so
the user can click to reset the timer.

**Constants (at the top of `AuthContext.tsx`):**

```typescript
const SESSION_TIMEOUT_MS =
  Number(import.meta.env.VITE_SESSION_TIMEOUT_MS) || 30 * 60 * 1000; // 30 minutes
const SESSION_WARNING_MS = SESSION_TIMEOUT_MS - 2 * 60 * 1000;        // 28 minutes
```

`VITE_SESSION_TIMEOUT_MS` is optional; if absent, defaults to 1 800 000 ms. Do not add it to
`.env.production` for now — the default is the production value. It can be set to a small value
(e.g. `10000`) in `.env.development.local` for local testing.

**Updated `AuthContext.tsx` — complete after-state:**

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
  sessionWarning: boolean;        // true when < 2 min remain; consumers render a banner
  extendSession: () => void;      // call to reset the timer from the warning UI
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

**What changed vs. the current file:**

| Addition | Purpose |
|---|---|
| `signOut` import from `firebase/auth` | Called by the logout timer |
| `useCallback`, `useRef` imports | Timer management |
| `SESSION_TIMEOUT_MS`, `SESSION_WARNING_MS` constants | Configurable durations |
| `ACTIVITY_EVENTS` constant | Event names to listen for |
| `sessionWarning: boolean` in `AuthContextValue` | Exposed so the app can render a warning banner |
| `extendSession: () => void` in `AuthContextValue` | Called from the warning banner's "Stay logged in" button |
| `logoutTimerRef`, `warningTimerRef` refs | Hold `setTimeout` handles |
| `clearTimers`, `resetTimers` callbacks | Timer lifecycle management |
| `extendSession` callback | Delegates to `resetTimers` |
| Activity event listener `useEffect` | Attaches/detaches on `user` change |
| Cleanup `useEffect` | Clears timers on unmount |

**Warning banner — new component `SessionTimeoutWarning.tsx`:**

Create `frontend/src/auth/SessionTimeoutWarning.tsx`:

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

Render `<SessionTimeoutWarning />` inside the authenticated layout so it is visible across all
protected pages. The exact placement is inside whatever component wraps authenticated routes (e.g.
`AuthLayout.tsx` or the authenticated branch of `App.tsx`). Styling is left to the implementer
(a fixed top/bottom banner or a modal are both acceptable; the class name
`session-warning-banner` is the hook for CSS).

**`AuthLayout.tsx` integration (if that is the auth wrapper):**

```typescript
// Add to the authenticated subtree render — exact location TBD by implementer
import SessionTimeoutWarning from './SessionTimeoutWarning';

// Inside the JSX:
<SessionTimeoutWarning />
```

---

## 5. API Change Summary

No wire-protocol changes. The backend continues to receive `Authorization: Bearer <firebase-id-token>`
headers and validates them via `firebase_admin.auth.verify_id_token()`. Identity Platform issues
the same JWT format; the `firebase_admin` SDK is compatible without any change.

No new API endpoints. No changes to request/response shapes.

---

## 6. Frontend Change Summary

**Files changed:**

| File | Change |
|---|---|
| `frontend/src/auth/AuthContext.tsx` | Add session timeout logic — see §4.2 full before/after |
| `frontend/src/auth/SessionTimeoutWarning.tsx` | **New file** — warning banner component |
| `frontend/src/auth/AuthLayout.tsx` (or equivalent) | Add `<SessionTimeoutWarning />` to authenticated layout |

**Files NOT changed:**

| File | Reason |
|---|---|
| `frontend/src/api/firebase.ts` | Identity Platform is SDK-transparent; no change needed |
| `frontend/.env.production` | `authDomain` stays `juno-medical-clarity.firebaseapp.com` |
| `frontend/src/pages/LoginPage.tsx` | `signInWithEmailAndPassword` unchanged |
| `frontend/src/auth/SignOutButton.tsx` | `signOut(firebaseAuth)` unchanged |
| `frontend/src/api/apiClient.ts` | `getIdToken()` call unchanged |
| All backend files | No backend changes in scope |

**Session timeout UX flow:**

1. User logs in. Timers start: warning at T+28 min, logout at T+30 min.
2. Any `mousemove`, `mousedown`, `keydown`, `touchstart`, or `scroll` event resets both timers.
3. At T+28 min of inactivity: `sessionWarning` becomes `true`. `SessionTimeoutWarning` banner
   renders with a "Stay logged in" button.
4. User clicks "Stay logged in": `extendSession()` clears both timers and restarts from T+30 min.
   `sessionWarning` becomes `false`. Banner disappears.
5. If user ignores the warning until T+30 min: `signOut(firebaseAuth)` is called. Firebase clears
   the local auth state. `onAuthStateChanged` fires with `null`. The app's existing auth guard
   redirects to the login page. Banner disappears (user is no longer authenticated).

**New env var (optional, dev only):**

```
VITE_SESSION_TIMEOUT_MS=10000   # 10 seconds — for local testing only
```

Do not set this in `.env.production`. If absent, the constant defaults to 1 800 000 ms (30 min).

---

## 7. Testing

### 7.1 Verifying Identity Platform is Active (Part A)

1. **GCP Console check:** After enabling Identity Platform, navigate to
   GCP Console > Identity Platform. The page should list existing Firebase Auth users and show
   "Identity Platform is enabled" for project `juno-medical-clarity`. This confirms the upgrade
   is complete.
2. **Existing user login test:** Log in to the Juno app with a known clinician account. Confirm
   the login succeeds — no SDK errors in the browser console. This verifies the `authDomain` and
   `apiKey` configuration still work post-upgrade.
3. **Backend token validation:** After logging in, confirm the backend can validate the token by
   making any authenticated API call (e.g. load the saved outputs list) and receiving a 200, not a
   401. This verifies `firebase_admin.auth.verify_id_token()` is compatible with Identity Platform
   tokens.
4. **GCP IAM check:** Confirm the Cloud Run service account (used by the backend) has the
   `Firebase Authentication Admin` or `Identity Platform Admin` role in IAM. Check via
   GCP Console > IAM & Admin > IAM, filter by the service account email.

### 7.2 Testing Session Timeout (Part B)

**Unit tests (add to `frontend/src/tests/auth/AuthContext.test.tsx`):**

- Verify that after `SESSION_TIMEOUT_MS` ms of no activity events, `signOut` is called.
  Use `vi.useFakeTimers()` and `vi.advanceTimersByTime()`.
- Verify that an activity event before `SESSION_TIMEOUT_MS` resets the timer (signOut is NOT
  called at T+SESSION_TIMEOUT_MS but IS called at T+SESSION_TIMEOUT_MS after the last event).
- Verify `sessionWarning` becomes `true` at `SESSION_WARNING_MS` and `false` after `extendSession`.

**Example test skeleton:**

```typescript
import { render, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { AuthProvider, useAuth } from '../../auth/AuthContext';

vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
}));

vi.mock('firebase/auth', () => ({
  onAuthStateChanged: vi.fn((auth, cb) => { cb({ uid: 'test' }); return () => {}; }),
  signOut: vi.fn(),
}));

describe('session timeout', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('calls signOut after SESSION_TIMEOUT_MS with no activity', async () => {
    const { signOut } = await import('firebase/auth');
    render(<AuthProvider><div /></AuthProvider>);
    await act(async () => { vi.advanceTimersByTime(30 * 60 * 1000 + 1); });
    expect(signOut).toHaveBeenCalledOnce();
  });

  it('resets timer on activity and does not sign out early', async () => {
    const { signOut } = await import('firebase/auth');
    render(<AuthProvider><div /></AuthProvider>);
    await act(async () => { vi.advanceTimersByTime(20 * 60 * 1000); });
    document.dispatchEvent(new Event('mousemove'));
    await act(async () => { vi.advanceTimersByTime(20 * 60 * 1000); });
    expect(signOut).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(10 * 60 * 1000 + 1); });
    expect(signOut).toHaveBeenCalledOnce();
  });
});
```

**Manual testing with short timeout:**

1. Set `VITE_SESSION_TIMEOUT_MS=15000` in `.env.development.local` (15 seconds).
2. Log in. Do nothing for 13 seconds — the warning banner should appear.
3. Wait 2 more seconds — app should sign out and redirect to login.
4. Log in again. Move mouse repeatedly. Confirm sign-out does NOT occur at 15 seconds (timer resets).
5. Log in, click "Stay logged in" when banner appears. Confirm banner dismisses and timer resets.

---

## 8. Manual Intervention Required From You

The following steps **cannot be automated** by a dev agent and must be performed by a human with
GCP Console access to project `juno-medical-clarity`.

**Step 1 — Enable Identity Platform (the upgrade):**
GCP Console > APIs & Services > Library > search "Identity Platform API" > Enable.
Alternatively: GCP Console > Identity Platform > click "Upgrade" if shown.
This is an in-place, non-destructive upgrade. Existing Firebase Auth users are automatically
accessible in Identity Platform. No user migration script is needed.

**Step 2 — Verify existing users post-upgrade:**
GCP Console > Identity Platform > Users tab. Confirm existing clinician accounts appear. Log in
with a test account in the Juno app to confirm end-to-end auth still works.

**Step 3 — Execute (or verify) the HIPAA BAA with Google:**
GCP Console > IAM & Admin > Data Protection > HIPAA. If a BAA is not yet signed, follow the
prompts to sign it for GCP project `juno-medical-clarity`. Note: SP-09 also references this step
— coordinate with SP-09 to avoid duplicate submissions. A BAA is per-GCP-project; signing once
covers all HIPAA-covered services on that project.

**Step 4 — Verify Cloud Run service account permissions:**
GCP Console > IAM & Admin > IAM > filter by the Cloud Run service account used by the backend
(`firebase-service-account` or the account in `FIREBASE_SERVICE_ACCOUNT_JSON`). Confirm it has
at minimum `roles/firebase.admin` or `roles/identityplatform.admin`. If not, add the appropriate
role.

**Step 5 (optional) — Review Identity Platform advanced settings:**
GCP Console > Identity Platform > Settings. Optionally configure session cookie policies, custom
domains, or blocking functions. These are not required for HIPAA compliance but may be relevant
to future MFA enforcement (next SP).

---

## 9. Open Questions & Decisions

**Q1: Does `authDomain` need to change after enabling Identity Platform?**
[RESOLVED: No change needed.] The Firebase JS client SDK uses `authDomain` only for the OAuth
redirect/popup flow. Juno uses `signInWithEmailAndPassword`, which communicates directly with
`https://identitytoolkit.googleapis.com` (the Identity Platform REST API endpoint), not the
`authDomain`. Identity Platform and Firebase Auth share the same `identitytoolkit.googleapis.com`
endpoint. Therefore `juno-medical-clarity.firebaseapp.com` continues to work as `authDomain`
after the upgrade; no env var change is needed.

**Q2: Does `firebase_admin.auth.verify_id_token()` work with Identity Platform tokens?**
[RESOLVED: Yes, no change needed.] Identity Platform issues Firebase JWTs with the same signing
keys (`securetoken@system.gserviceaccount.com`) and the same claim structure (`iss`, `aud`, `sub`,
`uid`, etc.) as Firebase Auth. The `firebase_admin` Python SDK verifies tokens against those same
keys and is fully compatible. No backend code changes are required.

**Q3: Are existing users automatically migrated to Identity Platform?**
[RESOLVED: Yes, automatically.] Enabling Identity Platform is an upgrade on the same underlying
Google user store — existing Firebase Auth users, UIDs, and credentials are preserved without any
migration step. Verify post-upgrade via GCP Console as described in §8 Step 2.

**Q4: Should the activity debounce rate be limited to avoid excessive timer resets?**
[RESOLVED: No debounce needed.] `clearTimeout` + `setTimeout` is O(1) and costs nothing
meaningful. `mousemove` fires at up to 60fps but calling `clearTimeout` on every event is safe.
Adding a debounce wrapper adds complexity without meaningful gain. Keep the implementation simple:
reset on every event.

**Q5: What happens if the user has the app open in two browser tabs?**
[RESOLVED: Each tab manages its own timer independently.] Firebase's `onAuthStateChanged` is
per-tab. If one tab signs out (due to inactivity), the other tab's `onAuthStateChanged` will fire
with `null` (Firebase propagates sign-out across tabs via `localStorage`). This means the user
will also be redirected to login in the other tab. This is the correct HIPAA behavior and requires
no special handling.

**Q6: Should `VITE_SESSION_TIMEOUT_MS` be added to `.env.production`?**
[RESOLVED: No.] The constant defaults to 30 minutes when the env var is absent. Adding it
explicitly to `.env.production` would expose the timeout value in version control and provide no
benefit. Developers can override it in `.env.development.local` for testing. If the timeout value
ever needs to change, the constant in `AuthContext.tsx` is the single source of truth.

**Q7: Should Firebase Hosting be migrated as part of this SP to avoid `firebaseapp.com` serving
the app under a non-HIPAA-covered service?**
[DEFERRED to a future SP.] Firebase Hosting is not a channel through which PHI flows — it serves
only static JS/CSS assets. PHI flows through the backend API on Cloud Run, which is HIPAA-covered.
The authentication credential (the Firebase JWT) originates on the Identity Platform endpoint, not
the hosting domain. The risk of leaving Hosting on Firebase is assessed as low; migration is
tracked as a separate P4 item.

**Q8: Does SP-09 HIPAA BAA execution need to be coordinated with Part A of this SP?**
[RESOLVED: Coordinate timing.] SP-09 and this SP both reference executing the HIPAA BAA. The BAA
is a single document per GCP project — it needs to be signed only once. Whoever completes their
SP first should sign the BAA; the other SP's §8 step becomes a verify-only step. Do not sign the
BAA twice.
