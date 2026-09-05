# PRD: SP3 — Trial Frontend App
**Sub-project:** SP3
**Branch context:** users/tejitpabari/trial-app
**Date:** 2026-09-04
**Status:** Draft
**Dependencies:** SP2 (API contract); coordinates with SP4 (hosting target, legal pages)
---

## 1. Problem

Juno's only frontend today, `frontend/`, is a single Vite/React app that requires a
logged-in Firebase user for every screen (`App.tsx`'s `if (!user && !isCarePlanRoute)
return <LoginPage />`), carries the full app's navbar/sidebar chrome, dataset/Athena preset
UI, grading toggles, and admin surface, and ships Firebase config plus the entire app
bundle to any visitor. None of that is appropriate for a public, no-login "try it now"
page that a stranger can reach with no account and no explanation of the rest of the
product.

Per **D3 (locked, brainstorm.md)**, the trial gets its own Vite build,
`frontend-trial/`, sharing exactly four things with the main app via a path alias —
`CarePlanView`, `MedicalTerm`, `buildPdfHtml`, and the `types/` module — and nothing else.
Everything else (routing, auth, Firestore subscription, file validation, the three
screens, analytics, legal pages) is net-new, small, and trial-owned.

This PRD designs that new app end-to-end: exact file tree, build config, the anonymous-
auth wiring, the `upload → processing → result` state machine, GA4 instrumentation that
structurally cannot leak document content, the "download report" mechanism (reused as-is
from the main app), and the best-effort `DELETE /trial/jobs/<id>` cleanup call that is the
user-visible half of the "no data is saved" promise (SP2 owns the other half —
server-side retention).

Three things were verified directly against the current repo before writing this design
(cited throughout §4):
- `CarePlanView.tsx`'s entire transitive import graph is auth-free, router-free, and
  app-global-state-free (only React, `MedicalTerm.tsx`, and two `types/` files — confirmed
  by reading both files in full).
- `buildPdfHtml.ts` is a pure function with one type-only import — directly reusable.
- Neither `useJobSnapshot.ts` nor `api/firebase.ts` is on D3's shared list, and reading
  both confirms why: `useJobSnapshot.ts`'s auth-state-resubscription dance and
  `AuthContext.tsx`'s 30-minute inactivity auto-sign-out are both designed for named,
  logged-in users switching accounts — wrong behavior for an anonymous trial session that
  signs in once and never signs out. SP3 writes small, trial-owned equivalents instead of
  aliasing these two files (§4.6, §4.8).

---

## 2. Goals

1. A new `frontend-trial/` Vite app, `npm run build`-able and `npm run dev`-able
   independently of `frontend/`, sharing exactly the four files/dirs D3 names via a path
   alias, with a documented, verified (or honestly flagged) story for how `tsc -b`
   type-checks across that alias boundary.
2. Three screens — upload, processing, result — implementing the exact product scope in
   the task brief (file upload + paste-text, 5-file cap, no presets, no grading toggle,
   one "Simplify" button; live pipeline steps; title + date + body + before→after score +
   one "Download report" button, with every explicitly-excluded main-app feature actually
   absent).
3. Invisible anonymous Firebase Auth wiring (D1) — the user never sees a sign-in screen;
   the app signs in anonymously on load and gates submission on having a uid.
4. A Firestore `onSnapshot` subscription to `care_plan_outputs/{jobId}` (SP2 §5 — there is
   no `GET` endpoint) driving the live pipeline-step display and the result render.
5. GA4 instrumentation (D10) via a closed, typed event wrapper that makes sending document
   content structurally hard, not just procedurally forbidden.
6. A best-effort, multi-layered `DELETE /trial/jobs/<id>` firing strategy covering the
   "reached results," "closed the tab mid-processing," and "backgrounded the app on
   mobile" cases, given `sendBeacon` cannot carry the required `Authorization` header.
7. `/privacy` and `/terms` routes and a persistent `Footer` component per SP4's contract
   (§6.1 of SP4's PRD), so the two initiatives plug together without either side guessing
   at the other's route names or env var names.
8. A full test list using the same vitest + testing-library conventions `frontend/`
   already uses, including a smoke test whose specific purpose is to catch a silent alias
   break.

---

## 3. Non-Goals

- **No backend changes.** SP3 codes directly against SP2's §5 contract; no route, model,
  or Firestore schema change originates here.
- **No changes to `frontend/`.** Every file this PRD touches is new, under
  `frontend-trial/`. The only two files it *reads* from `frontend/src` are consumed via a
  read-only path alias, never edited.
- **No Hosting config, CI deploy job, CORS list, or legal-copy authorship.** SP4 owns
  `firebase.json`/`.firebaserc`, the `deploy.yml` build/deploy steps, `backend/app.py`'s
  CORS origins, and the Privacy/Terms *text*. SP3 only needs `/privacy` and `/terms`
  routes to exist as a place for SP4's copy to render into (§4.16) — this PRD does not
  duplicate SP4's draft text.
- **No preset datasets, dataset/Athena UI, grading toggle, sharing, notes, saved-outputs
  sidebar, admin surface, or navbar chrome.** Explicitly excluded by the product brief;
  none of it is built, not even behind a flag.
- **No "Show Original" viewer, session ID, trace ID, "Another care plan" button (on the
  success view), score breakdown, or Download JSON.** Explicitly excluded (§9 has one
  narrow, flagged exception for a "Try again" button on the *error* sub-view — not the
  same as the excluded "Another care plan" button; see §9 Q6).
- **No cold-start masking UI (D7, locked).** The processing screen's copy is identical
  whether the wait is 2 seconds or 30 seconds.
- **No client-side image compression/resizing** (SP1's Q3, deferred there — not
  reopened here).
- **No shared cross-app constants module.** `ALLOWED_UPLOAD_EXTENSIONS` is hardcoded
  independently in `frontend-trial/` (SP1's own Q4 already deferred creating a shared
  `frontend/src/constants.ts` entry for this; SP3 doesn't reopen it, see §9 Q1).

---

## 4. Architecture Decisions

### 4.1 Exact file tree

```
frontend-trial/
├── package.json
├── package-lock.json                  (generated by npm install)
├── tsconfig.json
├── tsconfig.app.json
├── tsconfig.node.json
├── vite.config.ts
├── vitest.setup.ts
├── eslint.config.js
├── index.html
├── .env.example
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── App.css                        (base layout, imports shared CSS — §4.17)
    ├── api/
    │   ├── firebase.ts                 (own init — §4.6, deliberately NOT aliased)
    │   └── trialApi.ts                 (createTrialJob, deleteTrialJob — §4.7)
    ├── analytics/
    │   └── ga.ts                       (typed GA4 wrapper + event table — §4.15)
    ├── hooks/
    │   ├── useAnonAuth.ts              (§4.6)
    │   ├── useTrialJobSnapshot.ts      (§4.8)
    │   └── useUnloadCleanup.ts         (§4.13)
    ├── utils/
    │   ├── validateFiles.ts            (§4.10)
    │   └── downloadReport.ts           (§4.12, wraps aliased buildPdfHtml)
    ├── components/
    │   ├── Footer.tsx                  (§4.16)
    │   ├── UploadScreen.tsx            (§4.11)
    │   ├── ProcessingScreen.tsx        (§4.11)
    │   └── ResultScreen.tsx            (§4.11)
    ├── pages/
    │   ├── TrialPage.tsx               (state machine orchestrator — §4.9)
    │   ├── PrivacyPage.tsx             (§4.16 — body TBD by SP4)
    │   └── TermsPage.tsx               (§4.16 — body TBD by SP4)
    └── tests/
        ├── utils/
        │   ├── validateFiles.test.ts
        │   ├── downloadReport.test.ts
        │   └── aliasSmoke.test.ts       (§4.4's regression guard)
        ├── hooks/
        │   ├── useAnonAuth.test.ts
        │   └── useTrialJobSnapshot.test.ts
        ├── components/
        │   ├── UploadScreen.test.tsx
        │   ├── ProcessingScreen.test.tsx
        │   ├── ResultScreen.test.tsx
        │   └── CarePlanViewAliasSmoke.test.tsx  (§4.4's regression guard)
        ├── api/
        │   └── trialApi.test.ts
        └── analytics/
            └── ga.test.ts
```

No `firebase.json`/`.firebaserc` in `frontend-trial/` — SP4's design puts the multi-target
Hosting config at the repo root (`/root/projects/juno/firebase.json`), with `public:
"frontend-trial/dist"` for the `trial` target. Nothing for SP3 to add there.

### 4.2 `package.json`

Mirrors `frontend/package.json` field-for-field (same dependency versions — no reason to
drift), renamed and with `react-router-dom` still present (needed for `/`, `/privacy`,
`/terms`):

```json
{
  "name": "simplify-trial",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "firebase": "^12.14.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "react-router-dom": "^6.30.3"
  },
  "devDependencies": {
    "@eslint/js": "^9.39.1",
    "@testing-library/jest-dom": "^6.9.1",
    "@testing-library/react": "^16.3.2",
    "@testing-library/user-event": "^14.6.1",
    "@types/react": "^19.2.7",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^5.1.1",
    "@vitest/coverage-v8": "^4.1.9",
    "eslint": "^9.39.1",
    "eslint-plugin-react-hooks": "^7.0.1",
    "eslint-plugin-react-refresh": "^0.4.24",
    "globals": "^16.5.0",
    "jsdom": "^29.1.1",
    "typescript": "~5.9.3",
    "typescript-eslint": "^8.48.0",
    "vite": "^7.3.1",
    "vitest": "^4.1.9"
  }
}
```

**Why a fully separate `package.json`/`node_modules`, not an npm workspace:** the repo has
no workspace root today (no `"workspaces"` field anywhere, confirmed); introducing one to
save one duplicated `devDependencies` block is a much larger structural change than this
PRD's scope and would ripple into `frontend/`'s own build/CI (its own `package-lock.json`,
its own `npm ci` step). Two independent `npm ci`s (already how SP4's `deploy.yml` design
treats it, §4.3 of that PRD) is the additive, zero-blast-radius choice.

### 4.3 `vite.config.ts` — the alias, the dev port, and `server.fs.allow`

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // D3's shared surface: CarePlanView, MedicalTerm (its dependency),
      // buildPdfHtml, and types/. Nothing else in ../frontend/src should be
      // imported through this alias — see §4.4 for why the boundary is
      // enforced by convention (code review), not by tooling.
      '@main': path.resolve(__dirname, '../frontend/src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
    },
  },
  server: {
    port: 5174,        // pinned, not left to Vite's auto-increment — SP4's CORS
    strictPort: true,   // list (backend/app.py) hard-codes localhost:5174 for this
                        // dev server; strictPort makes a collision fail loudly
                        // instead of silently drifting to 5175 and breaking CORS.
    fs: {
      // Vite's default fs.allow is scoped near this project's own root. The
      // dev server must be able to read ../frontend/src (the @main alias
      // target) on every request during `npm run dev`, so widen it to the
      // repo root explicitly rather than relying on Vite's workspace-root
      // auto-detection (which looks for a package.json "workspaces" field or
      // a lockfile above this directory — neither exists here, so the
      // default would NOT automatically include ../frontend/src).
      allow: [path.resolve(__dirname, '..')],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
```

**Port 5174, confirmed against SP4's design:** SP4's PRD §5 already writes
`http://localhost:5174` into `backend/app.py`'s CORS allow-list as "frontend-trial/ dev
server — NEW" and flags to SP3 (its §9 Q6) that this should be pinned explicitly rather
than assumed. This PRD does that pinning; `strictPort: true` turns a silent port
mismatch into a loud dev-time failure instead of a confusing CORS error later.

### 4.4 `tsconfig` — the alias across the `tsc -b` boundary, verified reasoning and fallback

`tsconfig.app.json` mirrors `frontend/tsconfig.app.json` exactly, plus a `paths` entry:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true,
    "types": ["vite/client"],
    "baseUrl": ".",
    "paths": {
      "@main/*": ["../frontend/src/*"]
    }
  },
  "include": ["src"],
  "exclude": ["src/tests"]
}
```

`tsconfig.json` and `tsconfig.node.json` are byte-identical to `frontend/`'s (project
references to `tsconfig.app.json` + `tsconfig.node.json`; `tsconfig.node.json` only
type-checks `vite.config.ts`, untouched by the alias).

**Why this should work, verified as far as possible without a live build:**
- With `moduleResolution: "bundler"` + `paths`, TypeScript resolves `@main/components/
  CarePlanView` to `../frontend/src/components/CarePlanView.tsx` and then follows that
  file's own imports transitively — `MedicalTerm.tsx`, `types/carePlan.ts`,
  `types/envelope.ts` — adding them to the program automatically. TypeScript does not
  require an imported file to be inside the `include` glob; `include` only seeds the
  initial file set, and the import graph is followed regardless.
- The four shared files' own dependencies are, per the task brief's verified survey and
  this PRD's own re-read of them (§1), limited to `react` and `react-dom` (both already
  `frontend-trial/` dependencies) plus two type-only files with no runtime imports at
  all — nothing pulls in `react-router-dom`, `firebase/*`, or any auth/global-state
  module through this boundary.
- `noEmit: true` on both projects means TypeScript never needs to compute where a
  declaration file for an out-of-rootDir source would go — the usual class of
  cross-directory `tsc` errors (`TS6059`, "not under 'rootDir'") is an emit-time concern
  and does not fire in a type-check-only, `noEmit` build.

**What is NOT verified (no live build was run during this design pass) and must be the
implementer's first step, before writing any screen:** run `npm install && npm run build`
in a freshly scaffolded `frontend-trial/` containing only this config plus a placeholder
`App.tsx` that imports `CarePlanView` via `@main/components/CarePlanView`. If `tsc -b`
errors — the two most likely failure modes are a `rootDir`/composite-project complaint
from `-b`'s stricter cross-project rules, or ESLint's `tseslint` config not knowing about
the `paths` mapping (a separate, non-blocking concern — ESLint doesn't need to resolve
TS `paths` to lint, only `tsc` does) — the fallback is:

**Fallback: copy, don't alias.** Copy `CarePlanView.tsx`, `MedicalTerm.tsx`,
`buildPdfHtml.ts`, `types/carePlan.ts`, and `types/envelope.ts` verbatim into
`frontend-trial/src/shared/`, each with a one-line header comment (`// Copied from
frontend/src/... on <date> — see PRD.md §4.4 for why. Keep in sync manually.`) recording
the copy's origin and the fact that it does not update automatically. This accepts the
exact drift risk D3's own brainstorm entry flagged as the tradeoff of the "fully separate
duplicated app" alternative it rejected — but scoped to five small files instead of the
whole app, which is a materially smaller and more honest fallback than D3's rejected
alternative. This is called out again in §9 Q2 as an open risk, not silently assumed away.

### 4.5 `index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
      rel="stylesheet"
    />
    <title>Juno — Simplify Your Care Plan</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Same font stack as the main app (visual consistency — Inter, already loaded this way in
`frontend/index.html`), different `<title>` (no reason to share it, and the trial is a
different, standalone product surface).

**Search indexing: deliberately allowed.** Per §9 Q9 (resolved 2026-09-05), this
`index.html` carries no `<meta name="robots" content="noindex">` tag and the deploy adds
no `public/robots.txt` disallow rule — the user wants Juno discoverable organically via
search. Cost exposure from uncontrolled search traffic against a free, no-login AI
endpoint is bounded only by SP2's 5-requests-per-IP-per-hour limit and the Cloud Run
max-instances ceiling; revisit if costs climb.

`main.tsx` — deliberately **no `AuthProvider` wrapper** (that's `frontend/`'s
session-timeout auth context, wrong model for anonymous trial sessions — see §4.6):

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './App.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
```

### 4.6 Anonymous auth wiring — `api/firebase.ts` + `hooks/useAnonAuth.ts`

**`src/api/firebase.ts` — deliberately NOT aliased, a small duplicate of `frontend/src/
api/firebase.ts`:**

```ts
import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET as string,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID as string,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string,
};

export const firebaseApp = initializeApp(firebaseConfig);
export const firebaseAuth = getAuth(firebaseApp);
export const API_URL = import.meta.env.VITE_API_PROCESSING_URL as string;

const firestoreDatabaseId = import.meta.env.VITE_FIRESTORE_DATABASE_ID as string | undefined;
export const firebaseDb = firestoreDatabaseId
  ? getFirestore(firebaseApp, firestoreDatabaseId)
  : getFirestore(firebaseApp);
```

**Why copy instead of alias, when it's byte-identical today:** if this were aliased
(`@main/api/firebase`), the file's *own* relative imports would still resolve correctly
(it has none beyond `firebase/*` packages), so aliasing would actually work mechanically —
but doing so would blur exactly the boundary D3 draws. `api/firebase.ts` is not on D3's
shared list, and the one thing that would go wrong is `useJobSnapshot.ts` (also not
shared, §4.8) or any future main-app hook importing `../api/firebase` via a *relative*
path — if such a file were ever aliased in from `frontend-trial/`, that relative import
would silently resolve to `frontend/src/api/firebase.ts`, not `frontend-trial/src/api/
firebase.ts`, which is confusing and fragile exactly because it happens to work today by
coincidence (same Firebase project, same env var names — SP4's `deploy.yml` design passes
identical `VITE_FIREBASE_*` secrets to both builds). Keeping this file trial-owned
converts a "happens to work" situation into a "obviously and structurally correct"
one, for the cost of ~15 duplicated lines.

**`src/hooks/useAnonAuth.ts`:**

```ts
import { useEffect, useState, useCallback } from 'react';
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
```

Firebase Auth persists anonymous sessions in IndexedDB by default, so a returning visitor
within the same browser reuses the same anonymous uid across reloads (`onAuthStateChanged`
fires immediately with the cached user, no network round trip needed) — this is Firebase
SDK default behavior, not something SP3 configures. If `signInAnonymously` rejects (network
failure, or the Anonymous provider somehow disabled), `authState` becomes `'error'` and
the Upload screen shows a full-width banner with a **Retry** button wired to `retry()`
(§4.14, error UX table). The **Simplify** button is `disabled` whenever `authState !==
'ready'`, structurally preventing a submit attempt with no uid.

### 4.7 Trial API client — `api/trialApi.ts`

Mirrors `frontend/src/api/jobs.ts` + `api/apiClient.ts`'s shape, trimmed to only what the
trial needs (no batch jobs, no `doc_id`, no `version`/`grading_enabled` fields per SP2 §5
— sending them is harmless since the server silently ignores them, but the trial's own
client never constructs them, keeping its `FormData` payload minimal and honest about what
it actually uses):

```ts
import { firebaseAuth } from './firebase';
import { API_URL } from './firebase';
import { ApiError } from '@main/types/errors';
import type { ApiErrorResponse } from '@main/types/errors';

export interface CreateTrialJobResponse {
  job_id: string;
}

async function getAuthHeader(): Promise<Record<string, string>> {
  const user = firebaseAuth.currentUser;
  if (!user) {
    throw new Error('Not signed in yet — please wait a moment and try again.');
  }
  const token = await user.getIdToken();
  return { Authorization: `Bearer ${token}` };
}

export async function createTrialJob(formData: FormData): Promise<CreateTrialJobResponse> {
  const headers = await getAuthHeader();
  const res = await fetch(`${API_URL}/trial/jobs`, { method: 'POST', headers, body: formData });
  if (!res.ok) {
    let parsed: unknown;
    try { parsed = await res.json(); } catch { parsed = null; }
    if (parsed && typeof parsed === 'object' && (parsed as ApiErrorResponse).error) {
      const errBody = parsed as ApiErrorResponse;
      throw new ApiError(errBody.error, errBody.requestId ?? null);
    }
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Best-effort, fire-and-forget cleanup call — see §4.13 for when this is invoked
 * and why fetch(keepalive) is used instead of navigator.sendBeacon. */
