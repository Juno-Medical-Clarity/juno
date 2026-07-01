# SP10 Frontend Legacy-Shim Retirement — TASKS

## Prerequisites

Purpose: retire every frontend legacy shim, dead stub, dual-shape branch, and stale legacy-format comment left over from the incremental backend-contract unification, and wire the one item that was placeheld (`processingIds`).

This is the **last** sub-project. It assumes SP01–SP09 are all fully complete and deployed: the backend now writes only the unified `FirestoreJobError` error shape and the `CarePlanInternal` output envelope, and no legacy/flat documents remain anywhere.

> Note (USER DECISIONS applied): Q1 — nothing legacy remains; we do NOT inspect Firestore and assume no legacy documents exist, so `normalizeOutput.ts` is retired unconditionally (not gated). Q2 — the `CarePlanJobPage.tsx` component split is INCLUDED in this SP. Q3 — retire everything legacy, no back-compat, removals are not gated on "is it still used". Q4 — all SPs run in strict numeric order; SP01–SP09 are complete and deployed, so every gated change in the PRD is now ungated.

> Note: The PRD's "two-commit, gate-on-merge" sequencing (PRD §9 Q4) is superseded — since SP01–SP09 are already merged and deployed, all removals proceed now. Each task below is still its own commit for clean review and bisectability.

All work is under `frontend/`. After every task, `tsc --noEmit` (strict, `noUnusedLocals`, `noUnusedParameters`) and the full Vitest suite must stay green.

---

## Tasks

### Task 10.1: Delete dead `JobErrorData` type from `useJobSnapshot.ts`

- **Goal:** Remove the unreferenced dual-shape `JobErrorData` type export and its block comment. The canonical error shape is `FirestoreJobError`, already used by `JobDoc.error_data`.
- **Files:**
  - `frontend/src/hooks/useJobSnapshot.ts`
- **Steps:**
  1. In `frontend/src/hooks/useJobSnapshot.ts`, delete the entire block from the docstring comment on **line 9** (`/**` beginning "Worker-written error_data dict…") through the closing `};` of the `export type JobErrorData = { … }` on **line 38**, inclusive. (PRD §4a cited lines 14–38; the actual block including its leading docstring is lines 9–38.)
  2. Leave one blank line between the `export type JobStatus = …` declaration (line 7) and the `export interface JobDoc {` declaration so the file stays cleanly formatted.
  3. Do NOT touch the `import type { FirestoreJobError } from '../types/errors';` on line 5 — it is still used by `JobDoc.error_data` (line 44).
  4. Do NOT touch `JobDoc`, `useJobSnapshot`, or any other code in the file.
- **Acceptance:**
  - `grep -rn "JobErrorData" frontend/src` returns no matches.
  - `useJobSnapshot.ts` still exports `JobStatus`, `JobDoc`, and `useJobSnapshot`.
  - `npx tsc --noEmit` passes (no unused-import error for `FirestoreJobError`).
- **Commit:** `refactor(frontend): remove dead JobErrorData type from useJobSnapshot`

---

### Task 10.2: Remove `flush()` TODO from `logger.ts` docstring

- **Goal:** Delete the aspirational `flush()` / Firebase-Analytics TODO paragraph from the `logger.ts` module docstring. No such method exists; the comment sets a false expectation.
- **Files:**
  - `frontend/src/utils/logger.ts`
- **Steps:**
  1. In `frontend/src/utils/logger.ts`, in the module docstring (lines 1–11), delete the paragraph beginning `* TODO: In a future iteration, add a \`flush()\` method…` through the line ending `…without changes to call sites.` (lines 7–10).
  2. Keep the docstring as:
     ```typescript
     /**
      * Juno frontend logger.
      *
      * In development: pretty-prints structured log entries to the browser console.
      * In production: console output only (browser logs stay local).
      */
     ```
  3. Do NOT change any code in the file. The `LogEntry` interface, `Logger` class, `_emit`, and the singleton export are all out of scope.
  4. Leave the in-body comment at line 113–114 ("any future log ingestion pipeline") as-is — it is descriptive of current behavior, not a TODO for an unimplemented method.
