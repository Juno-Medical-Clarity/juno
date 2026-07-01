# PRD: SP10 — Frontend Legacy-Shim Retirement

**Sub-project:** SP10  
**Branch context:** `users/tejitpabari/llm-code-check`  
**Date:** 2026-06-29  
**Status:** Planning — no implementation started  
**Dependencies:** SP01 (unified error system), SP07 (pipeline output shape + SSE retirement)

---

## 1. Problem

The frontend accumulated several shims, dead stubs, and dual-shape branches to bridge the old and new backend contracts as the backend was being incrementally unified. Now that SP01 and SP07 are completing the backend contract, those bridge artifacts must be retired. Leaving them in place creates maintenance noise, type-level confusion (a dead exported type that implies an alternative exists), and the risk that a future developer wires a new callsite to the deprecated shape instead of the unified one.

Specific pain points:

1. **`useJobSnapshot.ts` exports a dead dual-shape type.** `JobErrorData` (lines 14–38) was created to accommodate both the old "SP2 ErrorDetail format" (with `details`, `timestamp`, `path`) and the new "JunoError-classified" format (with `user_hint`, `retryable`, `detail`). The `JobDoc.error_data` field is already typed as `FirestoreJobError | null` — the correct unified shape — making `JobErrorData` an unreferenced export. No file in the project imports it.

2. **`CarePlanJobPage.tsx` carries a stale legacy-format comment.** Line 411 has `// Use "details" field from FirestoreJobError / legacy ErrorDetail formats`. Now that `FirestoreJobError` is the sole Firestore error shape, the "legacy ErrorDetail" half of that comment is dead. The code itself is correct; only the comment misleads.

3. **`normalizeOutput.ts` exists only to convert old flat Firestore documents.** The `isLegacyShape` guard converts documents written before the `CarePlanInternal` envelope wrapper was introduced. Whether any such documents still exist in production is unknown (see §9 Q1). If none remain, the entire file can be deleted and `CarePlanJobPage.tsx` can cast `output_data` directly.

4. **`CarePlanPage.tsx:49` has a dead `processingIds` stub.** The variable is always `undefined` and passed as an optional prop to `Sidebar`. The `useJobStatuses` hook that was supposed to back it already exists at `src/api/useJobStatuses.ts` — the wire was never pulled. This is the one item in SP10 that is a **wire-up**, not a removal.

5. **`logger.ts` docstring advertises an unimplemented `flush()` method.** There is no `flush()` method on the `Logger` class; only a multi-line TODO comment in the module docstring describes a future batched-upload feature. The comment sets a false expectation and should be removed.

---

## 2. Goals

1. Delete the dead `JobErrorData` type export from `useJobSnapshot.ts`.
2. Remove the "legacy ErrorDetail formats" reference from the comment in `CarePlanJobPage.tsx`.
3. Conditionally retire `normalizeOutput.ts` once old Firestore documents are confirmed gone (see §9 Q1).
4. Wire `processingIds` in `CarePlanPage.tsx` to the already-existing `useJobStatuses` hook.
5. Remove the `flush()` TODO paragraph from `logger.ts`'s module docstring.
6. (Optional) Propose a component split for `CarePlanJobPage.tsx`.

The codebase must continue to pass `tsc --noEmit` (strict, `noUnusedLocals`, `noUnusedParameters`) and all existing Vitest tests after each change.

---

## 3. Non-Goals

- No backend changes of any kind. SP10 only consumes the contracts finalized by SP01 and SP07.
- No UI behavior changes. The visible output of all pages must be identical before and after.
- No new features. The optional component split (§6 item 6) is a refactor-only, not a feature addition.
- No changes to `src/types/errors.ts`. `ApiErrorDetail`, `ApiError`, and `FirestoreJobError` are already correct; SP01 declared them stable and SP10 does not re-derive them.
- No implementation of the logger's flush/remote-ingest feature. Removing the comment is all that is in scope.
- No migration of old Firestore documents — that is backend territory (SP05/SP07).

---

## 4. Architecture Decisions

### 4a. Remove Dead `JobErrorData` Export

**File:** `frontend/src/hooks/useJobSnapshot.ts`

Lines 14–38 define and export `JobErrorData`, a union-shaped type created to accommodate two different error formats. The grep search confirms zero import sites for this type. `JobDoc.error_data` (line 44) is already correctly typed as `FirestoreJobError | null` from `src/types/errors.ts`, which is the canonical shape after SP01.

