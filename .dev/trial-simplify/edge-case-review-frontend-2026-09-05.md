# Edge-case review — frontend-trial (2026-09-05)

Scope: `frontend-trial/src/**`, `frontend-trial/vite.config.ts`, `index.html`, `package.json`,
`.env.example`, `eslint.config.js`, and every module reachable through the `@main` alias
(`frontend/src/types/{errors,carePlan,envelope}.ts`, `frontend/src/components/{CarePlanView,MedicalTerm}.tsx`,
`frontend/src/utils/buildPdfHtml.ts`). Branch `users/tejitpabari/trial-optimizations`.

Method: full read of every file in scope, plus the relevant slice of `backend/routes/trial.py`,
`backend/routes/worker.py`, and `backend/utils/constants.py` where needed to judge whether a
client-visible gap is actually reachable in production. `npx tsc --noEmit` is clean; `npm test -- --run`
passes all 79 tests across 18 files. The existing trial test suite is unusually thorough — several
scenarios explicitly named in the review brief (StrictMode double-invoke idempotency, doc-deleted-under-
a-live-listener, XSS via `buildPdfHtml`, popup-blocked, `window.opener` nulling, rate-limit copy vs.
backend constant) are already covered by tests and verified correct by direct reading; those are called
out below as "Verified, no issue" rather than padded into findings.

---

## BLOCKING

None found. No XSS, no auth-bypass, no data leak, and no "you must sign in" message reaches the user
anywhere in `frontend-trial` or the `@main` surface it imports.

---

## SHOULD FIX

### 1. A job stuck in `processing` forever has no client-side timeout or escape button
**File:** `frontend-trial/src/components/ProcessingScreen.tsx:70-102` (the non-error, non-`jobGone`
branch), `frontend-trial/src/hooks/useTrialJobSnapshot.ts`

**Scenario:** the worker process dies hard (OOM-killed, container crash) after Cloud Tasks has
dispatched the task but before `backend/routes/worker.py`'s outer `try/except Exception` (line 254) gets
a chance to run — a hard process kill bypasses Python exception handling entirely, so `fail_job()` is
never called and the Firestore doc never reaches a terminal `status`. The only backstop is the
document's `expires_at` field (`backend/routes/trial.py:108`, `now + timedelta(hours=JOB_TTL_HOURS=1)`),
which is a Firestore native-TTL field: it marks the doc *eligible* for deletion after 1 hour, but
Firestore's documented TTL SLA is "deletion typically occurs within 24 hours of expiration," not at the
expiry instant. So a genuinely stuck job can leave a real visitor staring at the "Creating your
simplified care plan…" step list — with a spinner-like `active` step and no message that anything is
wrong — for up to roughly a day.

Every *other* terminal-ish state in `ProcessingScreen` (`jobExists === false`, `snapshotError`) already
renders a "Start over" button (lines 73-79, 80-87). The plain in-flight branch (lines 89-99) renders
none — by design, since the intent is "the TTL is the real safety net" (see the comment above
`useUnloadCleanup`), but that safety net's own latency is up to ~24h, far longer than a user will
plausibly wait without a signal.

**Fix:** add a bounded client-side watchdog (e.g. via a `startedAt` timestamp kept in `TrialPage` and a
few-minutes threshold) that, independent of the Firestore listener, surfaces a "this is taking longer
than expected" message with a manual "Start over" button once elapsed time crosses a threshold well
under the TTL backstop.

### 2. `useAnonAuth`'s `pending` state has no timeout and no retry affordance
**File:** `frontend-trial/src/hooks/useAnonAuth.ts:13-34`, `frontend-trial/src/components/UploadScreen.tsx:84,128-139`

**Scenario:** if the `signInAnonymously(firebaseAuth)` promise kicked off on mount never settles (or
settles without `onAuthStateChanged` ever firing with a non-null user — the only path that flips
`authState` to `'ready'`), `authState` stays `'pending'` indefinitely. `UploadScreen` renders "Getting
ready…" (`role="status"`) in that state and nothing else — the Retry button only exists in the
`authState === 'error'` branch (line 128). `disabled` (line 84) keeps the Simplify button disabled the
whole time. There is no path back to `'error'` from a hung `'pending'`, so the user is stuck with no
actionable UI element, and no way to know their session simply never started. Contrast this with
`trialApi.ts::getCurrentUser`, which deliberately treats a 5s hang as a signal to self-heal
(`waitForAuthUser` + one retry) — `useAnonAuth` has no analogous bound.

**Fix:** add a bounded timeout in `useAnonAuth` (e.g. 8-10s) that flips `authState` to `'error'` if still
`pending`, so the existing Retry button becomes reachable instead of leaving the user on an unbounded
"Getting ready…" screen.

### 3. No accessible announcement or focus management across screen transitions
**Files:** `frontend-trial/src/pages/TrialPage.tsx` (state machine driving `upload → processing →
result`), `frontend-trial/src/components/ProcessingScreen.tsx`, `ResultScreen.tsx`

