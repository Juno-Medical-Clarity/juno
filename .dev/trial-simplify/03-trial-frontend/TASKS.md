# Tasks: SP3 — Trial Frontend App

Source PRD: `.dev/trial-simplify/03-trial-frontend/PRD.md`. All decisions below trace to
PRD §4 (Architecture Decisions); §9 is fully `[RESOLVED]`/`[DEFERRED]` — no open questions
block this work. Order matches dependency order; each task is committable on its own.

**Cross-SP boundaries respected in this file:** no changes to any file under
`frontend/src` (read-only via the `@main` path alias — PRD §3 non-goal); no
`firebase.json`/`.firebaserc`/`deploy.yml`/CORS/legal-copy changes (SP4's scope); no
Firestore TTL policy or GCS lifecycle rule changes (SP5's scope). Everything in this file
lives under a brand-new `frontend-trial/` directory plus one new job in the existing
`.github/workflows/ci.yml`.

**Deferred, per the PRD (do not build these — noted so they aren't silently reopened):**
- **Q1** — a shared `frontend/src/constants.ts` entry for `ALLOWED_UPLOAD_EXTENSIONS`
  instead of two independently hardcoded copies. `frontend-trial/`'s copy in Task 9 stays
  hardcoded, on purpose.
- **Q7** — a `tsc -b`/`npm run build` type-check step in `ci.yml`'s new `frontend-trial`
  job (Task 20). The job runs `npm run test` only, mirroring the existing `frontend` job
  exactly.

**Critical path note:** Task 2 is a gate, not ordinary scaffolding — it is the PRD's own
"first thing the implementer must do" (§4.4, §8 item 1). Every task after it assumes the
`@main` alias resolved successfully through `tsc -b`. If Task 2's fallback branch is
taken instead, every `@main/...` import in Tasks 6, 9, 11, 14, 16 below becomes a
`../shared/...` import to the copied files — re-read Task 2's fallback branch before
starting any of those tasks if that happened.

---

### Task 1 — Scaffold `frontend-trial/`'s build and lint config

   - Files (all new): `frontend-trial/package.json`, `frontend-trial/tsconfig.json`,
     `frontend-trial/tsconfig.app.json`, `frontend-trial/tsconfig.node.json`,
     `frontend-trial/vite.config.ts`, `frontend-trial/eslint.config.js`,
     `frontend-trial/vitest.setup.ts`, `frontend-trial/.env.example`
   - Changes:
     1. `package.json` — verbatim from PRD §4.2:
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
     2. `tsconfig.json` — byte-identical to `frontend/tsconfig.json`:
        ```json
        {
          "files": [],
          "references": [
            { "path": "./tsconfig.app.json" },
            { "path": "./tsconfig.node.json" }
          ]
        }
        ```
     3. `tsconfig.app.json` — `frontend/tsconfig.app.json` plus `baseUrl`/`paths`
        (PRD §4.4):
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
     4. `tsconfig.node.json` — byte-identical to `frontend/tsconfig.node.json` (only
        type-checks `vite.config.ts`; untouched by the alias):
        ```json
        {
          "compilerOptions": {
            "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
            "target": "ES2022",
            "lib": ["ES2023"],
            "module": "ESNext",
            "skipLibCheck": true,
            "moduleResolution": "bundler",
            "allowImportingTsExtensions": true,
            "isolatedModules": true,
            "moduleDetection": "force",
            "noEmit": true,
            "strict": true,
            "noUnusedLocals": true,
            "noUnusedParameters": true,
            "noFallthroughCasesInSwitch": true,
            "noUncheckedSideEffectImports": true
          },
          "include": ["vite.config.ts"]
        }
        ```
     5. `vite.config.ts` — verbatim from PRD §4.3 (the `@main` alias, pinned port 5174,
        widened `server.fs.allow`):
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
              // imported through this alias — see PRD §4.4 for why the boundary is
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
            port: 5174,        // pinned, not left to Vite's auto-increment — backend/app.py's
            strictPort: true,   // CORS list (SP4) hard-codes localhost:5174 for this dev
                                // server; strictPort makes a collision fail loudly instead
                                // of silently drifting to 5175 and breaking CORS.
            fs: {
              allow: [path.resolve(__dirname, '..')],
            },
          },
          build: {
            outDir: 'dist',
            emptyOutDir: true,
          },
        })
        ```
     6. `eslint.config.js` — byte-identical to `frontend/eslint.config.js`:
        ```js
        import js from '@eslint/js';
        import globals from 'globals';
        import reactHooks from 'eslint-plugin-react-hooks';
        import reactRefresh from 'eslint-plugin-react-refresh';
        import tseslint from 'typescript-eslint';

        export default tseslint.config(
          { ignores: ['dist'] },
          {
            extends: [js.configs.recommended, ...tseslint.configs.recommended],
            files: ['**/*.{ts,tsx}'],
            languageOptions: {
              ecmaVersion: 2020,
              globals: globals.browser,
            },
            plugins: {
              'react-hooks': reactHooks,
              'react-refresh': reactRefresh,
            },
            rules: {
              ...reactHooks.configs.recommended.rules,
              'react-refresh/only-export-components': [
                'warn',
                { allowConstantExport: true },
              ],
            },
          },
        );
        ```
     7. `vitest.setup.ts` — byte-identical to `frontend/vitest.setup.ts`:
        ```ts
        import '@testing-library/jest-dom/vitest';
        ```
     8. `.env.example` — every `import.meta.env.VITE_*` name referenced anywhere in this
        PRD (§4.6's `firebase.ts`, §4.15's `ga.ts`), no `VITE_DEFAULT_VERSION` (the trial
        hard-codes `v1-2` server-side, no client version selector — initiative README's
        "Pipeline version" locked decision):
        ```
        # Copy this file to .env.local and fill in your values.
        # Same Firebase project as frontend/ — see frontend/.env.local.example.

        VITE_FIREBASE_API_KEY=
        VITE_FIREBASE_AUTH_DOMAIN=
        VITE_FIREBASE_PROJECT_ID=
        VITE_FIREBASE_STORAGE_BUCKET=
        VITE_FIREBASE_MESSAGING_SENDER_ID=
        VITE_FIREBASE_APP_ID=

        VITE_API_PROCESSING_URL=http://localhost:8080

        # Optional. Unset in local dev / CI on purpose (PRD §9 Q5) — analytics/ga.ts
        # no-ops when this is empty.
        VITE_GA_MEASUREMENT_ID=
        ```
   - Acceptance criteria:
     - `ls frontend-trial/package.json frontend-trial/tsconfig.json frontend-trial/tsconfig.app.json frontend-trial/tsconfig.node.json frontend-trial/vite.config.ts frontend-trial/eslint.config.js frontend-trial/vitest.setup.ts frontend-trial/.env.example` lists all eight files.
     - `cd frontend-trial && node -e "require('./package.json')"` parses without error
       (valid JSON).
     - No file under `frontend/` is modified (`git diff --stat frontend/` is empty).

---

### Task 2 — First-build verification of the `@main` alias (critical gate — PRD §4.4, §8 item 1)

   - Files: `frontend-trial/index.html` (new), `frontend-trial/src/main.tsx` (new, final
     content), `frontend-trial/src/App.css` (new, final content), `frontend-trial/src/App.tsx`
     (new, **temporary placeholder** — replaced in Task 18)
   - Changes:
     1. `index.html` — verbatim from PRD §4.5:
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
        No `<meta name="robots" content="noindex">` — deliberate, per PRD §9 Q9 (search
        indexing is allowed).
     2. `src/main.tsx` — verbatim from PRD §4.5. Deliberately **no `AuthProvider`**
        wrapper (that's `frontend/`'s session-timeout context, wrong model for an
        anonymous trial session — PRD §4.6):
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
     3. `src/App.css` — verbatim from PRD §4.17 (imports the two source stylesheets by
        relative path through the repo, plus trial-only layout classes):
        ```css
        /* frontend-trial/src/App.css */
        @import '../../frontend/src/App.css';
        @import '../../frontend/src/pages/care-plan/CarePlanPage.css';

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
        Note for later reference (not a code change here): the PRD's own comment on
        this snippet says the first `@import` carries `.upload-zone`/`.step-*`/
        `.result-card`/`.glossary-*`/`.medical-term*` — verified against the actual
        files, `.upload-zone`/`.step-*`/`.result-card`/`.glossary-*` are in
        `frontend/src/App.css` (first import) but `.medical-term*` is actually in
        `frontend/src/pages/care-plan/CarePlanPage.css` (second import), and
        `.input-tabs`/`.input-tab`/`.text-input-area` are in the second import too. This
        doesn't change what to write here — both files are imported either way — it only
        matters if you go looking for a selector in the file the PRD's comment names and
        don't find it there.
     4. `src/App.tsx` — **temporary placeholder**, not the real app. Its only job is to
        prove `CarePlanView` (and, transitively, `MedicalTerm`, `types/carePlan`,
        `types/envelope`) resolves and type-checks through the `@main` alias under
        `tsc -b`:
        ```tsx
        // TEMPORARY — replaced by the real router in Task 18. Exists only to prove the
        // @main alias resolves and type-checks across the tsc -b project boundary
        // (PRD §4.4) before any real screen is written.
        import CarePlanView from '@main/components/CarePlanView';
        import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';

        const EMPTY_CARE_PLAN: SimplifiedCarePlan = {
          doc_type: 'care_plan',
          urgency: 'normal',
          version: '1.2',
          summary: '',
          reason_for_visit: [],
          diagnosis: { details: [] },
          medications: [],
          tests: [],
          procedures: [],
          other: [],
          follow_up: [],
          warning_signs: [],
          questions: [],
          low_priority: [],
        };
        const EMPTY_GRADING: Grading = { entries: [], enabled: false, graded_at: null };

        export default function App() {
          return <CarePlanView result={EMPTY_CARE_PLAN} grading={EMPTY_GRADING} />;
        }
        ```
     5. Run `cd frontend-trial && npm install && npm run build`.
        - **If it succeeds:** the alias works as designed. Proceed to Task 3 unmodified.
        - **If `tsc -b` fails:** apply the PRD §4.4 fallback exactly — copy
          `CarePlanView.tsx`, `MedicalTerm.tsx`, `buildPdfHtml.ts`, `types/carePlan.ts`,
          and `types/envelope.ts` verbatim from `frontend/src/...` into
          `frontend-trial/src/shared/...` (mirroring the same relative subpaths), each
          prefixed with:
          ```
          // Copied from frontend/src/... on <date> — see PRD.md §4.4 for why. Keep in
          // sync manually.
          ```
          Update this placeholder `App.tsx` to import from `../shared/components/CarePlanView`
          instead, re-run `npm run build` to confirm it now passes, and record in this
          file's own git history (commit message) that the fallback was invoked. Every
          later task's `@main/...` import becomes `../shared/...` from that point on —
          re-check Tasks 6, 9, 11, 14, and 16 before implementing them.
   - Acceptance criteria:
     - `cd frontend-trial && npm install && npm run build` exits 0.
     - `frontend-trial/dist/` exists and contains an `index.html` after the build.
     - No file under `frontend/` is modified — `CarePlanView.tsx`/`MedicalTerm.tsx`/
       `buildPdfHtml.ts`/`types/*.ts` are read, never written, whichever path was taken.