**Before (lines 14–38):**
```typescript
/**
 * Worker-written error_data dict stored in Firestore on job failure.
 *
 * New rich format (JunoError-classified jobs):
 *   { code, message, user_hint, retryable, detail }
 *
 * Legacy SP2 ErrorDetail format (older jobs):
 *   { code, message, details?, timestamp?, path? }
 *
 * Both formats include `code` and `message`; new fields are optional so
 * the frontend degrades gracefully for docs written before this schema.
 */
export type JobErrorData = {
  /** Canonical error code, e.g. "LLM_MAX_TOKENS" */
  code: string;
  /** Developer-facing description of the error. */
  message: string;
  /** User-facing actionable hint (new rich format). */
  user_hint?: string;
  /** Whether a retry of the same request is likely to succeed (new rich format). */
  retryable?: boolean;
  /** Exception string or extra technical context (new rich format). */
  detail?: string;
  /** Legacy SP2 ErrorDetail field — specific detail string. */
  details?: string;
  /** Legacy SP2 ErrorDetail field — ISO-8601 UTC timestamp. */
  timestamp?: string;
  /** Legacy SP2 ErrorDetail field — request path; null for worker errors. */
  path?: string | null;
};
```

**After:** Delete lines 14–38 entirely. No other change in this file.

`JobDoc` (line 40) and `useJobSnapshot` (line 53) are unaffected; `JobDoc.error_data` is already typed via the imported `FirestoreJobError`. The `import type { FirestoreJobError }` on line 5 remains because it is used by `JobDoc`.

---

### 4b. Drop Stale Comment in `CarePlanJobPage.tsx`

**File:** `frontend/src/pages/care-plan/CarePlanJobPage.tsx`

After SP01 lands, `jobDoc.error_data` is always `FirestoreJobError | null`. The `details` field is the canonical technical-detail field in `FirestoreJobError`; no "legacy ErrorDetail" alternative exists. The comment on line 411 must be updated to reflect this.

**Before (line 411):**
```typescript
    // Use "details" field from FirestoreJobError / legacy ErrorDetail formats
    const technicalDetail = errData?.details ?? null;
```

**After:**
```typescript
    // Technical detail string from FirestoreJobError.
    const technicalDetail = errData?.details ?? null;
```

Additionally, `retryable` in `FirestoreJobError` is typed `boolean` (non-optional). The current code reads it with optional chaining (`errData?.retryable`), producing `boolean | undefined`. After the shim removal this can be tightened:

**Before (line 409–410):**
```typescript
    // retryable is a boolean; check !== undefined so false renders correctly
    const retryable = errData?.retryable;
```

**After:**
```typescript
    const retryable = errData?.retryable ?? false;
```

The JSX that consumes `retryable` already renders correctly for both true and false values; narrowing the type to `boolean` (instead of `boolean | undefined`) only tightens the contract.

---

### 4c. Conditional Retirement of `normalizeOutput.ts`

**File:** `frontend/src/utils/normalizeOutput.ts`  
**Gated on:** Q1 resolution (§9)

`normalizeOutput.ts` exists solely to normalise old Firestore documents that lack the `care_plan` envelope key. If confirmed that no such documents remain in `care_plan_outputs`:

**Step 1 — Delete `frontend/src/utils/normalizeOutput.ts` entirely.**

**Step 2 — Update `CarePlanJobPage.tsx` (line 5 import + line 59 call site):**

Before (lines 5 and 57–60):
```typescript
import { normalizeCarePlanOutput } from '../../utils/normalizeOutput';
// ...
const baseResult: CarePlanInternal | null =
  jobDoc?.status === 'completed' && jobDoc.output_data
    ? normalizeCarePlanOutput(jobDoc.output_data)
    : null;
```

After:
```typescript
// (import removed)
// ...
const baseResult: CarePlanInternal | null =
  jobDoc?.status === 'completed' && jobDoc.output_data
    ? (jobDoc.output_data as CarePlanInternal)
    : null;
```

The cast is safe because SP07 pins the pipeline to always writing the `CarePlanInternal` envelope shape. If a legacy doc is somehow encountered, the downstream render will produce a type error at runtime (missing fields), which is the appropriate outcome once migration is confirmed complete.

**Step 3 — Delete `frontend/src/tests/utils/normalizeOutput.test.ts`.** The single test exercises legacy-shape conversion; it has no purpose once `normalizeOutput.ts` is removed.

**If Q1 resolves as "old docs still exist":** keep `normalizeOutput.ts` and this task is deferred. Do not partially retire it. Coordinate the full deletion with the backend team's Firestore migration plan (SP05/SP07).

---

### 4d. Wire `processingIds` in `CarePlanPage.tsx`

**File:** `frontend/src/pages/care-plan/CarePlanPage.tsx`

`useJobStatuses` at `frontend/src/api/useJobStatuses.ts` already implements the Firestore real-time subscription that powers processing spinners in the Sidebar. The TODO comment (lines 45–49) was written before the hook existed. The hook is now ready to use.