**Scenario:** `TrialPage` swaps entire subtrees (`UploadScreen` → `ProcessingScreen` → `ResultScreen`) by
conditionally rendering different components; nothing moves focus to the new screen's heading, and
nothing wraps the changing content (step list progressing 1→5, or the eventual "Your care plan"
heading) in an `aria-live` region. `grep` across `frontend-trial/src` for `aria-live` /
`role="status"` / `.focus(` turns up exactly one hit (`UploadScreen.tsx:136`'s "Getting ready…" hint) —
none of the actually time-varying content (pipeline step progress, the transition into results) is
announced. A screen-reader user gets no auditory feedback that their submission was accepted, that
processing is progressing, or that results have finished loading; they would need to manually re-explore
the page to discover the state changed.

**Fix:** wrap the step list (or at minimum the currently-active step's label) in `aria-live="polite"`,
and move focus to the new screen's `<h1>`/heading (or a dedicated visually-hidden live region) on each
`appState` transition in `TrialPage`.

---

## NICE TO HAVE

### 4. `CarePlanView`'s "Copy" button has no error handling or success feedback
**File:** `frontend/src/components/CarePlanView.tsx:271` (via `@main`, rendered inside
`ResultScreen.tsx:117`)

```
onClick={() => navigator.clipboard.writeText(q)}
```

`navigator.clipboard` can be `undefined` (very old WebViews, some locked-down/embedded contexts, non-
secure origins) and `writeText` can reject (permission denied, e.g. Safari without a preceding user-
activation edge case, or clipboard-write blocked by a Permissions-Policy). Since this runs inside a
synchronous `onClick`, a thrown/rejected result is an uncaught exception in an event handler — outside
render, so it does **not** trip the app's `ErrorBoundary` and does not blank the page — but nothing tells
the user whether the copy actually worked, silently failing on the affected browsers. Low impact (worst
case is a no-op click), but easy to harden: wrap in `.catch()` and show a brief inline confirmation/failure
state.

### 5. Privacy Policy wording says deletion is gated on the user closing/navigating away; the code deletes as soon as results are displayed
**Files:** `frontend-trial/src/pages/PrivacyPage.tsx:67-72` vs. `frontend-trial/src/components/ResultScreen.tsx:23-27`

The policy states: "The job record ... is deleted as soon as your browser has finished displaying your
results **and you close or navigate away from the page**." The actual primary delete trigger fires
unconditionally the moment `ResultScreen` mounts (i.e., the instant results are shown), independent of
whether the user ever closes or navigates away — `useUnloadCleanup`'s `visibilitychange`/`pagehide`
triggers are only the secondary safety net for jobs that never reach `result`. The implementation is
strictly more protective than the copy implies (data is gone even sooner than promised), so this is not
a privacy problem, just an inaccurate description of the trigger condition — worth tightening the copy so
it matches the actual (better) behavior.

### 6. No guard for a missing/malformed `VITE_API_PROCESSING_URL` at build/runtime
**Files:** `frontend-trial/src/api/firebase.ts:16`, consumed at `frontend-trial/src/api/trialApi.ts:81,103`

If `VITE_API_PROCESSING_URL` is unset, `API_URL` is `undefined`, and `` `${API_URL}/trial/jobs` `` becomes
the literal string `"undefined/trial/jobs"` — a same-origin relative path that 404s against the static
hosting bucket rather than reaching the backend. The resulting error surfaced to the user is the generic
`Request failed: 404 Not Found` (from `createTrialJob`'s fallback branch, `trialApi.ts:89`), which gives a
developer debugging a fresh deployment no signal that an env var is missing. Separately, if the value
*is* set but carries a trailing slash, the same template produces a double slash
(`https://host//trial/jobs`), which most Flask route tables will 404 on. Recommend an explicit
"missing required env var" check at module load (loud console error, or a build-time assertion), and
stripping any trailing slash from `API_URL` before use.

### 7. `MAX_TEXT_LENGTH` is not actually the same limit as the backend for surrogate-pair-heavy text
**Files:** `frontend-trial/src/utils/validateFiles.ts:7-9,49-55` vs. `backend/utils/constants.py`'s
`Constants.Uploads.MAX_TEXT_LENGTH`

The comment says the two constants are meant to mirror each other, and both are `500_000`. But
`validateText`'s check is JS `text.length`, which counts UTF-16 code units (an emoji outside the BMP, or
many combining-character sequences, count as 2 units), while the backend's `len(text_input)`
(`backend/routes/trial.py:39`) counts Python Unicode code points (1 per emoji). For emoji-/surrogate-pair-
heavy paste content the client's effective cap is *smaller* in real character terms than the server's —
never the reverse, so this can't produce a "client accepts, server 400s" surprise, only an occasional
"client says too long" when the server would in fact have accepted it. Cosmetic/UX-only; not a functional
break.

### 8. Raw Firebase Auth SDK error text can reach the on-screen error box
**File:** `frontend-trial/src/components/UploadScreen.tsx:105-118`

If `getAuthHeader()` (called from `createTrialJob`, `trialApi.ts:80`) throws because `user.getIdToken()`
itself fails (e.g. `auth/network-request-failed`, `auth/quota-exceeded`), the error is a plain `Error`,
not an `ApiError`, so it falls through to `else if (err instanceof Error) message = err.message;`
(`UploadScreen.tsx:111-113`) and Firebase's own message text (e.g. `"Firebase: Error
(auth/network-request-failed)."`) is shown verbatim to the trial visitor. It never says "sign in" (so the
hard no-login requirement is respected), but it does leak the underlying tech stack/SDK naming to a
non-technical audience. Consider mapping known Firebase auth error codes to a generic
"Something went wrong starting your session, please try again" message before display.

---

## Verified, no issue (checked explicitly to avoid false positives)

- **XSS / injection:** `frontend/src/components/CarePlanView.tsx` renders every model-derived string as a
  JSX text child (React-escaped) — no `dangerouslySetInnerHTML` anywhere in the `@main` surface reachable
  from the trial app. `frontend/src/utils/buildPdfHtml.ts` runs every interpolated field (including
  nested arrays/objects) through `escapeHtml()` before string-concatenating into the `document.write`'d
  report; verified by reading all ~20 call sites, and confirmed by
  `frontend-trial/src/tests/utils/downloadReport.test.ts`/`aliasSmoke.test.ts`.
- **`window.opener` leak on download:** `downloadReport.ts` explicitly nulls `printWindow.opener` right
  after `window.open`, and a dedicated test (`downloadReport.test.ts`, "defense-in-depth vs stored XSS")
  asserts this.
- **Popup blocked:** handled with an `alert()` fallback and no attempt to `document.write` on a null
  window; tested.
- **Malformed/partial care-plan payloads:** `ResultScreen.tsx` defensively optional-chains/defaults every
  field, has an explicit non-blank fallback for `completed` + `null output_data` (line 75-85), and wraps
  `CarePlanView` in its own local `ErrorBoundary` (line 116) distinct from the app-root one — verified
  against `ResultScreen.test.tsx`'s "renders without crashing when grading is missing entirely" and
  "Ghost Job" cases, both passing.
- **Doc deleted out from under a live listener:** `TrialPage.tsx` captures `finalJobDoc` once a terminal
  status is seen and tears down the live listener (`useTrialJobSnapshot(finalJobDoc ? null : jobId)`), so
  a subsequent `exists: false` from the backend's own delete can never blank the result screen — this
  exact regression is covered by three tests in `TrialPage.test.tsx`.
- **StrictMode double-invocation:** `useUnloadCleanup`'s ref-based `deletedRef` and `ProcessingScreen`'s
  `seenActive`/`seenDone` Sets make the effects idempotent under dev double-mount; job *creation* happens
  only inside a button `onClick`, never inside a `useEffect`, so StrictMode cannot cause a double job
  creation regardless.
- **`useUnloadCleanup` correctness:** deliberately does **not** delete on `visibilitychange→hidden` while
  `processing` (only while `result`), specifically to avoid killing a still-running job when a user
  backgrounds the tab or locks their phone — this is a documented, deliberate fix in the code's own
  comments and is covered by dedicated tests for every combination of appState × trigger.
- **Auth self-heal hangs/unhandled rejections:** `trialApi.ts::getCurrentUser` and `waitForAuthUser` never
  reject (every path resolves, including the bounded-timeout branch); `signInAnonymously` failures inside
  `getCurrentUser`'s self-heal are caught and logged, never rethrown early. Confirmed by five passing
  tests in `trialApi.test.ts` covering the happy path, the wait-then-succeed race, the self-heal path, and
  the fully-exhausted failure path (which throws only the generic, no-"sign-in" message).
- **Token expiry mid-job:** both `createTrialJob` and `deleteTrialJob` call `user.getIdToken()` fresh each
  time, which the Firebase SDK auto-refreshes as needed — no manual refresh logic required or missing.
- **Rate-limit copy consistency:** `TermsPage.tsx` says "currently 5 per hour"; `backend/utils/constants.py`
  sets `RATE_LIMIT_PER_IP_PER_HOUR = 5`. No drift.
- **Analytics privacy:** every event in `analytics/ga.ts`'s `TrialEvent` union carries only counts,
  categories, durations, and enum-like values (e.g. `file_types` is a sorted, deduped list of
  *extensions*, never filenames; `error_code` is a fixed backend code, never message text). No
  document content, filename, or job id is ever passed to `trackEvent`. Matches the Privacy Policy's
  explicit claim ("We do not send any document content, filenames, or care-plan text to Google
  Analytics").
- **Extension casing / no-extension files:** `validateFiles.ts` lowercases the extension before checking
  membership, so `FILE.PDF` is accepted; a file with no `.` (e.g. `record`) correctly falls into the
  "unsupported file type" branch rather than crashing or silently passing.
- **Keyboard operability of the drop zone:** the real `<input type="file">` is visually hidden
  (`aria-hidden`, `tabIndex={-1}`), but it's triggered by a genuine `<button>` (`upload-zone-trigger`),
  so Tab + Enter/Space opens the native file picker with no custom keydown handling required.