export async function deleteTrialJob(jobId: string): Promise<void> {
  const user = firebaseAuth.currentUser;
  if (!user) return; // nothing we can authenticate the delete with; expires_at is the safety net
  const token = await user.getIdToken();
  await fetch(`${API_URL}/trial/jobs/${jobId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
    keepalive: true,
  });
}
```

`ApiError`/`ApiErrorResponse` come from `@main/types/errors` — a type-only-plus-one-class
import. `ApiError` itself has no runtime dependency beyond the `Error` builtin (confirmed
by re-reading `frontend/src/types/errors.ts` in full), so importing its concrete class
(not just its type) through the alias is safe and carries zero of the app-global-state risk
the alias boundary is meant to guard against.

### 4.8 `hooks/useTrialJobSnapshot.ts` — simpler than the main app's, deliberately

```ts
import { useEffect, useState } from 'react';
import { doc, onSnapshot } from 'firebase/firestore';
import { firebaseDb } from '../api/firebase';
import type { FirestoreJobError } from '@main/types/errors';

export type JobStatus = 'not_started' | 'processing' | 'completed' | 'error';

export interface TrialJobDoc {
  status: JobStatus;
  stage: number | null;
  output_data: Record<string, unknown> | null;
  error_data: FirestoreJobError | null;
  name: string;
}

export function useTrialJobSnapshot(jobId: string | null): {
  jobDoc: TrialJobDoc | null;
  loading: boolean;
  error: Error | null;
} {
  const [jobDoc, setJobDoc] = useState<TrialJobDoc | null>(null);
  const [loading, setLoading] = useState(jobId !== null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJobDoc(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);

    const unsubscribe = onSnapshot(
      doc(firebaseDb, 'care_plan_outputs', jobId),
      (snapshot) => {
        if (!snapshot.exists()) {
          setJobDoc(null);
          setLoading(false);
          return;
        }
        const data = snapshot.data();
        setJobDoc({
          status: (data.status as JobStatus) ?? 'completed',
          stage: data.stage ?? null,
          output_data: data.output_data ?? null,
          error_data: data.error_data ?? null,
          name: data.name ?? '',
        });
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      },
    );

    return unsubscribe;
  }, [jobId]);

  return { jobDoc, loading, error };
}
```

**Why not alias/reuse `useJobSnapshot.ts` (main app's version):** that hook wraps its
Firestore subscription in an `onAuthStateChanged` listener that tears down and
re-subscribes whenever the uid changes — necessary for the main app, where a user can sign
out and a different user can sign in in the same tab. The trial signs in once per page
load and never changes identity mid-session, so that entire resubscribe-on-auth-change
mechanism is dead weight (and, worse, imports `../api/firebase` by relative path — see
§4.6 for why that's the wrong file to pull in through an alias). The trial's version is a
direct, single `onSnapshot` subscription keyed only on `jobId`, mirroring the *pattern*
(same collection, same field names, same Firestore rules already permit anonymous-auth
reads — confirmed unchanged in SP2 PRD §4.11) without the unneeded complexity — exactly
what SP2's own PRD (§5) instructs: "SP3 must use the Firestore `onSnapshot` pattern," not
"SP3 must reuse this exact file."

`session_id`/`batch_run_id`/`shared`/`comment`/`trace_id` are omitted from `TrialJobDoc`
on purpose — the results screen never displays them (explicitly excluded), so there is no
reason to read or expose them.

### 4.9 State machine — `AppState`, and `stage` → `PipelineStep` mapping

`AppState` (`'upload' | 'processing' | 'result'`) is imported, unmodified, from
`@main/types/carePlan` — it is already exactly the three values this app needs, and it is
on D3's shared `types/` list. **`TrialPage.tsx` does not introduce a fourth literal for
"error"** — a pipeline failure is a `jobDoc.status === 'error'` value observed *while*
`AppState === 'result'`, rendered as a distinct sub-view inside `ResultScreen` (§4.11,
§4.14) rather than as a new top-level state. This mirrors the main app's own
`CarePlanJobPage.tsx`, which branches on `jobDoc.status === 'error'` inside its single
result-route render function rather than modeling error as a separate route/state.

```tsx
// pages/TrialPage.tsx (orchestrator — abbreviated to the state-machine skeleton)
import { useState, useRef } from 'react';
import type { AppState } from '@main/types/carePlan';
import { useAnonAuth } from '../hooks/useAnonAuth';
import { useTrialJobSnapshot } from '../hooks/useTrialJobSnapshot';
import { useUnloadCleanup } from '../hooks/useUnloadCleanup';
import UploadScreen from '../components/UploadScreen';
import ProcessingScreen from '../components/ProcessingScreen';
import ResultScreen from '../components/ResultScreen';
import Footer from '../components/Footer';

export default function TrialPage() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [jobId, setJobId] = useState<string | null>(null);
  const { authState, retry } = useAnonAuth();
  const { jobDoc, error: snapshotError } = useTrialJobSnapshot(jobId);
  const deletedRef = useRef<Set<string>>(new Set());

  useUnloadCleanup(jobId, appState, deletedRef);

  function handleJobCreated(id: string) {
    setJobId(id);
    setAppState('processing');
  }

  // Advance processing -> result the moment the job doc reaches a terminal status.
  if (appState === 'processing' && jobDoc && (jobDoc.status === 'completed' || jobDoc.status === 'error')) {
    setAppState('result');
  }

  function handleRestart() {
    setJobId(null);
    setAppState('upload');
  }

  return (
    <div className="trial-page">
      {appState === 'upload' && (
        <UploadScreen authState={authState} onAuthRetry={retry} onJobCreated={handleJobCreated} />
      )}
      {appState === 'processing' && (
        <ProcessingScreen jobDoc={jobDoc} snapshotError={snapshotError} />
      )}
      {appState === 'result' && jobDoc && (
        <ResultScreen jobDoc={jobDoc} jobId={jobId} deletedRef={deletedRef} onRestart={handleRestart} />
      )}
      <Footer />
    </div>
  );
}
```

**`stage` → `PipelineStep` mapping**, identical logic to the main app's
`stepsFromStage` (`CarePlanJobPage.tsx:18-29`), reusing `PipelineStep`/`StepStatus` types
from `@main/types/carePlan` and a trial-owned copy of the five step labels (matching
`Constants.Pipeline.PIPELINE_V1_2_STEPS`'s labels verbatim, per the task brief):

```ts
// components/ProcessingScreen.tsx (excerpt)
import type { PipelineStep } from '@main/types/carePlan';

const TRIAL_STEPS: Omit<PipelineStep, 'status'>[] = [
  { id: 1, label: 'Reading your note', description: 'Extracting text from your input' },
  { id: 2, label: 'Finding difficult and medical terms', description: 'Matching terms from AHRQ and medical dictionary' },
  { id: 3, label: 'Simplifying language', description: 'Rewriting to a 6th-grade reading level' },
  { id: 4, label: 'Clarifying actions and numbers', description: 'Active voice, plain action verbs, clear instructions' },
  { id: 5, label: 'Organizing your care plan', description: 'Structuring into sections that are easy to follow' },
];

function stepsFromStage(stage: number | null): PipelineStep[] {
  return TRIAL_STEPS.map(step => ({
    ...step,
    status: stage == null ? 'waiting' : step.id < stage ? 'done' : step.id === stage ? 'active' : 'waiting',
  }));
}
```

Note step 3's label: the task brief's authoritative label list (from
`Constants.Pipeline.PIPELINE_V1_2_STEPS`, `backend/utils/constants.py`) says **"Simplifying
language"**; `frontend/src/pages/care-plan/CarePlanPage.tsx`'s `INITIAL_STEPS` const
currently says "Rewriting to plain language" for the same step id — a small, pre-existing
drift between the backend's enum labels and the main app's hardcoded copy. This PRD uses
the **backend's** label (the authoritative source named in the task brief) for the trial,
and flags the main app's drift as an out-of-scope, pre-existing inconsistency (§9 Q3) —
not something SP3 fixes in `frontend/`.

**GA instrumentation hook points** (§4.15's event table): `pipeline_step_start` fires the
first time `stepsFromStage` computes a given step as `'active'`; `pipeline_step_complete`
fires the first time it computes that step as `'done'`. Both are driven off a `useRef` of
the highest `stage` value seen so far, to fire exactly once per step per job (React
Strict Mode double-invokes effects in dev; the ref guard makes this idempotent).

### 4.10 Client-side validation — `utils/validateFiles.ts`

```ts
export const ALLOWED_UPLOAD_EXTENSIONS = [
  'pdf', 'txt', 'docx', 'html', 'htm', 'png', 'jpg', 'jpeg', 'webp', 'heic',
];
export const MAX_FILES = 5;                          // SP2 Constants.Trial.MAX_FILE_COUNT
export const MAX_FILE_BYTES = 10 * 1024 * 1024;       // Constants.Uploads.MAX_FILE_BYTES
export const MAX_AGGREGATE_BYTES = 25 * 1024 * 1024;  // Constants.Uploads.MAX_AGGREGATE_FILE_BYTES
export const MAX_TEXT_LENGTH = 100_000;               // §9 Q4 — client-side only, no server mirror

export function validateFiles(selected: File[]): string | null {
  if (selected.length === 0) return null;
  if (selected.length > MAX_FILES) {
    return `You can upload up to ${MAX_FILES} files at a time (selected ${selected.length}).`;
  }
  const invalidExt = selected.filter(f => {
    const ext = f.name.split('.').pop()?.toLowerCase() ?? '';
    return !ALLOWED_UPLOAD_EXTENSIONS.includes(ext);
  });
  if (invalidExt.length > 0) {
    return `Unsupported file type: ${invalidExt.map(f => f.name).join(', ')}. ` +
      'Use PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC).';
  }
  const tooLarge = selected.filter(f => f.size > MAX_FILE_BYTES);
  if (tooLarge.length > 0) {
    return `File too large (max 10MB each): ${tooLarge.map(f => f.name).join(', ')}.`;
  }
  const totalBytes = selected.reduce((sum, f) => sum + f.size, 0);
  if (totalBytes > MAX_AGGREGATE_BYTES) {
    return 'Combined file size is too large (max 25MB total). Remove a file and try again.';
  }
  return null;
}

export function validateText(text: string): string | null {
  if (text.length > MAX_TEXT_LENGTH) {
    return `Pasted text is too long (max ${MAX_TEXT_LENGTH.toLocaleString()} characters, ` +
      `got ${text.length.toLocaleString()}). Try shortening it or uploading a file instead.`;
  }
  return null;
}
```

These four file-related numbers mirror SP2's server-side values (`Constants.Trial.MAX_FILE_COUNT=5`,
`Constants.Uploads.MAX_FILE_BYTES`/`MAX_AGGREGATE_FILE_BYTES`, unchanged from the main
app) exactly, but there is **no shared source of truth across the Python/TypeScript
boundary** — this is the same situation SP1's own Q4 already identified and deferred for
the main app's extension list. The server (SP2 §5) is authoritative regardless: any drift
here only degrades from "instant client feedback" to "a 400 after a wasted upload," never
a correctness or security problem, since the server always re-validates independently.

**Paste-text path (§9 Q4, resolved 2026-09-05):** a client-side cap of 100,000 characters
(`MAX_TEXT_LENGTH`, roughly 15–20k words — far beyond any realistic care plan) is enforced
via `validateText`, shown as an inline `.error-box` message on the Upload screen (§4.11)
when exceeded, blocking submit the same way `validateFiles` does for the file path. No
`MAX_TEXT_LENGTH`-shaped constant exists anywhere in the backend today (confirmed:
`Constants.Uploads` only caps files), so this cap has no server value to mirror and is a
purely client-side UX guard — the server remains authoritative regardless. Flagged to SP2
as a possible follow-up if a matching server-side cap is judged worth adding later.

### 4.11 The three screens — component sketches and visual layout

All three screens (plus `/privacy`/`/terms`) share one centered-card visual language,
reusing the main app's existing CSS classes via the shared-stylesheet import (§4.17) —
**no sidebar, no top nav, no aurora background** (those are main-app chrome the product
brief excludes).

**Upload screen** (`components/UploadScreen.tsx`):
- A minimal header: "Juno" wordmark + one-line tagline ("Turn your care plan into plain
  language"), centered, no nav links.
- Two-tab toggle, reusing `.input-tabs`/`.input-tab`: "Upload files" / "Paste text".
  Clicking a tab fires `input_mode_selected` (GA).
- **File mode:** a drag-and-drop zone (`.upload-zone`), `<input type="file" multiple
  accept=".pdf,.txt,.docx,.html,.htm,.png,.jpg,.jpeg,.webp,.heic">`. Selected files render
  as a list with a small ✕ remove-button per file (a small addition over the main app's
  version — useful here because the 5-file cap makes "deselect one file" a real, expected
  interaction, not an edge case). Hint text: "PDF, TXT, DOCX, HTML, or an image (PNG/JPG/
  WEBP/HEIC) · Up to 5 files". On a valid (post-validation) selection, fires
  `files_selected` (GA, `file_count` + sorted-unique `file_types`).
- **Text mode:** `.text-input-area` textarea, same placeholder tone as the main app's.
  Capped client-side at 100,000 characters (`validateText`, §4.10, §9 Q4) — pasting past
  the cap surfaces the inline error below rather than truncating silently.
- Inline `.error-box` for validation errors (client-side, from `validateFiles`/`validateText`)
  and submission errors (server 4xx/5xx, §4.14).
- One button, `.cta-btn`, label **"Simplify"** — the *only* button on this screen (no
  grading toggle, no preset-data card, no version selector). `disabled` when
  `authState !== 'ready'` OR no valid input OR a submit is already in flight (label
  changes to "Starting…" while in flight). Click fires `simplify_clicked` (GA) before the
  network call, then `simplify_submit_success`/`simplify_submit_error` after it resolves.
- `Footer` (§4.16) at the bottom, present on every screen.

**Processing screen** (`components/ProcessingScreen.tsx`):
- Same centered `.glass-card` step-list layout as the main app's inline "Creating your
  care plan…" block (`CarePlanJobPage.tsx`'s JSX, `.step-list`/`.step-item`/`.step-node`/
  `.step-label`/`.step-desc`) — small enough (≈20 lines) to re-implement directly in the
  trial rather than alias, since it is page-specific JSX, not a reusable library function.
- Heading: "Creating your simplified care plan…" — **identical copy regardless of elapsed
  time** (D7: no cold-start-specific messaging; the first visitor after Cloud Run scales
  from zero sees the exact same screen as every subsequent visitor, just for longer).
- If `snapshotError` is set (Firestore listener error, not a transient network blip — see
  §4.14), the step list is replaced with a plain-language reconnect message.
- `Footer` still rendered.

**Result screen** (`components/ResultScreen.tsx`):
- Header block: `<h1>{jobDoc.name}</h1>` (the derived title — §4.14) and, directly under
  it, `<p>{formattedDate}</p>` — **just the date**, no "Simplified on" prefix (unlike the
  main app's `CarePlanJobResultView.tsx`, which does prefix it — a deliberate, brief-driven
  difference, not an oversight).
- A small, prominent before→after score widget — two numbers with an arrow between them
  (e.g. "42 → 78"), derived from `grading.entries` (§4.14). No sub-score breakdown, no
  dimension chart.
- Body: `<CarePlanView result={care_plan} grading={grading} />` — the shared component,
  completely unmodified, rendered exactly as the main app renders it.
- One button: **"Download report"** (§4.12).
- `Footer`.
- **On `jobDoc.status === 'error'`:** the score widget and `CarePlanView` body are replaced
  by an error message built from `jobDoc.error_data.user_hint` (falling back to
  `.message`) and a **"Try again"** button that calls `onRestart()` (§4.9), returning to
  the upload screen with cleared state. **Confirmed by user decision (§9 Q6, resolved
  2026-09-05): this button is scoped to the ERROR sub-view only** — it is a distinct
  error-recovery affordance (there is otherwise no way to retry after a pipeline failure
  besides a manual page reload), not the excluded "start a second, separate care plan
  after a successful one" feature.
- **On the *success* sub-view**, no such button exists — the "no Another care plan
  button" exclusion applies exactly as originally scoped. The distinction is deliberate:
  ERROR gets "Try again"; SUCCESS does not get an equivalent "Another care plan" button.
- Explicitly absent, confirmed against the brief: Show Original button, session ID, trace
  ID, "Another care plan" button (on the *success* sub-view), score breakdown, Download
  JSON, grading toggle/UI, share button, comment/notes area, saved-outputs sidebar.

### 4.12 Download report — `utils/downloadReport.ts`

Grepped `frontend/src` for every `buildPdfHtml` caller (confirmed: exactly one,
`CarePlanJobPage.tsx:88-99`, `handleDownloadPdf`). That is the mechanism this PRD reuses
verbatim — **it does not trigger a literal file download.** It opens a new browser tab
containing print-formatted HTML (an in-page "Print / Save as PDF" button plus an
auto-invoked `window.print()`), and the user completes the "download" via their browser's
native print dialog's Save-as-PDF option. This is the *only* PDF-generation mechanism
anywhere in the codebase today (the main app's separate `handleDownloadJson` uses a real
Blob-anchor-click download, but that is for JSON, which the trial explicitly excludes).

```ts
// utils/downloadReport.ts
import { buildPdfHtml } from '@main/utils/buildPdfHtml';
import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';
import { trackEvent } from '../analytics/ga';

export function downloadReport(carePlan: SimplifiedCarePlan, grading: Grading): void {
  trackEvent({ name: 'report_downloaded', params: {} });
  const html = buildPdfHtml(carePlan, grading);
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    alert('Pop-up blocked. Please allow pop-ups to download the report.');
    return;
  }
  printWindow.document.write(html);
  printWindow.document.close();
  setTimeout(() => printWindow.print(), 500);
}
```

This is an inherited UX quirk (a print dialog, not a one-click file save), not something
SP3 fixes here — fixing it would mean building a client-side HTML-to-PDF renderer, a real
new capability out of scope for a PRD whose locked decision (brainstorm §6) is "reuse
`buildPdfHtml.ts` directly."

### 4.13 `DELETE /trial/jobs/<id>` — firing strategy (`hooks/useUnloadCleanup.ts`)

Two independent triggers, because either one alone misses a real case:

1. **Primary — fires on reaching the result screen.** `ResultScreen` calls
   `deleteTrialJob(jobId)` once, in a `useEffect` keyed on `jobId`, immediately after the
   job doc's first terminal (`completed`/`error`) render. Covers the overwhelming majority
   of visits — the "happy path" the brief's brainstorm.md §5 describes as layer (b).
2. **Safety net — fires on tab close / navigation / backgrounding, whenever a `jobId`
   exists and hasn't already been cleaned up**, regardless of whether the app ever reached
   the result screen (i.e., also covers "closed the tab while still on the processing
   screen"). Implemented as a `useEffect` in `TrialPage.tsx` registering **both**
   `document.visibilitychange` (state `'hidden'`) and `window.pagehide` — not either one
   alone:
   - `visibilitychange` → `'hidden'` is the more reliably-firing signal on mobile Safari
     (backgrounding/app-switching does not always fire `pagehide`/`unload` there).
   - `pagehide` is the modern replacement for the deprecated `unload`/`beforeunload` pair
     and is the correct backstop for desktop tab-close/navigation, including pages
     eligible for the back/forward cache.

```ts
// hooks/useUnloadCleanup.ts
import { useEffect } from 'react';
import type { AppState } from '@main/types/carePlan';
import { deleteTrialJob } from '../api/trialApi';

export function useUnloadCleanup(
  jobId: string | null,
  appState: AppState,
  deletedRef: React.MutableRefObject<Set<string>>,
): void {
  useEffect(() => {
    if (!jobId || appState === 'upload') return;

    const fireOnce = () => {
      if (deletedRef.current.has(jobId)) return;
      deletedRef.current.add(jobId);
      // fire-and-forget; fetch(keepalive) survives page teardown in every
      // evergreen browser — see below for why sendBeacon is not used here.
      void deleteTrialJob(jobId).catch(() => { /* best-effort; expires_at is the safety net */ });
    };

    const onVisibilityChange = () => { if (document.visibilityState === 'hidden') fireOnce(); };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', fireOnce);

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', fireOnce);
    };
  }, [jobId, appState, deletedRef]);
}
```

`ResultScreen`'s own primary-trigger `useEffect` shares the same `deletedRef` (passed down
from `TrialPage`, §4.9) so the two triggers can never double-fire in a way that matters —
though double-firing would be harmless anyway, since `DELETE /trial/jobs/<id>` is
idempotent by design (SP2 §5: "calling `DELETE` twice returns `204` then `404`").

**Why `navigator.sendBeacon` is not used, despite being the textbook "reliable send on
unload" API:** `sendBeacon(url, data)` has no mechanism to attach custom headers — its
second argument is only a body (optionally typed via a `Blob`'s `type`, which becomes the
`Content-Type` header and nothing else). `DELETE /trial/jobs/<id>` requires an
`Authorization: Bearer <firebase-id-token>` header (every trial route is behind
`@verify_firebase_token`, SP2 §5, D1) — there is no way to attach it via `sendBeacon`, and
no way to authenticate the delete without it (the route has no alternative, e.g.
query-string token, auth path — nor should it grow one just for this). `fetch(url, {
method: 'DELETE', headers, keepalive: true })` is the browser-native alternative that
*can* carry arbitrary headers and is documented to survive page-teardown for the same
class of use cases `sendBeacon` targets, in every currently-evergreen browser. This is the
answer to the task brief's explicit "note the Authorization header constraint that rules
out `sendBeacon`."

**What happens if all of this fails** (browser killed the tab process before any handler
ran, an ad-blocker interferes, etc.): `expires_at` (SP2 §4.7, 1-hour TTL on the job doc)
and the worker's own GCS-input deletion on every terminal job state (SP2 §4.5, unconditional
on `is_trial`, independent of any DELETE call ever happening) are the two server-side
safety nets. This frontend layer is a *fast-path* privacy improvement (data usually gone
in seconds, not up to an hour), never the sole guarantee.

### 4.14 Date, title, and score — exact field sourcing

- **Title:** `jobDoc.name` — server-derived by `derive_output_name()` (task brief; no
  title field exists inside `care_plan` content itself). Rendered as the `<h1>` verbatim,
  no "Your Care Plan" static heading (unlike the main app's `CarePlanJobResultView.tsx`,
  which shows a static "Your Care Plan" title instead of `jobDoc.name` — the trial's use
  of `jobDoc.name` is a deliberate brief-driven choice, not a bug in either app).
- **Date:** `output_data.metrics.created_at` (an ISO-8601 string, confirmed present on
  `CarePlanInternal.metrics` in `@main/types/envelope`) — **the same field the main app
  already uses** for its "Simplified on \<date\>" line (`CarePlanJobResultView.tsx:90-94`,
  confirmed by reading it). The trial renders only the date, no prefix:
  ```ts
  new Date(outputData.metrics.created_at).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  })
  ```
  `jobDoc.created_at`/`completed_at` (the Firestore-document-level timestamps on
  `JobDoc`, not inside `output_data`) are **not** used — `TrialJobDoc` (§4.8) doesn't even
  expose them, since `output_data.metrics.created_at` is both sufficient and already the
  established main-app precedent for this exact display.
- **Score:** `output_data.grading.entries`, filtered to `entry.name === 'combined'`, read
  `.grade` for `entry.target === 'before'` and `entry.target === 'after'` — both entries
  always present for a trial job (grading is pinned `True` server-side, SP2 §5). Rendered
  as `${before} → ${after}`, no `grade_breakdown`, no other `entries` members.

### 4.15 GA4 analytics — `analytics/ga.ts` and the event table

A closed, typed wrapper is the mechanism that makes D10's hard rule ("no document
content, no filenames, no care-plan text may ever be sent as an event parameter") hard to
violate rather than merely a convention someone has to remember: `trackEvent` only accepts
one of a fixed, exhaustive set of event shapes, each with a flat `Record<string, string |
number | boolean>` params object — there is no generic "send anything" call, and no
params shape has a slot a care-plan string could be dropped into without TypeScript
rejecting it as an excess/mismatched property.

```ts
// analytics/ga.ts
const MEASUREMENT_ID = import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined;

declare global {
  interface Window {
    dataLayer: unknown[];
    gtag: (...args: unknown[]) => void;
  }
}

let initialized = false;

function ensureInitialized(): void {
  if (initialized || !MEASUREMENT_ID) return;
  initialized = true;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag(...args: unknown[]) { window.dataLayer.push(args); };
  window.gtag('js', new Date());
  // send_page_view: false — this is an SPA; GA4's automatic page_view only
  // fires once on initial script load and would never see subsequent
  // client-side route changes. Every page_view, including the first, is
  // sent manually (see usePageViewTracking in App.tsx) so there is exactly
  // one send-path to audit, not two.
  window.gtag('config', MEASUREMENT_ID, { send_page_view: false });
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`;
  document.head.appendChild(script);
}

// The exhaustive, closed set of events this app may send. Adding a new
// event means adding a case here — there is no escape hatch that accepts
// an arbitrary event name or an arbitrary params shape.
export type TrialEvent =
  | { name: 'page_view'; params: { page_path: string; page_title: string } }
  | { name: 'input_mode_selected'; params: { mode: 'file' | 'text' } }
  | { name: 'files_selected'; params: { file_count: number; file_types: string } }
  | { name: 'simplify_clicked'; params: { input_mode: 'file' | 'text'; file_count: number } }
  | { name: 'simplify_submit_success'; params: Record<string, never> }
  | { name: 'simplify_submit_error'; params: { error_code: string; http_status: number | null } }
  | { name: 'pipeline_step_start'; params: { step_id: number; step_key: string } }
  | { name: 'pipeline_step_complete'; params: { step_id: number; step_key: string } }
  | { name: 'simplify_complete'; params: { total_duration_ms: number; score_before: number; score_after: number } }
  | { name: 'simplify_pipeline_error'; params: { error_code: string; stage_reached: number | null } }
  | { name: 'report_downloaded'; params: Record<string, never> }
  | { name: 'legal_link_clicked'; params: { link: 'privacy' | 'terms'; source_screen: string } }
  | { name: 'auth_ready'; params: Record<string, never> }
  | { name: 'auth_failed'; params: Record<string, never> };

export function trackEvent(event: TrialEvent): void {
  if (!MEASUREMENT_ID) return; // no-op with no measurement id configured (local dev)
  ensureInitialized();
  window.gtag('event', event.name, event.params);
}
```

**Event table:**

| Event | Params | Fired when |
|---|---|---|
| `page_view` | `page_path`, `page_title` | Every route change (`/`, `/privacy`, `/terms`), via a `usePageViewTracking` hook keyed on `useLocation().pathname` — including the very first render, since `send_page_view: false` disables GA4's own automatic first send. |
| `input_mode_selected` | `mode: 'file' \| 'text'` | Upload screen's tab toggle clicked. |
| `files_selected` | `file_count`, `file_types` (sorted, comma-joined unique extensions, e.g. `"pdf,png"`) | A file selection passes `validateFiles` (§4.10). |
| `simplify_clicked` | `input_mode`, `file_count` (0 in text mode) | Simplify button clicked, before the network call. |
| `simplify_submit_success` | — | `POST /trial/jobs` returns 202; fires right before transitioning to `'processing'`. |
| `simplify_submit_error` | `error_code`, `http_status` | Submit failed — client validation, a network error, or a server 4xx/5xx. `error_code` is `'CLIENT_VALIDATION'` for client-side rejections (no HTTP round trip), otherwise the server's `ApiError.code` (e.g. `'RATE_LIMIT_EXCEEDED'`), or `'NETWORK_ERROR'` for a fetch-level failure. |
| `pipeline_step_start` | `step_id` (1–5), `step_key` (stable enum, e.g. `'read_note'`) | First render where `stepsFromStage` computes that step as `'active'`. |
| `pipeline_step_complete` | `step_id`, `step_key` | First render where that step becomes `'done'`. |
| `simplify_complete` | `total_duration_ms` (from `output_data.metrics.total_duration_ms`, not a client-side clock — avoids skew from a throttled background tab), `score_before`, `score_after` (both from §4.14's combined-grading entries) | `jobDoc.status` transitions to `'completed'`. |
| `simplify_pipeline_error` | `error_code` (`jobDoc.error_data.code`), `stage_reached` | `jobDoc.status` transitions to `'error'`. |
| `report_downloaded` | — | Download report button clicked. |
| `legal_link_clicked` | `link: 'privacy' \| 'terms'`, `source_screen` (the `AppState`, or `'footer'` if clicked from a legal page itself) | Footer's Privacy/Terms link clicked (in addition to the `page_view` the resulting navigation also fires). |
| `auth_ready` / `auth_failed` | — | `useAnonAuth`'s sign-in resolves / rejects. |

Every param above is a count, an enum-like string, or a timing — never a filename,
never any character of document/care-plan text. `file_types` is the one param that could
look risky at a glance; it is restricted by construction to values already validated
against the fixed `ALLOWED_UPLOAD_EXTENSIONS` list (§4.10), never the raw filename.

### 4.16 Routing, `Footer`, and the legal pages

```tsx
// App.tsx
import { Routes, Route, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import TrialPage from './pages/TrialPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';
import { trackEvent } from './analytics/ga';

function usePageViewTracking(): void {
  const location = useLocation();
  useEffect(() => {
    trackEvent({ name: 'page_view', params: { page_path: location.pathname, page_title: document.title } });
  }, [location.pathname]);
}

export default function App() {
  usePageViewTracking();
  return (
    <Routes>
      <Route path="/" element={<TrialPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="*" element={<TrialPage />} />
    </Routes>
  );
}
```

`PrivacyPage.tsx`/`TermsPage.tsx` are thin shells — a `Footer`-less static page (still
needs a way back, e.g. a "← Back" link to `/`) rendering whatever copy SP4 finalizes
(§6.2/§6.3 of SP4's PRD are drafts pending the user's review per D8 — this PRD does not
duplicate that text, only the route contract):

```tsx
// pages/PrivacyPage.tsx (structure; body text supplied by SP4)
import { Link } from 'react-router-dom';

export default function PrivacyPage() {
  return (
    <div className="legal-page">
      <Link to="/">← Back</Link>
      <article>{/* SP4's Privacy Policy copy renders here */}</article>
    </div>
  );
}
```

`components/Footer.tsx` — rendered on every screen (input, processing, results, and,
per SP4's own contract, the legal pages too — though `TrialPage.tsx` already renders it
once for all three `AppState`s; the legal pages render their own copy since a user reading
`/privacy` shouldn't see the same footer linking back to `/privacy` again):

```tsx
import { Link, useLocation } from 'react-router-dom';
import { trackEvent } from '../analytics/ga';

export default function Footer() {
  const location = useLocation();
  return (
    <footer className="trial-footer">
      <p>No documents are saved — content is deleted immediately after processing.</p>
      <p>This is a demo, not medical advice. Do not upload real patient information.</p>
      <p>
        <Link to="/privacy" onClick={() => trackEvent({ name: 'legal_link_clicked', params: { link: 'privacy', source_screen: location.pathname } })}>
          Privacy Policy
        </Link>
        {' · '}
        <Link to="/terms" onClick={() => trackEvent({ name: 'legal_link_clicked', params: { link: 'terms', source_screen: location.pathname } })}>
          Terms & Conditions
        </Link>
      </p>
    </footer>
  );
}
```

Footer copy is verbatim from SP4's PRD §6.4 — SP3 does not originate this text, only
implements the component contract SP4 designed against.

### 4.17 Styling approach — reuse existing CSS via the alias, don't recreate ~50 selectors

`CarePlanView.tsx` and `MedicalTerm.tsx` carry **zero inline styling of their own for
structural classes** (`.result-card`, `.result-card-header`, `.glossary-item`,
`.result-list`, `.medical-term`, `.medical-term-popover`, etc. — confirmed by reading both
files in full: some elements use inline `style={{...}}` for one-off colors, but the
majority of visual structure comes from class names defined in `frontend/src/App.css` and
`frontend/src/pages/care-plan/CarePlanPage.css`). Recreating ~50 selectors and the
CSS custom-property palette (`--surface`, `--border`, `--text-secondary`,
`--radius-pill`, `--accent-violet`, etc., defined in `App.css`'s `:root`) in a second
stylesheet would immediately drift from the original the first time either changes.

**Decision: `frontend-trial/src/App.css` imports the two source stylesheets directly,
by relative path through the same alias mechanism, since CSS `@import` is a Vite-resolved
asset reference, not a `tsc`-type-checked module** — sidestepping §4.4's alias-boundary
risk entirely for this piece (CSS has no import graph for `tsc` to trip over):

```css
/* frontend-trial/src/App.css */
@import '../../frontend/src/App.css';                          /* :root vars, reset, .glass-card, .cta-btn, .error-box, .medical-term* */
@import '../../frontend/src/pages/care-plan/CarePlanPage.css';  /* .input-tabs, .upload-zone, .text-input-area, .step-*, .result-card, .glossary-* */

/* Trial-only additions below — centered single-column layout, no sidebar/nav offset */
.trial-page {
  max-width: 640px;
  margin: 0 auto;
  padding: 48px 24px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.trial-footer {
  margin-top: 48px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 0.8rem;
  text-align: center;
}
```

**Tradeoff, stated plainly:** importing the whole of `App.css` also pulls in selectors the
trial never uses (`.top-nav`, `.sidebar`, `.aurora-bg`, admin-page styles, etc.) — pure
byte weight and unused CSS rules, not a functional or auth risk (CSS has no side effects,
no JS execution, nothing it could leak). Given the alternative (hand-maintaining a second
copy of ~50 selectors that silently drifts), this is the correct tradeoff for a small
trial app where a few extra KB of unused CSS is immaterial.

### 4.18 File-by-file change summary

| File | Change |
|---|---|
| `frontend-trial/package.json`, `tsconfig*.json`, `vite.config.ts`, `index.html`, `eslint.config.js`, `vitest.setup.ts` | **New.** Build/test scaffolding, mirroring `frontend/`'s equivalents plus the `@main` alias and pinned port 5174 (§4.2–§4.5). |
| `frontend-trial/src/api/firebase.ts` | **New.** Own Firebase init, deliberately not aliased (§4.6). |
| `frontend-trial/src/api/trialApi.ts` | **New.** `createTrialJob`, `deleteTrialJob` (§4.7). |
| `frontend-trial/src/hooks/useAnonAuth.ts` | **New.** Anonymous sign-in + ready-state gating (§4.6). |
| `frontend-trial/src/hooks/useTrialJobSnapshot.ts` | **New.** Trial-scoped Firestore subscription (§4.8). |
| `frontend-trial/src/hooks/useUnloadCleanup.ts` | **New.** Best-effort `DELETE` firing on visibilitychange/pagehide (§4.13). |
| `frontend-trial/src/utils/validateFiles.ts` | **New.** Client-side upload validation (§4.10). |
| `frontend-trial/src/utils/downloadReport.ts` | **New.** Wraps aliased `buildPdfHtml` (§4.12). |
| `frontend-trial/src/analytics/ga.ts` | **New.** Typed GA4 wrapper + event table (§4.15). |
| `frontend-trial/src/components/{Footer,UploadScreen,ProcessingScreen,ResultScreen}.tsx` | **New.** The three screens + footer (§4.11, §4.16). |
| `frontend-trial/src/pages/{TrialPage,PrivacyPage,TermsPage}.tsx` | **New.** State-machine orchestrator + two legal-page shells (§4.9, §4.16). |
| `frontend-trial/src/App.tsx`, `main.tsx`, `App.css` | **New.** Routing, GA page-view tracking, shared-CSS import (§4.16, §4.17). |
| `frontend/src/**` (any file) | **No change.** Confirmed: this PRD reads exactly two files (`CarePlanView.tsx`'s subtree and `buildPdfHtml.ts`) via a read-only alias and copies (not edits) the shape of two more (`useJobSnapshot.ts`, `api/firebase.ts`) as inspiration for trial-owned equivalents. |

---

## 5. API Change Summary

**No new endpoints originate from this PRD.** SP3 is purely a consumer of SP2's §5
contract:

- `POST /trial/jobs` — called from `createTrialJob` (§4.7), `multipart/form-data` with
  `files` (≤5) or `text`, `Authorization: Bearer <anon-id-token>`. Success: `202
  {"job_id": "..."}`. Errors handled per §4.14's table: `400 INPUT_VALIDATION_ERROR`,
  `401` variants, `429 RATE_LIMIT_EXCEEDED`, `500 INTERNAL_ERROR`.
- `care_plan_outputs/{jobId}` — subscribed via Firestore `onSnapshot` (§4.8), **not** a
  `GET` endpoint (SP2 §5 explicitly does not implement one; confirmed the existing
  security rule already permits anonymous-auth same-uid reads with zero rule changes).
- `DELETE /trial/jobs/<job_id>` — called from `deleteTrialJob` (§4.7, §4.13). Success:
  `204`. Idempotent (`204` then `404` on a repeat call) — the frontend never needs to
  branch on this response.

No request/response shape in this PRD deviates from SP2's documented contract; no field
SP2 marked "not accepted"/"silently ignored" (`doc_id`, `version`, `grading_enabled`) is
ever sent by `trialApi.ts`.

---

## 6. Frontend Change Summary

This entire PRD *is* the frontend change — a new, standalone Vite app, `frontend-trial/`,
fully itemized in §4.1 (file tree) and §4.18 (file-by-file summary). Zero files under
`frontend/src` are modified; two are read through a path alias (§4.4), and two more have
their *pattern* (not their code) mirrored into small trial-owned equivalents (§4.6, §4.8),
each with the reasoning for not reusing them directly stated inline.

The GA4 event table is specified in full in §4.15.

---

## 7. Testing

Own vitest config (`frontend-trial/vite.config.ts`'s `test` block, §4.3) and own
`vitest.setup.ts` (`import '@testing-library/jest-dom/vitest';`, byte-identical to
`frontend/`'s) — not shared with `frontend/`'s config, consistent with D3's "separate
Vite build": a one-line setup file is not worth coupling two otherwise-independent
projects' test runs together.

**`src/tests/utils/validateFiles.test.ts`** (new):
- Accepts a valid mixed selection (pdf + png) under all four caps.
- Rejects >5 files with the exact count in the message.
- Rejects a disallowed extension (e.g. `.gif`), listing the offending filename(s).
- Rejects a single file over 10MB.
- Rejects a valid-individually-sized set whose total exceeds 25MB.
- Empty selection returns `null` (no error) — distinguishing "nothing selected yet" from
  "invalid selection."
- `validateText` (§9 Q4): accepts text at/under 100,000 characters, rejects text over it
  with the exact length in the message.

**`src/tests/utils/downloadReport.test.ts`** (new):
- Mocks `window.open` to return a fake window object with a `document` stub and a `print`
  spy; asserts `downloadReport` writes non-empty HTML containing the plan's summary text
  and calls `print()` after the existing `buildPdfHtml`-caller's `setTimeout` delay
  (fake timers).
- Mocks `window.open` returning `null` (pop-up blocked); asserts `alert(...)` is called
  and `document.write` is never reached.
- Asserts `trackEvent` is called with exactly `{ name: 'report_downloaded', params: {} }`.

**`src/tests/utils/aliasSmoke.test.ts`** (new — the regression guard §4.4 calls for):
- Imports `buildPdfHtml`/`escapeHtml` via `@main/utils/buildPdfHtml` (not a relative path)
  and asserts a minimal fixture produces non-empty, well-formed HTML. **Purpose:** if the
  `@main` alias or the `paths` mapping is ever accidentally broken (e.g. by an unrelated
  `frontend/` directory rename), this test fails immediately and specifically, rather than
  surfacing as a confusing runtime error deep inside `ResultScreen.test.tsx`.

**`src/tests/components/CarePlanViewAliasSmoke.test.tsx`** (new, same purpose as above for
the component boundary):
- Renders `<CarePlanView result={minimalFixture} grading={emptyGrading} />` imported via
  `@main/components/CarePlanView`, asserts it renders without throwing and without
  `console.error` (catches an accidental pull-in of `react-router-dom`/auth context through
  the alias, which would surface as a context-provider-missing error here first).

**`src/tests/hooks/useAnonAuth.test.ts`** (new, mocking `firebase/auth` the same way
`frontend/src/tests/hooks/useJobSnapshot.test.ts` mocks `firebase/firestore` — confirmed
pattern, reused):
- `authState` starts `'pending'`, becomes `'ready'` with a `user` once `onAuthStateChanged`
  invokes its callback with a mock anonymous user.
- `authState` becomes `'error'` when `signInAnonymously` rejects.
- Calling `retry()` after an error re-invokes `signInAnonymously` and can recover to
  `'ready'`.
- `trackEvent` is called with `auth_ready`/`auth_failed` at the right transitions (mock
  the `ga` module).

**`src/tests/hooks/useTrialJobSnapshot.test.ts`** (new, mirroring
`useJobSnapshot.test.ts`'s `onSnapshot` mocking exactly, minus the `onAuthStateChanged`
wrapping this simpler hook doesn't have):
- `loading=true, jobDoc=null` immediately when a `jobId` is provided.
- `jobDoc` populates correctly on a snapshot with `status`/`stage`/`output_data`/
  `error_data`/`name`, defaulting missing fields the same way the main app's hook does.
- Snapshot `error` callback sets `error` and `loading=false`.
- Passing `jobId=null` clears `jobDoc`/`error` and sets `loading=false`.
- Unsubscribes on unmount and on `jobId` change (assert the mock unsubscribe fn is
  called).

**`src/tests/api/trialApi.test.ts`** (new, mocking global `fetch`):
- `createTrialJob` sends `POST {API_URL}/trial/jobs` with an `Authorization` header built
  from the mocked current user's ID token, and the given `FormData` as the body.
- A `202` response resolves with `{ job_id }`.
- A `400`/`429` JSON-error-shaped response throws `ApiError` with the right `code`/
  `userHint` (mirrors `frontend/src/tests/api/apiClient.test.ts`'s existing assertions for
  the same envelope shape).
- `deleteTrialJob` sends `DELETE {API_URL}/trial/jobs/<id>` with `keepalive: true` and the
  `Authorization` header; a missing current user makes it a no-op (no fetch call).

**`src/tests/analytics/ga.test.ts`** (new):
- `trackEvent` is a no-op (no `dataLayer` push, no script tag inserted) when
  `VITE_GA_MEASUREMENT_ID` is unset (simulating local dev / CI, where it will typically be
  unset — see §9 Q5).
- With a measurement ID set (via `vi.stubEnv`), the first `trackEvent` call inserts the
  `gtag.js` script tag exactly once and calls `gtag('config', ..., { send_page_view:
  false })`; a second `trackEvent` call does not re-insert the script.
- **Not tested here (a compile-time property, not a runtime one):** that `trackEvent`
  rejects an arbitrary event name or an extra params field — that's enforced by `tsc`
  during `npm run build`/`lint`, not by a vitest assertion. Noted so a reviewer doesn't
  look for a runtime test that wouldn't make sense to write.

**`src/tests/components/{UploadScreen,ProcessingScreen,ResultScreen}.test.tsx`** (new):
- `UploadScreen`: Simplify button `disabled` while `authState !== 'ready'`; an invalid
  file selection shows the `validateFiles` error and leaves the button disabled; a valid
  selection + `authState==='ready'` enables it; clicking it calls the mocked
  `createTrialJob` and, on success, calls `onJobCreated(jobId)`.
- `ProcessingScreen`: given a `jobDoc` fixture with `stage: 3`, steps 1–2 render `'done'`,
  step 3 `'active'`, steps 4–5 `'waiting'`; a `snapshotError` fixture renders the
  reconnect message instead of the step list.
- `ResultScreen`: a `completed` fixture renders the title (`jobDoc.name`), the formatted
  date (no "Simplified on" prefix — an explicit assertion, since this is a
  brief-mandated difference from the main app), the before→after score string, and
  `CarePlanView`'s content; an `error` fixture renders the error message + "Try again"
  button instead, and clicking it calls `onRestart`; clicking "Download report" calls the
  mocked `downloadReport`.

**`src/tests/pages/{PrivacyPage,TermsPage}.test.tsx`** (new): trivial render-smoke tests
(renders without throwing, contains a "← Back" link to `/`) — the copy itself is SP4's,
not asserted against specific text here since that text doesn't exist in this repo yet
(D8: pending user review).

**CI (resolving SP4's own PRD §9 Q8, which deferred this decision to SP3):** add a third
job to `.github/workflows/ci.yml`, `frontend-trial`, mirroring the existing `frontend`
job exactly (same Node setup, `npm ci`, `npm run test`), `working-directory:
frontend-trial`. This is the natural, low-cost place to catch an alias break or a broken
build on every PR, rather than only at `deploy.yml` time:

```yaml
  frontend-trial:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '24'
          cache: 'npm'
          cache-dependency-path: frontend-trial/package-lock.json
      - name: Install dependencies
        run: npm ci
        working-directory: frontend-trial
      - name: Run frontend-trial tests
        run: npm run test
        working-directory: frontend-trial
```

Not added here (left to whoever wires `ci.yml`'s build step, if any is added later): a
`tsc -b`/`npm run build` step in CI, which would also catch a broken alias at the type
level, not just at the test level. `npm run test` alone does exercise the alias (via
`aliasSmoke.test.ts`/`CarePlanViewAliasSmoke.test.tsx`, which import through `@main/*`),
but vitest's transform does not run full `tsc` type-checking — flagged as a gap in §9 Q7.

---

## 8. Manual Intervention Required From You

**None required to land this SP's code.** Three items to be aware of, not blocking:

1. **First-build verification of the `@main` alias (§4.4).** The implementer must run
   `npm run build` in a freshly scaffolded `frontend-trial/` as the very first step,
   before writing any screen, to confirm `tsc -b` actually type-checks across the alias
   boundary as designed. If it fails, the fallback (copy the five shared files instead of
   aliasing them, §4.4) is fully specified and should be applied without needing a design
   round-trip back through this PRD.
2. **Confirm the `VITE_GA_MEASUREMENT_ID` env var name with SP4** before merging — SP4's
   PRD already picked this exact name and wired it into `deploy.yml`'s build step for
   `frontend-trial/` (its §4.3, §9 Q5), so this should already match, but it's the one
   cross-SP name that must agree byte-for-byte or GA silently never initializes in
   production.
3. **This SP cannot be deployed standalone.** `frontend-trial/dist` has nowhere to be
   served until SP4 lands its Hosting config (root `firebase.json`'s `trial` target). Land
   SP3's code freely (it's harmless, unreferenced by anything, until SP4 wires the deploy
   target), but the two SPs' actual go-live is coupled.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Should `ALLOWED_UPLOAD_EXTENSIONS` live in a new shared `frontend/src/constants.ts` entry both `frontend/` and `frontend-trial/` import, instead of two independently hardcoded copies? | **[DEFERRED]** — SP1's own PRD (§9 Q4) already raised and deferred exactly this for `frontend/`'s own hardcoded list, on the grounds that no shared constant currently exists and introducing one is a reasonable-but-not-required dedup. Now that SP3 exists and the duplication is real (not speculative), this is worth doing as a small follow-up — but it touches `frontend/src/constants.ts` (out of this PRD's "no changes to `frontend/`" non-goal) and is not required for SP3's own correctness, so it is left as a flagged follow-up rather than expanded into this PRD's scope. |
| Q2 | If the `@main` alias fails `tsc -b` type-checking (§4.4) and the fallback (copying 5 files) is used instead, who keeps the copies in sync when `frontend/src`'s originals change? | **[RESOLVED: no drift detection — per user 2026-09-05]** — accepted risk for a prototype; no automated drift-detection (e.g. a CI diff check between the copy and the source) is added. The copy's header comment (§4.4) remains the only mitigation, making the staleness risk visible to the next person reading either file, but no machinery is built to detect or prevent drift if the fallback is ever invoked. |
| Q3 | Step 3's pipeline-step label: this PRD uses the backend's `Constants.Pipeline.PIPELINE_V1_2_STEPS` label ("Simplifying language"), which differs from `frontend/`'s own hardcoded `INITIAL_STEPS` const ("Rewriting to plain language") for the same step id. | **[RESOLVED for this PRD: use the backend's label.]** The backend enum is the task brief's cited authoritative source; the main app's copy is a small, pre-existing, out-of-scope drift this PRD does not fix (that would be a `frontend/src` change, outside this PRD's non-goals). |
| Q4 | Should the paste-text textarea have a client-side character/length cap? | **[RESOLVED: yes, a generous 100,000-character cap — per user 2026-09-05]** — user's guidance: "Yes. Maybe a large limit?" 100,000 characters (roughly 15–20k words) is far beyond any realistic care plan while still bounding abuse and Gemini cost. Enforced client-side via a new `validateText` function alongside `validateFiles` in `validateFiles.ts` (§4.10), with a clear inline error message when exceeded. No server-side text-length limit exists to mirror (`Constants.Uploads` only caps files) — the server remains authoritative regardless, and this is flagged to SP2 as a possible follow-up if a matching server-side cap is needed. |
| Q5 | Will `VITE_GA_MEASUREMENT_ID` be set in local dev / CI test runs, or only in `deploy.yml`'s production build? | **[RESOLVED, matches SP4's design]** — SP4's `deploy.yml` (§4.3 of that PRD) only sets this env var in the `Build trial (frontend-trial/)` CI step; local `npm run dev` and the `frontend-trial` CI test job (§7) will not have it set, so `analytics/ga.ts` is a no-op in both — exactly the intended behavior (§4.15, §7's `ga.test.ts`), not an oversight. |
| Q6 | The "Try again" button on the *error* sub-view of the result screen (§4.11) — is this in tension with the brief's explicit "no Another care plan button" exclusion? | **[RESOLVED: Approved by user 2026-09-05 — the ERROR screen gets a "Try again" button returning to the upload screen. The SUCCESS/results screen keeps the original exclusion: no "Another care plan" button. Rationale: without it a failed run is a dead end requiring a manual page reload, which reads as broken on a publicly shared link.]** |
| Q7 | Should a `tsc -b`/`npm run build` type-check step be added to `ci.yml`'s new `frontend-trial` job (§7), given `npm run test` alone doesn't fully re-verify the alias at the type level? | **[DEFERRED]** — reasonable follow-up (and would strengthen the exact alias-fragility concern §4.4 flags), but the existing `frontend` CI job also only runs `npm run test`, not a separate build/typecheck step, so adding one only to the new job would be an inconsistency between the two frontend CI jobs worth deciding for both at once, not unilaterally introduced here. |
| Q8 | Does the Firestore security rule change needed for the trial's anonymous reads require anything from SP3? | **[RESOLVED: no.]** Per SP2 §4.11 (verified against the current `firestore.rules`), the existing `allow get: if request.auth.uid == resource.data.uid` rule already permits an anonymous-auth uid to read its own trial job doc with zero rule changes — nothing for SP3 to configure or request. |
| Q9 | Should `frontend-trial/` have its own `robots.txt` / meta tags discouraging search-engine indexing of a page that invites PHI-adjacent uploads, given it's now the primary public address (D2)? | **[RESOLVED: Approved by user 2026-09-05 — ALLOW search indexing. No robots noindex meta tag. The user wants Juno discoverable organically. Consequence to monitor: uncontrolled search traffic against a free no-login AI endpoint means SP2's 5-requests-per-IP-per-hour limit and the Cloud Run max-instances ceiling are the only cost guards; revisit if costs climb.]** |

**Dependencies:** SP2's §5 API contract (already locked, this PRD codes directly against
it). Coordinates with SP4 on: the `5174` dev port baked into `backend/app.py`'s CORS list
(confirmed already present in SP4's PRD §5), the `VITE_GA_MEASUREMENT_ID` env var name
(confirmed already present in SP4's PRD §4.3/§9 Q5), the `/privacy`/`/terms` route + footer
contract (confirmed already present in SP4's PRD §6.1/§6.4), and the fact that SP3's
`frontend-trial/dist` has nowhere to deploy to until SP4's Hosting config lands (§8 item
3). No conflicting assumption was found between this PRD and SP4's — every cross-cutting
value cited above was cross-checked against SP4's actual (already-written) PRD text, not
assumed.