**Before (lines 45–49):**
```typescript
  // processingIds: wired from SP1's useJobStatuses hook.
  // When SP1 lands, import useJobStatuses from '../../api/useJobStatuses'
  // and compute this set from statuses Map (status === 'not_started' | 'processing').
  // Until then, undefined causes Sidebar to show no spinners (graceful degradation).
  const processingIds: Set<string> | undefined = undefined; // TODO: wire SP1
```

**After:**
```typescript
  const { statuses } = useJobStatuses();
  const processingIds = new Set(
    [...statuses.entries()]
      .filter(([, status]) => status === 'not_started' || status === 'processing')
      .map(([id]) => id),
  );
```

Add the import at the top of `CarePlanPage.tsx`:
```typescript
import { useJobStatuses } from '../../api/useJobStatuses';
```

The `Sidebar` component accepts `processingIds?: Set<string>` (already typed at `Sidebar/Sidebar.tsx:15`). Passing a live `Set<string>` instead of `undefined` causes the Sidebar to show a spinner for jobs that are in `not_started` or `processing` state — the feature the stub was placeholding.

**Why wire instead of remove:** The Sidebar prop is designed for exactly this; the hook is production-ready; the TypeScript types are already wired. Removing the prop would leave a useful real-time Sidebar feature forever dormant.

---

### 4e. Remove `flush()` TODO from `logger.ts`

**File:** `frontend/src/utils/logger.ts`

The module docstring (lines 1–11) describes a future `flush()` method that does not exist. There is no stub method, no partial implementation, no caller. The comment is aspirational documentation for a feature with no scheduled delivery. Removing it does not affect behavior.

**Before (lines 1–11):**
```typescript
/**
 * Juno frontend logger.
 *
 * In development: pretty-prints structured log entries to the browser console.
 * In production: console output only (browser logs stay local).
 *
 * TODO: In a future iteration, add a `flush()` method that POSTs batched log
 * entries to a `/log` endpoint on the backend, or integrates with Firebase
 * Analytics for UX event tracking. The LogEntry interface is already structured
 * to support either approach without changes to call sites.
 */
```

**After:**
```typescript
/**
 * Juno frontend logger.
 *
 * In development: pretty-prints structured log entries to the browser console.
 * In production: console output only (browser logs stay local).
 */
```

If remote log ingestion is ever prioritised, it should be implemented as a new feature ticket with its own design, not found via a stale comment.

---

### 4f. (Optional) Component Split for `CarePlanJobPage.tsx`

**File:** `frontend/src/pages/care-plan/CarePlanJobPage.tsx` (~544 lines)

The file renders three mutually-exclusive states — loading (trivial), error (lines 402–518), completed (lines 199–400), and processing/in-progress (lines 520–544) — all in a single component. This is a common React pattern that works fine at this size, but extracting the two large branches would improve readability and enable independent testing.

**Proposed extraction:**

| New file | Lines extracted | Approximate size |
|---|---|---|
| `frontend/src/pages/care-plan/CarePlanJobErrorView.tsx` | 402–518 (error state) | ~120 lines |
| `frontend/src/pages/care-plan/CarePlanJobResultView.tsx` | 199–400 (completed state) | ~200 lines |

The processing/in-progress state (lines 520–544, ~25 lines) is small enough to remain inline.

`CarePlanJobPage.tsx` becomes a thin orchestrator: reads `jobDoc`, dispatches to the correct view, handles shared state (`gradingOverride`, `showSplitView`, share/comment state). Shared handlers (`handleRunGrading`, `handleToggleShare`, `handleSaveComment`) can be passed as props or co-located with the subcomponent that owns them.

**This is explicitly optional and not required for SP10.** The component is functional; the split is a code-quality improvement. Mark in §9 whether to include it in this SP or defer.

---

## 5. API Change Summary

SP10 consumes, but does not change, two backend contracts:

| Contract | Source SP | What SP10 relies on |
|---|---|---|
| `FirestoreJobError` Firestore shape | SP01 | `{ code, message, user_hint, details, retryable, timestamp }` — all fields present, no legacy alternatives |
| `CarePlanInternal` output envelope | SP07 | All completed job `output_data` docs conform to the envelope shape (`metrics`, `input`, `grading`, `care_plan`) — no legacy flat docs remain |

SP10 makes no HTTP API changes and no Firestore schema changes.

---

## 6. Frontend Change Summary