---

### Task 3 — Alias regression-guard smoke tests

   - Files: `frontend-trial/src/tests/utils/aliasSmoke.test.ts` (new),
     `frontend-trial/src/tests/components/CarePlanViewAliasSmoke.test.tsx` (new)
   - Changes: Per PRD §4.1/§7 — these exist so a future accidental break of the `@main`
     alias (or the fallback's `../shared` copy) fails immediately and specifically,
     instead of surfacing as a confusing error deep inside a real screen's test.
     1. `aliasSmoke.test.ts`:
        ```ts
        import { describe, it, expect } from 'vitest';
        import { buildPdfHtml, escapeHtml } from '@main/utils/buildPdfHtml';
        import type { SimplifiedCarePlan } from '@main/types/envelope';

        describe('alias smoke: @main/utils/buildPdfHtml', () => {
          it('produces non-empty, well-formed HTML from a minimal fixture', () => {
            const fixture: SimplifiedCarePlan = {
              doc_type: 'care_plan',
              urgency: 'normal',
              version: '1.2',
              summary: 'Take it easy for a week.',
              reason_for_visit: [],
              diagnosis: { details: [] },
              medications: [],
              tests: [],
              procedures: [],
              other: [],
              follow_up: [],
              warning_signs: [],
              questions: [],
              low_priority: [],
            };
            const html = buildPdfHtml(fixture);
            expect(html.length).toBeGreaterThan(0);
            expect(html).toContain('<!DOCTYPE html>');
            expect(html).toContain('Take it easy for a week.');
          });

          it('escapeHtml escapes the five reserved characters', () => {
            expect(escapeHtml(`<a href="x">&'</a>`)).toBe(
              '&lt;a href=&quot;x&quot;&gt;&amp;&#039;&lt;/a&gt;',
            );
          });
        });
        ```
     2. `CarePlanViewAliasSmoke.test.tsx`:
        ```tsx
        import { describe, it, expect, vi } from 'vitest';
        import { render } from '@testing-library/react';
        import CarePlanView from '@main/components/CarePlanView';
        import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';

        describe('alias smoke: @main/components/CarePlanView', () => {
          it('renders without throwing and without console.error', () => {
            const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
            const fixture: SimplifiedCarePlan = {
              doc_type: 'care_plan',
              urgency: 'normal',
              version: '1.2',
              summary: 'Take it easy for a week.',
              reason_for_visit: [],
              diagnosis: { details: [] },
              medications: [],
              tests: [],
              procedures: [],
              other: [],
              follow_up: [],
              warning_signs: [],
              questions: [],
              low_priority: [],
            };
            const grading: Grading = { entries: [], enabled: false, graded_at: null };

            const { getByText } = render(<CarePlanView result={fixture} grading={grading} />);
            expect(getByText('Take it easy for a week.')).toBeInTheDocument();
            expect(consoleErrorSpy).not.toHaveBeenCalled();
            consoleErrorSpy.mockRestore();
          });
        });
        ```
        If Task 2's fallback branch was taken, change both files' imports from
        `@main/...` to `../../shared/...`.
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- aliasSmoke CarePlanViewAliasSmoke` passes
       both files.

---

### Task 4 — `src/api/firebase.ts` (own Firebase init, deliberately not aliased)

   - Files: `frontend-trial/src/api/firebase.ts` (new)
   - Changes: Per PRD §4.6 — a small, trial-owned duplicate of `frontend/src/api/firebase.ts`.
     **Not** imported through `@main` on purpose: aliasing it would blur the D3 boundary
     the moment any future main-app file imports `../api/firebase` by relative path (see
     PRD §4.6's full reasoning if you're tempted to alias this one).
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
   - Acceptance criteria:
     - `cd frontend-trial && npx tsc -b --noEmit 2>&1 | grep -i firebase.ts` shows no
       errors attributable to this file (the full `npm run build` from Task 2 already
       passed; this is a targeted re-check after adding real Firebase imports).
     - File is byte-for-byte identical to `frontend/src/api/firebase.ts` except for
       nothing — verify with `diff frontend/src/api/firebase.ts frontend-trial/src/api/firebase.ts`
       (expect no output).

---