- **Acceptance:**
  - `grep -n "flush" frontend/src/utils/logger.ts` returns no matches.
  - The docstring is exactly the 6-line block above.
  - `npx tsc --noEmit` passes; logger behavior is unchanged.
- **Commit:** `docs(frontend): remove unimplemented flush() TODO from logger docstring`

---

### Task 10.3: Wire `processingIds` in `CarePlanPage.tsx` to `useJobStatuses`

- **Goal:** Replace the dead `processingIds = undefined` stub with a live `Set<string>` computed from the existing `useJobStatuses` hook, so the Sidebar shows spinners for `not_started` / `processing` jobs.
- **Files:**
  - `frontend/src/pages/care-plan/CarePlanPage.tsx`
  - `frontend/src/api/useJobStatuses.ts` (read-only reference — already implemented, do not edit)
- **Steps:**
  1. In `frontend/src/pages/care-plan/CarePlanPage.tsx`, add an import near the other `../../api/...` imports (e.g. after line 13's `import { createCarePlanJob, createBatchJobs } from '../../api/jobs';`):
     ```typescript
     import { useJobStatuses } from '../../api/useJobStatuses';
     ```
  2. Replace the dead stub block at lines 45–49 (the 4-line `// processingIds: …` comment plus `const processingIds: Set<string> | undefined = undefined; // TODO: wire SP1`) with:
     ```typescript
     const { statuses } = useJobStatuses();
     const processingIds = new Set(
       [...statuses.entries()]
         .filter(([, status]) => status === 'not_started' || status === 'processing')
         .map(([id]) => id),
     );
     ```
  3. Leave the `<Sidebar … processingIds={processingIds} />` JSX (lines 138–143) unchanged — the prop wiring already exists and is typed `processingIds?: Set<string>`.
  4. Confirm `useJobStatuses` initializes with an empty `Map` (it does, line 13 of `useJobStatuses.ts`), so no loading-state guard is needed (PRD §9 Q5: resolved "no guard").
- **Acceptance:**
  - `grep -n "TODO: wire SP1" frontend/src` returns no matches.
  - `CarePlanPage.tsx` imports and calls `useJobStatuses`; `processingIds` is a `Set<string>` (no longer `undefined`).
  - `npx tsc --noEmit` passes.
  - Test added in Task 10.7 passes.
- **Commit:** `feat(frontend): wire processingIds from useJobStatuses into Sidebar`

---

### Task 10.4: Clean up legacy error-format comment and tighten `retryable` in `CarePlanJobPage.tsx`

- **Goal:** Remove the stale "legacy ErrorDetail formats" reference and tighten `retryable` to a non-optional `boolean`, now that `FirestoreJobError` is the sole Firestore error shape.
- **Files:**
  - `frontend/src/pages/care-plan/CarePlanJobPage.tsx`
- **Steps:**
  1. In the `jobDoc.status === 'error'` branch (starts line 402), replace the comment on **line 410**:
     ```typescript
     // Use "details" field from FirestoreJobError / legacy ErrorDetail formats
     ```
     with:
     ```typescript
     // Technical detail string from FirestoreJobError.
     ```
  2. Replace lines 408–409:
     ```typescript
     // retryable is a boolean; check !== undefined so false renders correctly
     const retryable = errData?.retryable;
     ```
     with:
     ```typescript
     const retryable = errData?.retryable ?? false;
     ```
  3. **Important consistency fix:** Because `retryable` is now always a `boolean` (never `undefined`), the JSX guard on **line 446** (`{retryable !== undefined && (`) would now always render the "Retryable" indicator even when `error_data` is `null`. Change that guard to key off the presence of error data instead, so the indicator only shows when there is a structured error. Replace:
     ```tsx
     {retryable !== undefined && (
     ```
     with:
     ```tsx
     {errData && (
     ```
     The inner `{retryable ? 'Yes' : 'No'}` rendering (line 448) stays unchanged and now reads correctly for both `true` and `false`.
     > Note: `errData` is `jobDoc.error_data` (line 403), typed `FirestoreJobError | null`. Gating on `errData` preserves the original behavior (indicator hidden when there is no error payload) while satisfying the tightened type. This addresses a subtle regression the PRD's §4b snippet did not call out.
  4. Do NOT change any other line in this file in this task. The component split is Task 10.6; the `normalizeOutput` removal is Task 10.5.
- **Acceptance:**
  - `grep -n "legacy ErrorDetail" frontend/src` returns no matches.
  - The error card still renders user message, error-code badge, retryable indicator (only when `error_data` is present), dev message, and technical-detail box.
  - `retryable` has type `boolean` (verify by hovering / `tsc` — no `boolean | undefined`).
  - `npx tsc --noEmit` passes.
- **Commit:** `refactor(frontend): drop legacy error comment and tighten retryable in CarePlanJobPage`

---

### Task 10.5: Retire `normalizeOutput.ts` and cast `output_data` directly

- **Goal:** Delete the legacy flat-document normalizer entirely (no legacy docs remain — USER DECISION Q1) and cast `jobDoc.output_data` directly to `CarePlanInternal` in `CarePlanJobPage.tsx`.
- **Files:**
  - `frontend/src/utils/normalizeOutput.ts` (delete)
  - `frontend/src/tests/utils/normalizeOutput.test.ts` (delete)
  - `frontend/src/pages/care-plan/CarePlanJobPage.tsx` (edit)
- **Steps:**
  1. Delete the file `frontend/src/utils/normalizeOutput.ts` (`git rm frontend/src/utils/normalizeOutput.ts`).
  2. Delete the file `frontend/src/tests/utils/normalizeOutput.test.ts` (`git rm frontend/src/tests/utils/normalizeOutput.test.ts`) — its sole test exercises legacy-shape conversion and has no purpose once the normalizer is gone.
  3. In `frontend/src/pages/care-plan/CarePlanJobPage.tsx`, remove the import on **line 5**:
     ```typescript
     import { normalizeCarePlanOutput } from '../../utils/normalizeOutput';
     ```
  4. Replace the `baseResult` call site at lines 57–60:
     ```typescript
     const baseResult: CarePlanInternal | null =
       jobDoc?.status === 'completed' && jobDoc.output_data
         ? normalizeCarePlanOutput(jobDoc.output_data)
         : null;
     ```
     with:
     ```typescript
     const baseResult: CarePlanInternal | null =
       jobDoc?.status === 'completed' && jobDoc.output_data
         ? (jobDoc.output_data as CarePlanInternal)
         : null;
     ```
  5. Confirm `CarePlanInternal` is already imported (it is — line 17). Do not add a duplicate import.
  6. `grep` to ensure no other importer exists before deleting: `grep -rn "normalizeOutput\|normalizeCarePlanOutput\|isLegacyShape" frontend/src` must return zero matches after the edits.
- **Acceptance:**
  - `frontend/src/utils/normalizeOutput.ts` and `frontend/src/tests/utils/normalizeOutput.test.ts` no longer exist.
  - `grep -rn "normalizeOutput\|normalizeCarePlanOutput\|isLegacyShape" frontend/src` returns no matches.
  - `npx tsc --noEmit` passes (the now-orphaned import is removed, so `noUnusedLocals` is satisfied).
  - Completed-job output renders identically (manual check #3 in Verification).
- **Commit:** `refactor(frontend): delete normalizeOutput legacy normalizer and cast output_data directly`

---

### Task 10.6: Split `CarePlanJobPage.tsx` into error / result view components

- **Goal:** Extract the two large render branches of `CarePlanJobPage.tsx` into dedicated components, leaving `CarePlanJobPage` as a thin orchestrator. Refactor only — no behavior or UI change. (USER DECISION Q2: include the split in this SP.)
- **Files:**
  - `frontend/src/pages/care-plan/CarePlanJobErrorView.tsx` (new)
  - `frontend/src/pages/care-plan/CarePlanJobResultView.tsx` (new)
  - `frontend/src/pages/care-plan/CarePlanJobPage.tsx` (edit)
- **Steps:**
  1. **Do this task AFTER Tasks 10.4 and 10.5** so the extracted JSX already reflects the cleaned-up comment, tightened `retryable`, the `errData`-gated retryable indicator, and the direct `output_data` cast.
  2. Create `frontend/src/pages/care-plan/CarePlanJobErrorView.tsx`:
     - Move the entire `if (jobDoc.status === 'error') { … }` block body (current lines 402–518: the `errData`/`userMessage`/`errorCode`/`devMessage`/`retryable`/`technicalDetail`/`sessionId`/`traceId`/URL derivations and the returned JSX) into a function component `CarePlanJobErrorView`.
     - Props it needs: `errorData: FirestoreJobError | null`, `sessionId: string | null`, `traceId: string | null`, and `isPublicView: boolean` (controls whether `<NavBar />` renders). Derive all the local consts (`userMessage`, `errorCode`, `devMessage`, `retryable`, `technicalDetail`, `sessionLogUrl`, `traceUrl`) inside the component from those props.
     - Import `NavBar` from `'../../components/NavBar'` and `import type { FirestoreJobError } from '../../types/errors'`.
  3. Create `frontend/src/pages/care-plan/CarePlanJobResultView.tsx`:
     - Move the `if (jobDoc.status === 'completed' && result) { … }` block body (current lines 199–400: the full completed-state JSX including the result header, `CarePlanView`, session/trace links, note card, download bar, and the `SplitView` at lines 386–397) into a function component `CarePlanJobResultView`.
     - This branch reads many parent values and handlers. Pass them as props: `result: CarePlanInternal`, `jobDoc: JobDoc`, `id: string | undefined`, `isPublicView: boolean`, `user` (the auth user object, typed to match `useAuth`'s return), plus the handlers and UI state it uses: `gradingLoading`, `gradingError`, `shareLoading`, `showSplitView`, `setShowSplitView`, `showCommentArea`, `setShowCommentArea`, `commentText`, `setCommentText`, `commentSaving`, `commentSaved`, `handleSaveComment`, `handleDownloadJson`, `handleDownloadPdf`, `handleRunGrading`, `handleToggleShare`.
     - Import `NavBar`, `Sidebar`, `CarePlanView`, `OutputGradingCard`, `SplitView`, `useNavigate`, and the necessary types.
     > Note: The result view has the largest prop surface. Define a single `CarePlanJobResultViewProps` interface so the call site stays readable. Keep the handlers and `useState` declarations in the parent `CarePlanJobPage` (they coordinate `gradingOverride` and persistence); pass them down. Do not lift `useJobSnapshot` or `useAuth` into the child.
  4. In `CarePlanJobPage.tsx`:
     - Keep all hooks, derived state (`baseResult`, `result`), and handlers in the parent.
     - Replace the completed-state `return (…)` (lines 199–400) with `return <CarePlanJobResultView … />;` passing the props above.
     - Replace the error-state `return (…)` (lines 402–518) with:
       ```tsx
       if (jobDoc.status === 'error') {
         return (
           <CarePlanJobErrorView
             errorData={jobDoc.error_data}
             sessionId={jobDoc.session_id ?? null}
             traceId={jobDoc.trace_id ?? null}
             isPublicView={isPublicView}
           />
         );
       }
       ```
     - Leave the `loading`, `error`, `!jobDoc`, private-view, and processing/in-progress branches (lines 154–197 and 520–544) inline in the parent — they are small.
     - Add imports for the two new components at the top of the file.
  5. Remove any imports in `CarePlanJobPage.tsx` that are now used only by the extracted children (e.g. `SplitView`, `OutputGradingCard`, `CarePlanView` if no longer referenced in the parent). Let `tsc --noEmit` (`noUnusedLocals`) drive which imports to drop — run it and remove whatever it flags.
- **Acceptance:**
  - `frontend/src/pages/care-plan/CarePlanJobErrorView.tsx` and `CarePlanJobResultView.tsx` exist and are imported by `CarePlanJobPage.tsx`.
  - `CarePlanJobPage.tsx` no longer contains the inline completed-state or error-state JSX bodies.
  - `npx tsc --noEmit` passes with zero unused-import / unused-param errors.
  - All existing Vitest tests for the care-plan pages still pass (UI output unchanged).
  - Manual checks #1 (error card) and #3 (completed output) render identically to before the split.
- **Commit:** `refactor(frontend): split CarePlanJobPage into error and result view components`

---

### Task 10.7: Add Vitest coverage for `processingIds` wiring

- **Goal:** Lock in the `processingIds` behavior from Task 10.3 with a test that mocks `useJobStatuses` and asserts the Sidebar receives a non-empty `processingIds` set when a job is in a processing state.
- **Files:**
  - `frontend/src/tests/pages/care-plan/CarePlanPage.test.tsx` (create or extend if it already exists)
- **Steps:**
  1. Check whether `frontend/src/tests/pages/care-plan/CarePlanPage.test.tsx` exists. If it does, add a new `it(...)` case to it; if not, create it.
  2. Mock `'../../../api/useJobStatuses'` (adjust the relative depth to match the test's location) so `useJobStatuses` returns `{ statuses: new Map([['job-a', 'processing'], ['job-b', 'completed'], ['job-c', 'not_started']]) }`.
  3. Mock the `Sidebar` component (`'../../../components/Sidebar'`) to capture the `processingIds` prop it receives (e.g. render its size into the DOM, or assert via a `vi.fn()` spy passed through the mock).
  4. Render `CarePlanPage` (wrapped in whatever router/context providers the existing care-plan tests use — mirror an existing test's setup).
  5. Assert the captured `processingIds` is a `Set` containing `'job-a'` and `'job-c'` and NOT `'job-b'` (size 2).
  6. Mock any other modules `CarePlanPage` imports that hit network/Firebase (`'../../../api/jobs'`, Firebase) the same way existing tests do, so the render is hermetic.
  > Note: Match the import-mock style and provider wrappers already used in the frontend test suite (look at a sibling test under `frontend/src/tests/` for the established pattern) rather than inventing a new harness.
- **Acceptance:**
  - `npx vitest run` includes the new test and it passes.
  - The test fails if `processingIds` is reverted to `undefined` (sanity-check by temporarily reverting Task 10.3 locally — do not commit the revert).
- **Commit:** `test(frontend): assert processingIds set is computed from useJobStatuses`

---

## Verification

Run all commands from `frontend/`:

```bash
# 1. Type check — strict, noUnusedLocals, noUnusedParameters
npx tsc --noEmit

# 2. Full unit/component test suite
npx vitest run

# 3. Production build (ensures no build-time-only breakage)
npm run build

# 4. Lint (if configured in the repo)
npm run lint
```

Targeted greps (all must return zero matches):

```bash
grep -rn "JobErrorData" frontend/src
grep -rn "legacy ErrorDetail" frontend/src
grep -rn "TODO: wire SP1" frontend/src
grep -n  "flush" frontend/src/utils/logger.ts
grep -rn "normalizeOutput\|normalizeCarePlanOutput\|isLegacyShape" frontend/src
```

### Definition of done

- All seven tasks committed (one conventional commit each), in order.
- `npx tsc --noEmit`, `npx vitest run`, and `npm run build` all pass.
- Every targeted grep above returns no matches.
- `frontend/src/utils/normalizeOutput.ts` and `frontend/src/tests/utils/normalizeOutput.test.ts` are deleted.
- `CarePlanJobErrorView.tsx` and `CarePlanJobResultView.tsx` exist; `CarePlanJobPage.tsx` is a thin orchestrator.
- `CarePlanPage.tsx` passes a live `Set<string>` to `Sidebar.processingIds`, covered by a Vitest test.
- No backend, API, Firestore-schema, or UI-behavior changes: every page renders identically to before SP10 (manual checks #1–#3 from PRD §7).