| File | Change | Gated on |
|---|---|---|
| `frontend/src/hooks/useJobSnapshot.ts` | Delete exported `JobErrorData` type and its 14-line block comment (lines 14–38) | SP01 merged |
| `frontend/src/pages/care-plan/CarePlanJobPage.tsx` | Update comment on line 411; tighten `retryable` from `boolean \| undefined` to `boolean` via `?? false` | SP01 merged |
| `frontend/src/utils/normalizeOutput.ts` | Delete entire file | Q1 resolved as "no legacy docs" + SP07 merged |
| `frontend/src/tests/utils/normalizeOutput.test.ts` | Delete (tests the deleted file) | Same as above |
| `frontend/src/pages/care-plan/CarePlanJobPage.tsx` | Remove `normalizeCarePlanOutput` import; replace call with direct cast | Same as above |
| `frontend/src/pages/care-plan/CarePlanPage.tsx` | Import `useJobStatuses`; replace dead `undefined` stub with live computed `Set<string>` | None (hook already exists) |
| `frontend/src/utils/logger.ts` | Remove 4-line `flush()` TODO paragraph from module docstring | None |
| `frontend/src/pages/care-plan/CarePlanJobErrorView.tsx` *(optional)* | New file — extracted error-state JSX from `CarePlanJobPage.tsx` | Q2 resolved as "split now" |
| `frontend/src/pages/care-plan/CarePlanJobResultView.tsx` *(optional)* | New file — extracted completed-state JSX from `CarePlanJobPage.tsx` | Q2 resolved as "split now" |

Changes with no gating dependency (`processingIds` wire-up and logger docstring) can land before SP01 and SP07 are merged.

---

## 7. Testing

### Automated tests (Vitest)

- **`tsc --noEmit`** must pass after every change. The `noUnusedLocals` flag will catch any import that becomes orphaned (e.g., the `normalizeCarePlanOutput` import in `CarePlanJobPage.tsx` after §4c).
- **Existing tests must stay green.** No new test logic is needed for the deletions and comment cleanups.
- **For `processingIds` wiring (§4d):** Add a test in `frontend/src/tests/pages/care-plan/CarePlanPage.test.tsx` (or the existing Sidebar test suite) asserting that when `useJobStatuses` returns a map with a `processing` entry, the Sidebar receives a non-empty `processingIds` set. This can be done by mocking `useJobStatuses`.
- **Delete `normalizeOutput.test.ts`** when `normalizeOutput.ts` is deleted (§4c). Do not leave an orphaned test file.

### Manual checks

1. Navigate to a job in `error` status. Confirm the error card renders correctly (user message, error code badge, retryable indicator, technical detail box) after the `CarePlanJobPage.tsx` comment cleanup.
2. With the `processingIds` wiring active: submit a new care plan job, then return to `CarePlanPage`. Confirm the Sidebar shows a spinner on the in-progress job.
3. Navigate to a completed job. Confirm the output renders identically before and after the `normalizeOutput.ts` retirement (once Q1 is resolved).

---

## 8. Manual Intervention Required

**If Q1 resolves as "old-shape docs exist":** A Firestore data migration must be run before `normalizeOutput.ts` can be deleted. That migration is backend territory (SP05/SP07) and must be coordinated with the backend team. SP10 cannot complete the `normalizeOutput.ts` deletion unilaterally.

No Cloud Run config changes, no GCS changes, no Firebase console actions are required for the non-gated items (§4d, §4e).

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Are there any Firestore `care_plan_outputs` documents in production that lack the `care_plan` top-level key (i.e., the legacy flat shape that `isLegacyShape()` detects)? Backend team (SP05/SP07) must confirm before `normalizeOutput.ts` is deleted. | [RESOLVED: nothing legacy remains; we do NOT inspect Firestore and assume no legacy documents exist, so `normalizeOutput.ts` is retired unconditionally (not gated). Per TASKS.md "USER DECISIONS applied" note.] |
| Q2 | Should the `CarePlanJobPage.tsx` component split (§4f) be included in this SP or deferred to a follow-on? | [RESOLVED: the `CarePlanJobPage.tsx` component split is INCLUDED in this SP. Per TASKS.md "USER DECISIONS applied" note.] |
| Q3 | Retire the listed legacy error/output shims (`JobErrorData`, stale comment, `processingIds` stub, logger TODO) once SP01 and SP07 land. | [RESOLVED: yes, retire all non-gated items in SP10; gate `normalizeOutput.ts` retirement on Q1 + SP07 merge] |
| Q4 | Sequencing: SP10 non-gated changes (`processingIds`, `logger.ts`) may land before SP01/SP07 without risk. SP10 gated changes must wait for SP01 (error shape) and SP07 (output shape). | [RESOLVED: implement in two commits — (a) no-dependency cleanups first, (b) SP01/SP07-gated deletions after both SPs are merged] |
| Q5 | Does the `useJobStatuses` hook need a loading state guard in `CarePlanPage.tsx` before passing `processingIds` to Sidebar? | [RESOLVED: no — `useJobStatuses` initialises with an empty `Map` and the Sidebar handles an empty `Set` gracefully (no spinners shown). No loading gate needed.] |