### Task 5 — `analytics/ga.ts` — the closed GA4 event wrapper, plus tests

   - Files: `frontend-trial/src/analytics/ga.ts` (new),
     `frontend-trial/src/tests/analytics/ga.test.ts` (new)
   - Changes: Per PRD §4.15 — a closed, typed `TrialEvent` union is what makes D10's "no
     document content in any event parameter" rule structurally hard to violate, not just
     a convention to remember.
     1. `ga.ts` verbatim:
        ```ts
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
          window.gtag('config', MEASUREMENT_ID, { send_page_view: false });
          const script = document.createElement('script');
          script.async = true;
          script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`;
          document.head.appendChild(script);
        }

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
          if (!MEASUREMENT_ID) return;
          ensureInitialized();
          window.gtag('event', event.name, event.params);
        }
        ```
     2. `ga.test.ts` (per PRD §7):
        ```ts
        import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

        describe('analytics/ga', () => {
          afterEach(() => {
            vi.unstubAllEnvs();
            vi.resetModules();
            document.head.querySelectorAll('script').forEach(s => s.remove());
            delete (window as unknown as { gtag?: unknown }).gtag;
            delete (window as unknown as { dataLayer?: unknown }).dataLayer;
          });

          it('is a no-op with no measurement id configured', async () => {
            vi.stubEnv('VITE_GA_MEASUREMENT_ID', '');
            const { trackEvent } = await import('../../analytics/ga');
            trackEvent({ name: 'auth_ready', params: {} });
            expect(document.head.querySelector('script')).toBeNull();
            expect((window as unknown as { gtag?: unknown }).gtag).toBeUndefined();
          });

          it('inserts the gtag.js script exactly once and configures send_page_view: false', async () => {
            vi.stubEnv('VITE_GA_MEASUREMENT_ID', 'G-TEST123');
            const { trackEvent } = await import('../../analytics/ga');
            const gtagSpy = vi.fn();

            trackEvent({ name: 'auth_ready', params: {} });
            // capture the real gtag installed by ensureInitialized, then wrap it to spy
            const realGtag = window.gtag;
            window.gtag = (...args: unknown[]) => { gtagSpy(...args); return realGtag(...args); };

            trackEvent({ name: 'report_downloaded', params: {} });

            const scripts = document.head.querySelectorAll('script[src*="gtag/js"]');
            expect(scripts.length).toBe(1);
            expect(gtagSpy).toHaveBeenCalledWith('event', 'report_downloaded', {});
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- ga.test` passes.
     - `npx tsc -b` (from `frontend-trial/`) still exits 0 — the closed `TrialEvent`
       union compiles.

---

### Task 6 — `hooks/useAnonAuth.ts` — anonymous sign-in, plus tests

   - Files: `frontend-trial/src/hooks/useAnonAuth.ts` (new),
     `frontend-trial/src/tests/hooks/useAnonAuth.test.ts` (new)
   - Changes: Per PRD §4.6. Depends on Task 4 (`api/firebase.ts`) and Task 5 (`ga.ts`).
     1. `useAnonAuth.ts` verbatim:
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
        Note `useCallback` is imported but unused in this exact snippet — either drop the
        import (cleaner, `noUnusedLocals` in `tsconfig.app.json` will fail the build
        otherwise) or wrap `retry` in `useCallback(() => setAttempt(a => a + 1), [])`.
        Prefer dropping the unused import unless you have a reason to memoize `retry`.
     2. `useAnonAuth.test.ts`, mocking `firebase/auth` the same way
        `frontend/src/tests/hooks/useJobSnapshot.test.ts` mocks it (confirmed pattern):
        ```ts
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
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- useAnonAuth` passes all three cases.

---

### Task 7 — `api/trialApi.ts` — trial API client, plus tests

   - Files: `frontend-trial/src/api/trialApi.ts` (new),
     `frontend-trial/src/tests/api/trialApi.test.ts` (new)
   - Changes: Per PRD §4.7. Trims `frontend/src/api/jobs.ts` + `api/apiClient.ts`'s shape
     down to exactly what the trial needs — no batch jobs, no `doc_id`.
     1. `trialApi.ts` verbatim:
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

        /** Best-effort, fire-and-forget cleanup call — see PRD §4.13 for when this is
         * invoked and why fetch(keepalive) is used instead of navigator.sendBeacon. */
        export async function deleteTrialJob(jobId: string): Promise<void> {
          const user = firebaseAuth.currentUser;
          if (!user) return;
          const token = await user.getIdToken();
          await fetch(`${API_URL}/trial/jobs/${jobId}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
            keepalive: true,
          });
        }
        ```
        If Task 2's fallback was invoked, the two `@main/types/errors` imports become
        `../shared/types/errors`.
     2. `trialApi.test.ts`, mocking global `fetch` (mirrors
        `frontend/src/tests/api/apiClient.test.ts`'s pattern):
        ```ts
        import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

        vi.mock('../../api/firebase', () => ({
          firebaseAuth: { currentUser: null },
          API_URL: 'http://localhost:8080',
        }));

        import { createTrialJob, deleteTrialJob } from '../../api/trialApi';
        import * as firebaseModule from '../../api/firebase';

        describe('trialApi', () => {
          let fetchSpy: ReturnType<typeof vi.spyOn>;

          beforeEach(() => {
            fetchSpy = vi.spyOn(globalThis, 'fetch');
          });
          afterEach(() => {
            vi.restoreAllMocks();
            (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = null;
          });

          describe('createTrialJob', () => {
            it('POSTs to /trial/jobs with an Authorization header and the given FormData', async () => {
              const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok-abc') };
              (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;
              fetchSpy.mockResolvedValue(new Response(JSON.stringify({ job_id: 'job-1' }), { status: 202 }));

              const fd = new FormData();
              fd.append('text', 'hi');
              const result = await createTrialJob(fd);

              expect(result).toEqual({ job_id: 'job-1' });
              const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
              expect(url).toBe('http://localhost:8080/trial/jobs');
              expect(init.method).toBe('POST');
              expect(init.body).toBe(fd);
              expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-abc');
            });

            it('throws ApiError with the server code/userHint on a 400/429 error envelope', async () => {
              const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok') };
              (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;
              fetchSpy.mockResolvedValue(new Response(JSON.stringify({
                status: 'error',
                error: { code: 'RATE_LIMIT_EXCEEDED', message: 'Trial rate limit exceeded', details: null, timestamp: '2026-01-01T00:00:00Z', path: '/trial/jobs', user_hint: 'Try again later.', retryable: true },
                requestId: 'req-1',
              }), { status: 429 }));

              await expect(createTrialJob(new FormData())).rejects.toMatchObject({
                code: 'RATE_LIMIT_EXCEEDED',
                userHint: 'Try again later.',
              });
            });
          });

          describe('deleteTrialJob', () => {
            it('sends DELETE with keepalive:true and the Authorization header', async () => {
              const mockUser = { getIdToken: vi.fn().mockResolvedValue('tok') };
              (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = mockUser;
              fetchSpy.mockResolvedValue(new Response(null, { status: 204 }));

              await deleteTrialJob('job-1');

              const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
              expect(url).toBe('http://localhost:8080/trial/jobs/job-1');
              expect(init.method).toBe('DELETE');
              expect(init.keepalive).toBe(true);
              expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
            });

            it('is a no-op (no fetch call) when there is no current user', async () => {
              (firebaseModule.firebaseAuth as { currentUser: unknown }).currentUser = null;
              await deleteTrialJob('job-1');
              expect(fetchSpy).not.toHaveBeenCalled();
            });
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- trialApi` passes all cases.

---

### Task 8 — `hooks/useTrialJobSnapshot.ts` — Firestore subscription, plus tests

   - Files: `frontend-trial/src/hooks/useTrialJobSnapshot.ts` (new),
     `frontend-trial/src/tests/hooks/useTrialJobSnapshot.test.ts` (new)
   - Changes: Per PRD §4.8 — a direct, single `onSnapshot` subscription keyed only on
     `jobId`, deliberately simpler than `frontend/`'s `useJobSnapshot.ts` (no
     `onAuthStateChanged` resubscribe dance — a trial session signs in once and never
     changes identity mid-session).
     1. `useTrialJobSnapshot.ts` verbatim:
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
        If Task 2's fallback was invoked, `@main/types/errors` becomes `../shared/types/errors`.
     2. `useTrialJobSnapshot.test.ts`, mirroring `useJobSnapshot.test.ts`'s `onSnapshot`
        mocking, minus the auth-resubscribe wrapping this simpler hook doesn't have:
        ```ts
        import { describe, it, expect, vi, beforeEach } from 'vitest';
        import { renderHook, act } from '@testing-library/react';

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
        vi.mock('../../api/firebase', () => ({ firebaseDb: {} }));

        import { useTrialJobSnapshot } from '../../hooks/useTrialJobSnapshot';

        describe('useTrialJobSnapshot', () => {
          beforeEach(() => {
            mockUnsubscribe.mockClear();
            mockOnSnapshot.mockClear();
            mockDoc.mockClear();
          });

          it('starts loading=true, jobDoc=null when a jobId is provided', () => {
            const { result } = renderHook(() => useTrialJobSnapshot('job-1'));
            expect(result.current.loading).toBe(true);
            expect(result.current.jobDoc).toBeNull();
          });

          it('populates jobDoc on snapshot, defaulting missing fields', () => {
            const { result } = renderHook(() => useTrialJobSnapshot('job-1'));
            const successCb = mockOnSnapshot.mock.calls[0][1];
            act(() => successCb({
              exists: () => true,
              data: () => ({ status: 'processing', stage: 2 }),
            }));
            expect(result.current.jobDoc).toEqual({
              status: 'processing', stage: 2, output_data: null, error_data: null, name: '',
            });
            expect(result.current.loading).toBe(false);
          });

          it('sets error and loading=false on the snapshot error callback', () => {
            const { result } = renderHook(() => useTrialJobSnapshot('job-1'));
            const errorCb = mockOnSnapshot.mock.calls[0][2];
            const err = new Error('permission-denied');
            act(() => errorCb(err));
            expect(result.current.error).toBe(err);
            expect(result.current.loading).toBe(false);
          });

          it('clears jobDoc/error and sets loading=false when jobId is null', () => {
            const { result, rerender } = renderHook(({ id }) => useTrialJobSnapshot(id), { initialProps: { id: 'job-1' as string | null } });
            rerender({ id: null });
            expect(result.current.jobDoc).toBeNull();
            expect(result.current.error).toBeNull();
            expect(result.current.loading).toBe(false);
          });

          it('unsubscribes on unmount and on jobId change', () => {
            const { unmount, rerender } = renderHook(({ id }) => useTrialJobSnapshot(id), { initialProps: { id: 'job-1' } });
            rerender({ id: 'job-2' });
            expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
            unmount();
            expect(mockUnsubscribe).toHaveBeenCalledTimes(2);
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- useTrialJobSnapshot` passes all five cases.

---

### Task 9 — `utils/validateFiles.ts` — client-side validation, plus tests

   - Files: `frontend-trial/src/utils/validateFiles.ts` (new),
     `frontend-trial/src/tests/utils/validateFiles.test.ts` (new)
   - Changes: Per PRD §4.10 (§9 Q1's deferred shared-constant follow-up applies here —
     this list stays hardcoded, independent of `frontend/`'s own copy; §9 Q4's 100,000
     character paste-text cap).
     1. `validateFiles.ts` verbatim:
        ```ts
        export const ALLOWED_UPLOAD_EXTENSIONS = [
          'pdf', 'txt', 'docx', 'html', 'htm', 'png', 'jpg', 'jpeg', 'webp', 'heic',
        ];
        export const MAX_FILES = 5;
        export const MAX_FILE_BYTES = 10 * 1024 * 1024;
        export const MAX_AGGREGATE_BYTES = 25 * 1024 * 1024;
        export const MAX_TEXT_LENGTH = 100_000;

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
     2. `validateFiles.test.ts` (per PRD §7 — construct `File` objects with a helper that
        sets `.size` via `Object.defineProperty`, since the `File` constructor derives
        size from actual content length):
        ```ts
        import { describe, it, expect } from 'vitest';
        import { validateFiles, validateText, MAX_FILES, MAX_TEXT_LENGTH } from '../../utils/validateFiles';

        function fakeFile(name: string, sizeBytes: number): File {
          const file = new File([''], name);
          Object.defineProperty(file, 'size', { value: sizeBytes });
          return file;
        }

        describe('validateFiles', () => {
          it('accepts a valid mixed selection under all four caps', () => {
            expect(validateFiles([fakeFile('a.pdf', 1000), fakeFile('b.png', 2000)])).toBeNull();
          });

          it('returns null for an empty selection', () => {
            expect(validateFiles([])).toBeNull();
          });

          it('rejects more than MAX_FILES with the exact count', () => {
            const files = Array.from({ length: MAX_FILES + 1 }, (_, i) => fakeFile(`f${i}.pdf`, 100));
            const err = validateFiles(files);
            expect(err).toContain(`up to ${MAX_FILES} files`);
            expect(err).toContain(`selected ${MAX_FILES + 1}`);
          });

          it('rejects a disallowed extension, listing the filename', () => {
            const err = validateFiles([fakeFile('animated.gif', 100)]);
            expect(err).toContain('animated.gif');
          });

          it('rejects a single file over 10MB', () => {
            const err = validateFiles([fakeFile('big.pdf', 11 * 1024 * 1024)]);
            expect(err).toContain('big.pdf');
            expect(err).toContain('10MB');
          });

          it('rejects a valid-individually-sized set whose total exceeds 25MB', () => {
            const files = [fakeFile('a.pdf', 9 * 1024 * 1024), fakeFile('b.pdf', 9 * 1024 * 1024), fakeFile('c.pdf', 9 * 1024 * 1024)];
            const err = validateFiles(files);
            expect(err).toContain('25MB total');
          });
        });

        describe('validateText', () => {
          it('accepts text at or under the cap', () => {
            expect(validateText('a'.repeat(MAX_TEXT_LENGTH))).toBeNull();
          });

          it('rejects text over the cap with the exact length in the message', () => {
            const text = 'a'.repeat(MAX_TEXT_LENGTH + 1);
            const err = validateText(text);
            expect(err).toContain(`${MAX_TEXT_LENGTH + 1}`.replace(/\B(?=(\d{3})+(?!\d))/g, ','));
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- validateFiles` passes all cases.

---

### Task 10 — `utils/downloadReport.ts` — wraps aliased `buildPdfHtml`, plus tests

   - Files: `frontend-trial/src/utils/downloadReport.ts` (new),
     `frontend-trial/src/tests/utils/downloadReport.test.ts` (new)
   - Changes: Per PRD §4.12. This is the *only* PDF-generation mechanism anywhere in the
     codebase — it opens a print-formatted HTML tab and auto-invokes `window.print()`; it
     does not trigger a literal file download.
     1. `downloadReport.ts` verbatim:
        ```ts
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
        If Task 2's fallback was invoked, both `@main/...` imports become `../shared/...`.
     2. `downloadReport.test.ts` (per PRD §7, using fake timers for the 500ms delay):
        ```ts
        import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

        const trackEventMock = vi.fn();
        vi.mock('../../analytics/ga', () => ({ trackEvent: (...a: unknown[]) => trackEventMock(...a) }));

        import { downloadReport } from '../../utils/downloadReport';
        import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';

        const fixture: SimplifiedCarePlan = {
          doc_type: 'care_plan', urgency: 'normal', version: '1.2',
          summary: 'Take it easy for a week.', reason_for_visit: [], diagnosis: { details: [] },
          medications: [], tests: [], procedures: [], other: [], follow_up: [],
          warning_signs: [], questions: [], low_priority: [],
        };
        const grading: Grading = { entries: [], enabled: false, graded_at: null };

        describe('downloadReport', () => {
          beforeEach(() => { vi.useFakeTimers(); trackEventMock.mockClear(); });
          afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

          it('writes non-empty HTML and calls print() after the 500ms delay', () => {
            const printSpy = vi.fn();
            const fakeWindow = { document: { write: vi.fn(), close: vi.fn() }, print: printSpy };
            vi.spyOn(window, 'open').mockReturnValue(fakeWindow as unknown as Window);

            downloadReport(fixture, grading);

            expect(fakeWindow.document.write).toHaveBeenCalledOnce();
            const html = fakeWindow.document.write.mock.calls[0][0] as string;
            expect(html).toContain('Take it easy for a week.');
            expect(printSpy).not.toHaveBeenCalled();
            vi.advanceTimersByTime(500);
            expect(printSpy).toHaveBeenCalledOnce();
          });

          it('alerts and never calls document.write when the pop-up is blocked', () => {
            vi.spyOn(window, 'open').mockReturnValue(null);
            const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

            downloadReport(fixture, grading);

            expect(alertSpy).toHaveBeenCalledOnce();
          });

          it('calls trackEvent with exactly report_downloaded', () => {
            vi.spyOn(window, 'open').mockReturnValue({ document: { write: vi.fn(), close: vi.fn() }, print: vi.fn() } as unknown as Window);
            downloadReport(fixture, grading);
            expect(trackEventMock).toHaveBeenCalledWith({ name: 'report_downloaded', params: {} });
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- downloadReport` passes all three cases.

---

### Task 11 — `hooks/useUnloadCleanup.ts` — safety-net `DELETE` firing

   - Files: `frontend-trial/src/hooks/useUnloadCleanup.ts` (new)
   - Changes: Per PRD §4.13. No dedicated test file for this hook (not in PRD §4.1's
     test-file list — its two triggers are DOM-lifecycle events (`visibilitychange`,
     `pagehide`) that are impractical to assert meaningfully under jsdom; its shared
     logic is already covered by Task 7's `trialApi.test.ts` for `deleteTrialJob`
     itself).
     ```ts
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
     If Task 2's fallback was invoked, `@main/types/carePlan` becomes `../shared/types/carePlan`.
     `navigator.sendBeacon` is deliberately not used here — it cannot carry the
     `Authorization` header `DELETE /trial/jobs/<id>` requires (PRD §4.13's full
     reasoning).
   - Acceptance criteria:
     - `cd frontend-trial && npx tsc -b` still exits 0 with this file added.
     - Manual check: `grep -n "sendBeacon" frontend-trial/src/hooks/useUnloadCleanup.ts`
       returns nothing (confirms the deliberate non-use).

---

### Task 12 — `components/Footer.tsx`

   - Files: `frontend-trial/src/components/Footer.tsx` (new)
   - Changes: Per PRD §4.16. Copy verbatim — SP3 does not originate this text, only
     implements the component contract SP4 designed against (copy is from SP4's PRD
     §6.4):
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
     Rendered exactly once, in `TrialPage.tsx` (Task 16) — not re-rendered inside
     `UploadScreen`/`ProcessingScreen`/`ResultScreen` individually (PRD §4.9's orchestrator
     code renders `<Footer />` once outside the `appState` branches; §4.16 confirms this
     is deliberate, not an oversight, so a user on `/privacy` doesn't see a footer linking
     back to `/privacy` again).
   - Acceptance criteria:
     - `cd frontend-trial && npx tsc -b` exits 0 with this file added (requires
       `react-router-dom`'s `useLocation`, already a dependency from Task 1).

---

### Task 13 — `components/UploadScreen.tsx`, plus tests

   - Files: `frontend-trial/src/components/UploadScreen.tsx` (new),
     `frontend-trial/src/tests/components/UploadScreen.test.tsx` (new)
   - Changes: Per PRD §4.11 (visual/behavioral spec) and §4.15 (GA hook points). Props
     match `TrialPage.tsx`'s call site from PRD §4.9:
     `{ authState: AuthState; onAuthRetry: () => void; onJobCreated: (jobId: string) => void }`.
     1. `UploadScreen.tsx`:
        ```tsx
        import { useState } from 'react';
        import type { AuthState } from '../hooks/useAnonAuth';
        import { createTrialJob } from '../api/trialApi';
        import { validateFiles, validateText, MAX_FILES } from '../utils/validateFiles';
        import { trackEvent } from '../analytics/ga';
        import { ApiError } from '@main/types/errors';

        type InputMode = 'file' | 'text';

        interface UploadScreenProps {
          authState: AuthState;
          onAuthRetry: () => void;
          onJobCreated: (jobId: string) => void;
        }

        export default function UploadScreen({ authState, onAuthRetry, onJobCreated }: UploadScreenProps) {
          const [mode, setMode] = useState<InputMode>('file');
          const [files, setFiles] = useState<File[]>([]);
          const [text, setText] = useState('');
          const [error, setError] = useState<string | null>(null);
          const [submitting, setSubmitting] = useState(false);

          function selectMode(next: InputMode) {
            setMode(next);
            setError(null);
            trackEvent({ name: 'input_mode_selected', params: { mode: next } });
          }

          function handleFilesSelected(selected: File[]) {
            const combined = [...files, ...selected].slice(0, MAX_FILES);
            const validationError = validateFiles(combined);
            setError(validationError);
            if (validationError) return;
            setFiles(combined);
            const fileTypes = [...new Set(combined.map(f => f.name.split('.').pop()?.toLowerCase() ?? ''))].sort().join(',');
            trackEvent({ name: 'files_selected', params: { file_count: combined.length, file_types: fileTypes } });
          }

          function removeFile(index: number) {
            setFiles(prev => prev.filter((_, i) => i !== index));
            setError(null);
          }

          function handleTextChange(value: string) {
            setText(value);
            setError(validateText(value));
          }

          const hasValidInput = mode === 'file' ? files.length > 0 && !error : text.trim().length > 0 && !error;
          const disabled = authState !== 'ready' || !hasValidInput || submitting;

          async function handleSubmit() {
            trackEvent({ name: 'simplify_clicked', params: { input_mode: mode, file_count: mode === 'file' ? files.length : 0 } });
            setSubmitting(true);
            setError(null);
            try {
              const formData = new FormData();
              if (mode === 'file') {
                files.forEach(f => formData.append('files', f));
              } else {
                formData.append('text', text);
              }
              const { job_id } = await createTrialJob(formData);
              trackEvent({ name: 'simplify_submit_success', params: {} });
              onJobCreated(job_id);
            } catch (err) {
              let errorCode = 'NETWORK_ERROR';
              let message = 'Something went wrong. Please try again.';
              if (err instanceof ApiError) {
                errorCode = err.code;
                message = err.userHint ?? err.message;
              } else if (err instanceof Error) {
                message = err.message;
              }
              trackEvent({ name: 'simplify_submit_error', params: { error_code: errorCode, http_status: null } });
              setError(message);
            } finally {
              setSubmitting(false);
            }
          }

          return (
            <div>
              <header style={{ textAlign: 'center' }}>
                <h1>Juno</h1>
                <p>Turn your care plan into plain language</p>
              </header>

              {authState === 'error' && (
                <div className="error-box">
                  Couldn&apos;t start your session.{' '}
                  <button onClick={onAuthRetry}>Retry</button>
                </div>
              )}

              <div className="input-tabs">
                <button
                  type="button"
                  className={`input-tab ${mode === 'file' ? 'active' : ''}`}
                  onClick={() => selectMode('file')}
                >
                  Upload files
                </button>
                <button
                  type="button"
                  className={`input-tab ${mode === 'text' ? 'active' : ''}`}
                  onClick={() => selectMode('text')}
                >
                  Paste text
                </button>
              </div>

              {mode === 'file' ? (
                <div className="upload-zone">
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.txt,.docx,.html,.htm,.png,.jpg,.jpeg,.webp,.heic"
                    onChange={e => handleFilesSelected(Array.from(e.target.files ?? []))}
                  />
                  <p>PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC) · Up to {MAX_FILES} files</p>
                  <ul>
                    {files.map((f, i) => (
                      <li key={`${f.name}-${i}`}>
                        {f.name}{' '}
                        <button type="button" aria-label={`Remove ${f.name}`} onClick={() => removeFile(i)}>✕</button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <textarea
                  className="text-input-area"
                  value={text}
                  onChange={e => handleTextChange(e.target.value)}
                  placeholder="Paste your care plan text here…"
                />
              )}

              {error && <div className="error-box">{error}</div>}

              <button className="cta-btn" disabled={disabled} onClick={handleSubmit}>
                {submitting ? 'Starting…' : 'Simplify'}
              </button>
            </div>
          );
        }
        ```
        If Task 2's fallback was invoked, `@main/types/errors` becomes `../shared/types/errors`.
     2. `UploadScreen.test.tsx` (per PRD §7), using `@testing-library/user-event`:
        ```tsx
        import { describe, it, expect, vi, beforeEach } from 'vitest';
        import { render, screen } from '@testing-library/react';
        import userEvent from '@testing-library/user-event';

        const createTrialJobMock = vi.fn();
        vi.mock('../../api/trialApi', () => ({ createTrialJob: (...a: unknown[]) => createTrialJobMock(...a) }));
        vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

        import UploadScreen from '../../components/UploadScreen';

        function makeFile(name: string, type = 'text/plain') {
          return new File(['hello'], name, { type });
        }

        describe('UploadScreen', () => {
          beforeEach(() => createTrialJobMock.mockReset());

          it('disables Simplify while authState is not ready', () => {
            render(<UploadScreen authState="pending" onAuthRetry={vi.fn()} onJobCreated={vi.fn()} />);
            expect(screen.getByRole('button', { name: 'Simplify' })).toBeDisabled();
          });

          it('shows a validateFiles error and leaves the button disabled on an invalid selection', async () => {
            const user = userEvent.setup();
            render(<UploadScreen authState="ready" onAuthRetry={vi.fn()} onJobCreated={vi.fn()} />);
            const input = document.querySelector('input[type="file"]') as HTMLInputElement;
            await user.upload(input, makeFile('bad.gif'));
            expect(screen.getByText(/Unsupported file type/)).toBeInTheDocument();
            expect(screen.getByRole('button', { name: 'Simplify' })).toBeDisabled();
          });

          it('enables Simplify on a valid selection + ready auth, and calls onJobCreated on success', async () => {
            createTrialJobMock.mockResolvedValue({ job_id: 'job-1' });
            const onJobCreated = vi.fn();
            const user = userEvent.setup();
            render(<UploadScreen authState="ready" onAuthRetry={vi.fn()} onJobCreated={onJobCreated} />);
            const input = document.querySelector('input[type="file"]') as HTMLInputElement;
            await user.upload(input, makeFile('note.txt'));

            const button = screen.getByRole('button', { name: 'Simplify' });
            expect(button).toBeEnabled();
            await user.click(button);

            expect(createTrialJobMock).toHaveBeenCalledOnce();
            expect(onJobCreated).toHaveBeenCalledWith('job-1');
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- UploadScreen` passes all three cases.

---

### Task 14 — `components/ProcessingScreen.tsx`, plus tests

   - Files: `frontend-trial/src/components/ProcessingScreen.tsx` (new),
     `frontend-trial/src/tests/components/ProcessingScreen.test.tsx` (new)
   - Changes: Per PRD §4.9 (`stage` → `PipelineStep` mapping, step labels — using the
     **backend's** `PIPELINE_V1_2_STEPS` label "Simplifying language" for step 3, not
     `frontend/`'s own drifted "Rewriting to plain language" copy — PRD §9 Q3, confirmed
     against `backend/utils/constants.py` and `frontend/src/pages/care-plan/CarePlanPage.tsx`'s
     `INITIAL_STEPS`) and §4.11 (visual layout, reconnect message on `snapshotError`).
     1. `ProcessingScreen.tsx`:
        ```tsx
        import { useEffect, useRef } from 'react';
        import type { PipelineStep } from '@main/types/carePlan';
        import type { TrialJobDoc } from '../hooks/useTrialJobSnapshot';
        import { trackEvent } from '../analytics/ga';

        interface ProcessingScreenProps {
          jobDoc: TrialJobDoc | null;
          snapshotError: Error | null;
        }

        const TRIAL_STEPS: Omit<PipelineStep, 'status'>[] = [
          { id: 1, label: 'Reading your note', description: 'Extracting text from your input' },
          { id: 2, label: 'Finding difficult and medical terms', description: 'Matching terms from AHRQ and medical dictionary' },
          { id: 3, label: 'Simplifying language', description: 'Rewriting to a 6th-grade reading level' },
          { id: 4, label: 'Clarifying actions and numbers', description: 'Active voice, plain action verbs, clear instructions' },
          { id: 5, label: 'Organizing your care plan', description: 'Structuring into sections that are easy to follow' },
        ];

        const STEP_KEYS: Record<number, string> = {
          1: 'read_note', 2: 'find_terms', 3: 'simplify', 4: 'clarify', 5: 'organize',
        };

        function stepsFromStage(stage: number | null): PipelineStep[] {
          return TRIAL_STEPS.map(step => ({
            ...step,
            status: stage == null ? 'waiting' : step.id < stage ? 'done' : step.id === stage ? 'active' : 'waiting',
          }));
        }

        function stepIcon(status: string): string {
          if (status === 'done') return '✓';
          if (status === 'active') return '◉';
          return '○';
        }

        export default function ProcessingScreen({ jobDoc, snapshotError }: ProcessingScreenProps) {
          const seenActive = useRef<Set<number>>(new Set());
          const seenDone = useRef<Set<number>>(new Set());
          const steps = stepsFromStage(jobDoc?.stage ?? null);

          // Fire pipeline_step_start/pipeline_step_complete the FIRST time a step is
          // computed as 'active'/'done', per PRD §4.9 — idempotent via the two Sets
          // above (React Strict Mode double-invokes effects in dev).
          useEffect(() => {
            for (const step of steps) {
              if (step.status === 'active' && !seenActive.current.has(step.id)) {
                seenActive.current.add(step.id);
                trackEvent({ name: 'pipeline_step_start', params: { step_id: step.id, step_key: STEP_KEYS[step.id] } });
              }
              if (step.status === 'done' && !seenDone.current.has(step.id)) {
                seenDone.current.add(step.id);
                trackEvent({ name: 'pipeline_step_complete', params: { step_id: step.id, step_key: STEP_KEYS[step.id] } });
              }
            }
            // eslint-disable-next-line react-hooks/exhaustive-deps
          }, [jobDoc?.stage]);

          return (
            <div className="glass-card">
              <p className="section-title">Creating your simplified care plan…</p>
              {snapshotError ? (
                <p>
                  We lost connection while checking your progress. Please check your
                  connection — this page will keep trying to reconnect.
                </p>
              ) : (
                <div className="step-list">
                  {steps.map(step => (
                    <div className="step-item" key={step.id}>
                      <div className={`step-node ${step.status}`}>{stepIcon(step.status)}</div>
                      <div className="step-content">
                        <p className={`step-label ${step.status === 'waiting' ? 'waiting' : ''}`}>{step.label}</p>
                        <p className="step-desc">{step.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        }
        ```
        If Task 2's fallback was invoked, `@main/types/carePlan` becomes `../shared/types/carePlan`.
        The GA firing mechanism (two `Set`s keyed by step id) is an implementer-level
        choice that satisfies PRD §4.9's stated requirement ("fires the first time
        `stepsFromStage` computes a given step as `'active'`/`'done'`") more directly than
        the PRD's own suggested "useRef of the highest stage seen" mechanism — either is
        acceptable; this file uses the Set-based version because it handles a stage
        jumping by more than 1 between snapshots without extra bookkeeping.
     2. `ProcessingScreen.test.tsx` (per PRD §7):
        ```tsx
        import { describe, it, expect, vi } from 'vitest';
        import { render, screen } from '@testing-library/react';

        vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

        import ProcessingScreen from '../../components/ProcessingScreen';
        import type { TrialJobDoc } from '../../hooks/useTrialJobSnapshot';

        const baseJobDoc: TrialJobDoc = {
          status: 'processing', stage: 3, output_data: null, error_data: null, name: '',
        };

        describe('ProcessingScreen', () => {
          it('renders steps 1-2 done, step 3 active, steps 4-5 waiting for stage=3', () => {
            render(<ProcessingScreen jobDoc={baseJobDoc} snapshotError={null} />);
            const nodes = document.querySelectorAll('.step-node');
            expect(nodes[0].className).toContain('done');
            expect(nodes[1].className).toContain('done');
            expect(nodes[2].className).toContain('active');
            expect(nodes[3].className).toContain('waiting');
            expect(nodes[4].className).toContain('waiting');
            expect(screen.getByText('Simplifying language')).toBeInTheDocument();
          });

          it('renders the reconnect message instead of the step list when snapshotError is set', () => {
            render(<ProcessingScreen jobDoc={baseJobDoc} snapshotError={new Error('boom')} />);
            expect(screen.getByText(/lost connection/i)).toBeInTheDocument();
            expect(document.querySelector('.step-list')).toBeNull();
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- ProcessingScreen` passes both cases.

---

### Task 15 — `components/ResultScreen.tsx`, plus tests

   - Files: `frontend-trial/src/components/ResultScreen.tsx` (new),
     `frontend-trial/src/tests/components/ResultScreen.test.tsx` (new)
   - Changes: Per PRD §4.11 (visual layout, error sub-view, PRD §9 Q6's "Try again"
     button scoped to the error sub-view only) and §4.14 (exact field sourcing for
     title/date/score).
     1. `ResultScreen.tsx`:
        ```tsx
        import { useEffect, useRef } from 'react';
        import CarePlanView from '@main/components/CarePlanView';
        import type { CarePlanInternal } from '@main/types/envelope';
        import type { TrialJobDoc } from '../hooks/useTrialJobSnapshot';
        import { deleteTrialJob } from '../api/trialApi';
        import { downloadReport } from '../utils/downloadReport';
        import { trackEvent } from '../analytics/ga';

        interface ResultScreenProps {
          jobDoc: TrialJobDoc;
          jobId: string | null;
          deletedRef: React.MutableRefObject<Set<string>>;
          onRestart: () => void;
        }

        export default function ResultScreen({ jobDoc, jobId, deletedRef, onRestart }: ResultScreenProps) {
          const trackedRef = useRef(false);

          // Primary DELETE trigger (PRD §4.13, layer 1) — fires once, on reaching this
          // screen, sharing deletedRef with TrialPage's safety-net trigger so the two
          // can never double-fire in a way that matters (DELETE is idempotent anyway).
          useEffect(() => {
            if (!jobId || deletedRef.current.has(jobId)) return;
            deletedRef.current.add(jobId);
            void deleteTrialJob(jobId).catch(() => { /* best-effort */ });
          }, [jobId, deletedRef]);

          const outputData = jobDoc.output_data as unknown as CarePlanInternal | null;

          useEffect(() => {
            if (trackedRef.current) return;
            if (jobDoc.status === 'completed' && outputData) {
              trackedRef.current = true;
              const combined = outputData.grading.entries.filter(e => e.name === 'combined');
              const before = combined.find(e => e.target === 'before')?.grade ?? 0;
              const after = combined.find(e => e.target === 'after')?.grade ?? 0;
              trackEvent({
                name: 'simplify_complete',
                params: {
                  total_duration_ms: outputData.metrics.total_duration_ms ?? 0,
                  score_before: before,
                  score_after: after,
                },
              });
            } else if (jobDoc.status === 'error' && jobDoc.error_data) {
              trackedRef.current = true;
              trackEvent({
                name: 'simplify_pipeline_error',
                params: { error_code: jobDoc.error_data.code, stage_reached: jobDoc.stage },
              });
            }
          }, [jobDoc, outputData]);

          if (jobDoc.status === 'error') {
            const message = jobDoc.error_data?.user_hint ?? jobDoc.error_data?.message
              ?? 'Something went wrong while creating your care plan.';
            return (
              <div className="glass-card">
                <p className="error-box">{message}</p>
                <button className="cta-btn" onClick={onRestart}>Try again</button>
              </div>
            );
          }

          if (!outputData) return null;

          const { care_plan, grading, metrics } = outputData;
          const combined = grading.entries.filter(e => e.name === 'combined');
          const before = combined.find(e => e.target === 'before')?.grade;
          const after = combined.find(e => e.target === 'after')?.grade;
          const formattedDate = new Date(metrics.created_at).toLocaleDateString('en-US', {
            month: 'long', day: 'numeric', year: 'numeric',
          });

          return (
            <div>
              <h1>{jobDoc.name}</h1>
              <p>{formattedDate}</p>
              {before != null && after != null && (
                <p className="score-widget">{before} → {after}</p>
              )}
              <CarePlanView result={care_plan} grading={grading} />
              <button className="cta-btn" onClick={() => downloadReport(care_plan, grading)}>
                Download report
              </button>
            </div>
          );
        }
        ```
        If Task 2's fallback was invoked, both `@main/...` imports become `../shared/...`.
        No "Another care plan" button anywhere in the success sub-view — confirmed absent
        per PRD §4.11's explicit exclusion list.
     2. `ResultScreen.test.tsx` (per PRD §7):
        ```tsx
        import { describe, it, expect, vi, beforeEach } from 'vitest';
        import { render, screen } from '@testing-library/react';
        import userEvent from '@testing-library/user-event';

        const deleteTrialJobMock = vi.fn().mockResolvedValue(undefined);
        vi.mock('../../api/trialApi', () => ({ deleteTrialJob: (...a: unknown[]) => deleteTrialJobMock(...a) }));
        const downloadReportMock = vi.fn();
        vi.mock('../../utils/downloadReport', () => ({ downloadReport: (...a: unknown[]) => downloadReportMock(...a) }));
        vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

        import ResultScreen from '../../components/ResultScreen';
        import type { TrialJobDoc } from '../../hooks/useTrialJobSnapshot';

        const completedJobDoc: TrialJobDoc = {
          status: 'completed', stage: 5, name: 'Jan 5 Care Plan', error_data: null,
          output_data: {
            metrics: { created_at: '2026-01-05T10:00:00Z', total_duration_ms: 12000 },
            grading: { entries: [
              { name: 'combined', target: 'before', grade: 42, grade_breakdown: null, reasoning: null },
              { name: 'combined', target: 'after', grade: 78, grade_breakdown: null, reasoning: null },
            ], enabled: true, graded_at: null },
            care_plan: { doc_type: 'care_plan', urgency: 'normal', version: '1.2', summary: 'Rest up.', reason_for_visit: [], diagnosis: { details: [] }, medications: [], tests: [], procedures: [], other: [], follow_up: [], warning_signs: [], questions: [], low_priority: [] },
          },
        };

        const errorJobDoc: TrialJobDoc = {
          status: 'error', stage: 2, name: '', output_data: null,
          error_data: { code: 'INTERNAL_ERROR', message: 'boom', user_hint: 'Something went wrong. Please try again.', retryable: true, details: null, timestamp: '2026-01-05T10:00:00Z' },
        };

        describe('ResultScreen', () => {
          const deletedRef = { current: new Set<string>() };
          beforeEach(() => { deletedRef.current = new Set(); deleteTrialJobMock.mockClear(); downloadReportMock.mockClear(); });

          it('renders title, date (no prefix), before->after score, and CarePlanView content on completed', () => {
            render(<ResultScreen jobDoc={completedJobDoc} jobId="job-1" deletedRef={deletedRef} onRestart={vi.fn()} />);
            expect(screen.getByText('Jan 5 Care Plan')).toBeInTheDocument();
            expect(screen.getByText('January 5, 2026')).toBeInTheDocument();
            expect(screen.queryByText(/Simplified on/)).not.toBeInTheDocument();
            expect(screen.getByText('42 → 78')).toBeInTheDocument();
            expect(screen.getByText('Rest up.')).toBeInTheDocument();
          });

          it('renders the error message and Try again button on error, calling onRestart when clicked', async () => {
            const onRestart = vi.fn();
            const user = userEvent.setup();
            render(<ResultScreen jobDoc={errorJobDoc} jobId="job-2" deletedRef={deletedRef} onRestart={onRestart} />);
            expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();
            await user.click(screen.getByRole('button', { name: 'Try again' }));
            expect(onRestart).toHaveBeenCalledOnce();
          });

          it('calls downloadReport when "Download report" is clicked', async () => {
            const user = userEvent.setup();
            render(<ResultScreen jobDoc={completedJobDoc} jobId="job-1" deletedRef={deletedRef} onRestart={vi.fn()} />);
            await user.click(screen.getByRole('button', { name: 'Download report' }));
            expect(downloadReportMock).toHaveBeenCalledOnce();
          });
        });
        ```
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- ResultScreen` passes all three cases.

---

### Task 16 — `pages/TrialPage.tsx` — the state-machine orchestrator

   - Files: `frontend-trial/src/pages/TrialPage.tsx` (new)
   - Changes: Per PRD §4.9. Wires together every hook and screen from Tasks 6, 8, 11–15.
     Deliberately **no fourth `'error'` literal on `AppState`** — a pipeline failure is
     `jobDoc.status === 'error'` observed while `AppState === 'result'`, rendered as
     `ResultScreen`'s error sub-view (Task 15), mirroring `frontend/`'s own
     `CarePlanJobPage.tsx` branching pattern.
     ```tsx
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
     If Task 2's fallback was invoked, `@main/types/carePlan` becomes `../shared/types/carePlan`.
   - Acceptance criteria:
     - `cd frontend-trial && npx tsc -b` exits 0 with this file added.
     - No test file for this task — it's a thin composition of already-tested pieces;
       its behavior is exercised end-to-end once `App.tsx` (Task 18) wires it into the
       router (no PRD §4.1 test file lists a `TrialPage.test.tsx`).

---

### Task 17 — `pages/PrivacyPage.tsx` / `pages/TermsPage.tsx`, plus tests

   - Files: `frontend-trial/src/pages/PrivacyPage.tsx` (new),
     `frontend-trial/src/pages/TermsPage.tsx` (new),
     `frontend-trial/src/tests/pages/PrivacyPage.test.tsx` (new),
     `frontend-trial/src/tests/pages/TermsPage.test.tsx` (new)
   - Changes: Per PRD §4.16. Thin shells — the actual Privacy Policy / Terms &
     Conditions body copy is SP4's to author and drop in later (D8: pending the user's
     review); this task only builds the route contract SP4 designed against.
     1. `PrivacyPage.tsx`:
        ```tsx
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
     2. `TermsPage.tsx` (identical structure, "Terms & Conditions" placeholder):
        ```tsx
        import { Link } from 'react-router-dom';

        export default function TermsPage() {
          return (
            <div className="legal-page">
              <Link to="/">← Back</Link>
              <article>{/* SP4's Terms & Conditions copy renders here */}</article>
            </div>
          );
        }
        ```
     3. `PrivacyPage.test.tsx` (per PRD §7 — trivial render-smoke, no specific copy
        asserted since it doesn't exist in this repo yet):
        ```tsx
        import { describe, it, expect } from 'vitest';
        import { render, screen } from '@testing-library/react';
        import { MemoryRouter } from 'react-router-dom';
        import PrivacyPage from '../../pages/PrivacyPage';

        describe('PrivacyPage', () => {
          it('renders without throwing and contains a Back link to /', () => {
            render(<MemoryRouter><PrivacyPage /></MemoryRouter>);
            const link = screen.getByRole('link', { name: /back/i });
            expect(link).toHaveAttribute('href', '/');
          });
        });
        ```
     4. `TermsPage.test.tsx` (identical structure, importing `TermsPage`).
   - Acceptance criteria:
     - `cd frontend-trial && npm run test -- PrivacyPage TermsPage` passes both files.

---

### Task 18 — `App.tsx` — real router (replaces Task 2's placeholder), GA page tracking

   - Files: `frontend-trial/src/App.tsx` (overwrite the Task 2 placeholder)
   - Changes: Per PRD §4.16. `send_page_view: false` is set in `ga.ts` (Task 5)
     specifically because this is an SPA — GA4's own automatic `page_view` only fires
     once on initial script load, so every `page_view` (including the first) is sent
     manually here.
     ```tsx
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
   - Acceptance criteria:
     - `cd frontend-trial && npm run build` exits 0 (the real, final `tsc -b && vite build`
       — this is the first time the full app builds end-to-end, not just the Task 2
       placeholder).
     - `cd frontend-trial && npm run dev &` then `curl -s http://localhost:5174/ | grep -q '<div id="root">'`
       confirms the dev server serves the app on the pinned port 5174 (kill the
       background process after checking).

---

### Task 19 — CI: add the `frontend-trial` job to `.github/workflows/ci.yml`

   - Files: `.github/workflows/ci.yml`
   - Changes: Per PRD §7 — a third job, mirroring the existing `frontend` job exactly
     (same Node setup, `npm ci`, `npm run test`), `working-directory: frontend-trial`.
     Add after the existing `frontend:` job:
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
     No `tsc -b`/`npm run build` step here — deliberately deferred (PRD §9 Q7): the
     existing `frontend` job also only runs `npm run test`, so adding a build/typecheck
     step to only the new job would be an inconsistency between the two jobs worth
     deciding for both at once, not unilaterally here. Do not touch the `backend` or
     `frontend` jobs in this task.
   - Acceptance criteria:
     - `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
       parses without error.
     - `git diff .github/workflows/ci.yml` shows only an added `frontend-trial:` job —
       the existing `backend`/`frontend` jobs are byte-for-byte unchanged.
     - `frontend-trial/package-lock.json` exists (generated by Task 2's `npm install`) so
       the new job's `cache-dependency-path` resolves.

---

### Task 20 — Run the SP3-scoped test suite and fix any regressions

   - Files: any file that fails — diagnose before editing; do not touch files outside
     `frontend-trial/` (this SP's whole scope) without a clear regression reason.
   - Changes / steps: Unlike the backend suite, `frontend-trial/`'s entire test suite
     *is* this SP's scope (a brand-new project with nothing pre-existing to accidentally
     over-run), so run the whole thing:
     ```bash
     cd frontend-trial && npm run test
     ```
     For each failure, read the error and fix with a minimal targeted edit; re-run until
     green. Also re-run the full build once more as a final gate:
     ```bash
     cd frontend-trial && npm run build
     ```
   - Acceptance criteria:
     - `npm run test` exits 0 — every test file listed in Tasks 3, 5–10, 13–15, 17 passes.
     - `npm run build` exits 0.
     - `git diff --stat` (repo root) shows changes confined to `frontend-trial/**` (all
       new) and `.github/workflows/ci.yml` — no file under `frontend/` or `backend/` is
       touched.

---

## Summary of what requires you (not a dev agent)

1. **Confirm the `VITE_GA_MEASUREMENT_ID` env var name with SP4 before merging (PRD §8
   item 2).** SP4's PRD already picked this exact name and wired it into `deploy.yml`'s
   trial build step — Task 1/Task 5 above use the same name, so this should already
   match, but it's the one cross-SP string that must agree byte-for-byte or GA silently
   never initializes in production. A quick diff of the literal string
   `VITE_GA_MEASUREMENT_ID` between this SP's code and SP4's `deploy.yml` once SP4 lands
   is enough to confirm — not something a dev agent can verify alone since SP4's
   `deploy.yml` doesn't exist on this branch yet.
2. **This SP cannot be deployed standalone (PRD §8 item 3).** `frontend-trial/dist` has
   nowhere to be served until SP4 lands its Hosting config (root `firebase.json`'s
   `trial` target). Land this SP's code freely — it's harmless and unreferenced by
   anything until then — but its actual go-live is coupled to SP4.
3. **If Task 2's `@main` alias fallback branch was taken:** the PRD's own §9 Q2 records
   "no drift detection" as the accepted risk for the resulting `frontend-trial/src/shared/`
   copies — no further action needed from you beyond being aware that those five files
   no longer auto-update when `frontend/src`'s originals change.
4. **No other manual/owner-only step exists in this PRD.** PRD §8 lists exactly the two
   items above (env var name confirmation, deploy coupling) and both are cross-SP
   coordination points, not GCP/IAM/console actions — nothing in this PRD requires a
   `gcloud`/`firebase` command or a console click to land the code.
