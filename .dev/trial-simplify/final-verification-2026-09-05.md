# Final pre-release verification — trial pathway (2026-09-05 / 2026-09-06)

**Branch:** `users/tejitpabari/trial-optimizations` @ `eac5dc84` (0 commits behind
`origin/main`; diff reviewed is `git diff origin/main...HEAD`, 49 files, +5493/-175).

**Method:** independent re-derivation, not a review of the earlier agents' summaries.
Every claim below was either (a) reproduced by actually running the suite/command, or
(b) confirmed by reading the current code and, where practical, exercising it directly
against a live Flask test client. Nothing here is copied from
`edge-case-review-backend-2026-09-05.md`, `edge-case-review-frontend-2026-09-05.md`, or
`scenario-validation-2026-09-05.md` without independent verification.

---

## 1. Full suite results (exact numbers)

### Backend — `cd backend && python3 -m pytest tests/ -q`
```
684 passed, 1 warning, 24 subtests passed in ~105-107s
Coverage: 94% (9941 stmts, 611 missed)
```
The one warning is a pre-existing `PyPDF2 is deprecated` `DeprecationWarning` from the
`PyPDF2` package itself — unrelated to this branch's changes. Ran twice (before and
after my one comment-only fix below); identical result both times.

### `frontend-trial` — tsc / lint / test / build
```
npx tsc --noEmit         → clean, no output, exit 0
npm run lint             → clean (eslint .), no output
npm test -- --run        → Test Files 19 passed (19); Tests 103 passed (103)
npm run build            → tsc -b && vite build — succeeded
                             (only a pre-existing "chunk >500kB" advisory warning,
                              not an error; unrelated to this diff)
```

### `frontend` (main app) — test / tsc / build
```
npm test -- --run        → Test Files 23 passed (23); Tests 189 passed (189)
npx tsc --noEmit         → clean, no output, exit 0
npm run build            → tsc -b && vite build — succeeded
                             (same pre-existing chunk-size advisory, unrelated)
```

**No failures in any of the three suites** — so there was nothing to root-cause against
`origin/main` via a scratch worktree; that fallback step wasn't needed.

---

## 2. Integration checks (combined-diff interaction risk)

| # | Check | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | `resolve_uploaded_files` call sites keep their prior behavior | **PASS** | `routes/care_plan_jobs.py:68` calls it with **no overrides** → falls back to `Constants.Uploads` defaults (10 files / 10MB per file / 25MB aggregate, `enforce_per_file_limit=True`, `tolerate_unusable_files=False`) — bit-for-bit the pre-existing main-app behavior. `routes/trial.py:72-78` passes `max_file_count=5, max_aggregate_bytes=10MB, enforce_per_file_limit=False, tolerate_unusable_files=True` — exactly the stated trial limits (5 files / 10MB aggregate / no per-file cap). |
| 2 | `MAX_TEXT_BYTES=350_000` scope | **CONFIRMED REGRESSION RISK — flagged, not fixed (product decision)** | See §3 below. |
| 3 | Frontend `MAX_TEXT_BYTES`/`MAX_TEXT_LENGTH` mirror vs backend, client never more permissive | **PASS** | `frontend-trial/src/utils/validateFiles.ts`: `MAX_TEXT_LENGTH = 500_000`, `MAX_TEXT_BYTES = 350_000` — byte-for-byte identical to `backend/utils/constants.py`'s `Constants.Uploads.MAX_TEXT_LENGTH`/`MAX_TEXT_BYTES`. Both checks run client-side before submit; client rejects at the same thresholds the server enforces, so the client is never more permissive. File limits (`MAX_FILES=5`, `MAX_AGGREGATE_BYTES=10MB`, no per-file cap) also match `Constants.Trial` exactly. |
| 4 | `clear_input_text` fires on every trial terminal path, never for main-app jobs, and nothing reads `input_text` after | **PASS** | Traced every `complete_job`/`fail_job` call site in `routes/worker.py` (timeout at `_check_timeout`, Athena API error, `EMPTY_DOCUMENT` guard, pipeline error, "no result", successful completion, and the outer catch-all `except Exception`) — **all eight** pass `clear_input_text=is_trial` (or `getattr(job, "is_trial", False)` in the outer catch-all). `is_trial` is only ever `True` for jobs created via `routes/trial.py`, so main-app jobs never clear it. Downstream: `grep -rn "input_text"` across `backend/` shows the **only** reader is `resolve_input_from_job_doc` (`services/care_plan_input.py:415`, `return job.input_text or ""`), which is called **only** before the top-of-`execute_job` terminal-state check would have already returned early — a job whose `input_text` was cleared is always already `completed`/`error`, so that early-return path (line ~64: `if job.status in ("completed", "error"): return "", 200`) fires first and `resolve_input_from_job_doc` is never reached. `grep -rn "input_text"` in `frontend-trial/src` returns **zero** matches — the client never reads this field at all. |
| 5 | Worker processing-lease idempotency vs. actual Cloud Tasks retry config | **PASS** | `Constants.Deadlines`: `SINGLE_JOB_INTERNAL_DEADLINE_S=270` < `JOB_TIMEOUT_SECONDS_SINGLE=300` (the `dispatch_deadline` passed to `enqueue_job` for both `routes/trial.py` and `routes/care_plan_jobs.py`); `BATCH_ITEM_INTERNAL_DEADLINE_S=870` < `JOB_TIMEOUT_SECONDS_BATCH=900` (batch's dispatch deadline). A legitimate job self-times-out via `_check_timeout` **before** Cloud Tasks' own external dispatch deadline could fire, so the redelivery-skip branch (`lease_elapsed_s < deadline_s`) is never hit for a healthy job. If the worker process crashes outright (no HTTP response at all), Cloud Tasks won't retry until its own `dispatch_deadline` (300s/900s) elapses — by which point `lease_elapsed_s` (~300s+) already exceeds the internal `deadline_s` (270s/870s), so the very next redelivery correctly falls into the "lease expired — allow retry" branch, not the skip branch. No legitimate job can get stuck: the 30s margin in both cases guarantees the self-timeout wins the race under normal operation, and the lease-expiry path (verified in `tests/routes/test_worker.py::test_processing_job_past_lease_window_is_retried_to_completion`) covers the crash case. Cloud Tasks queue creation (`.github/workflows/deploy.yml`, unchanged by this diff) sets only `--max-concurrent-dispatches=5 --max-dispatches-per-second=2`, no explicit `--max-attempts`/backoff — so it uses Cloud Tasks' defaults (unlimited attempts, exponential backoff capped at 1hr), meaning a genuinely broken job keeps retrying rather than being dropped. This is pre-existing infra, not touched by this diff — noted for completeness, not a defect. |
| 6 | `HTTPException` re-raise + `MAX_CONTENT_LENGTH=30MB` + 413 handler | **PASS (verified empirically against a live Flask test client, not just by reading code)** | Ran `app.py`'s actual Flask app under `flask_app.test_client()`: a body over `MAX_CONTENT_LENGTH` posted to `/care_plan/jobs` returns **413**, `content_type=application/json`, body `{"error": {"code": "FILE_TOO_LARGE", ...}}` — the standard error envelope, not Werkzeug's HTML page. Also checked the re-raise didn't perturb other codes: `GET /does-not-exist` still → 404 JSON (`ENDPOINT_NOT_FOUND`); `POST /care_plan/jobs` with no auth header still → 401 JSON. `routes/trial.py` and `routes/care_plan_jobs.py` both structure their handlers as inner `try` (catches `ValueError`/`FileNotFoundError`/`JunoError` narrowly) inside an outer `try` that re-raises `HTTPException` before the generic `except Exception → 500` — so `werkzeug.exceptions.RequestEntityTooLarge` (raised lazily when `request.form`/`request.get_json()` first reads an over-limit body) correctly escapes to Flask's `@app.errorhandler(413)` instead of being swallowed as a 500. `backend/tests/utils/test_app_observability.py::test_oversized_body_returns_standard_json_error_envelope_not_raw_413` covers this and passed in the full run. |
| 7 | `MIN_MEANINGFUL_CONTENT_CHARS=20` / `EMPTY_DOCUMENT` doesn't wrongly reject a real short document | **PASS, with one comment-accuracy bug found and fixed** | A realistic short prescription note (`"Take Amoxicillin 500mg\nPO TID x7 days\nDr. Lee"`, 45 chars) clears the 20-char floor easily, as does virtually any real multi-line clinical note. **However**, `utils/constants.py`'s own inline comment justifying the threshold cited `"Take Tylenol BID"` as an example that's `>20 chars` when it is actually **16 characters** — factually wrong, and it would in fact be rejected as `EMPTY_DOCUMENT` if submitted verbatim. Fixed the comment (changed the example to `"Take Tylenol 500mg BID"`, 22 chars, which genuinely clears the floor) — see §4. This does **not** change any runtime behavior; it only corrects a misleading comment. Flagging for the owner: a genuinely terse single-line note under 20 characters (rare, but possible) would still be rejected — this is an inherent property of a fixed character floor on a document-oriented tool, not something I changed. |
| 8 | `VITE_API_PROCESSING_URL` guard can't brick a valid deployment; CI/deploy actually set it | **PASS, verified by building both ways** | With no `VITE_API_PROCESSING_URL` set (matching a machine with no `.env.local`), `npm run build`'s output bundle contains the literal guard-throw string `"VITE_API_PROCESSING_URL is not set..."` — confirming the guard is live and would throw at runtime in that misconfigured case (this is the intended fail-loud behavior, not a bug). Rebuilt with a `.env.local` supplying a real value (`https://worker.example.com`): the build succeeded, the guard's throw branch was dead-code-eliminated, and the literal URL was correctly baked into the bundle. Confirmed `.github/workflows/deploy.yml`, `preview.yml`, and `rollback-production.yml` all set `VITE_API_PROCESSING_URL: ${{ secrets.VITE_API_PROCESSING_URL }}` before their respective builds — every real deploy path supplies the variable. `.github/workflows/ci.yml`'s `frontend-trial` job only runs `npm run test` (not `build`), and the vitest suite exercises the guard directly via `vi.stubEnv` (`src/tests/api/firebase.test.ts`), so CI doesn't need the var set globally. `frontend-trial/.env.example` documents the var. No brick risk in any real path. |

---

## 3. Defect found and NOT fixed — flagged for owner decision

### `MAX_TEXT_BYTES=350_000` silently narrows the main app's effective text limit too

`Constants.Uploads.MAX_TEXT_BYTES` (new, 350,000 UTF-8-encoded bytes) is enforced inside
`validate_extracted_text_length()`, which is now called from **every** text-accepting
path in the app, trial and main app alike:
- `routes/trial.py::_resolve_trial_input` (pasted text) — trial-only, intended.
- `routes/care_plan_jobs.py::_resolve_input_for_job` (pasted text) — **main app**.
- `services/care_plan_input.py::resolve_uploaded_files` (all uploads, both routes) —
  **main app** included.
- `routes/care_plan_jobs.py`'s `doc_id` path (re-extracting a previously stored upload)
  — **main app** only.

Before this branch, the main app's pasted-text check (`routes/care_plan_jobs.py`) was
purely character-based: `len(text_input) > Constants.Uploads.MAX_TEXT_LENGTH` (500,000
chars), confirmed via `git diff origin/main...HEAD -- routes/care_plan_jobs.py` — there
was no byte check at all pre-branch. Now `validate_extracted_text_length` adds a second,
independent gate at 350,000 UTF-8 bytes. For plain ASCII text (1 byte/char), that means
**any main-app document between ~350,001 and 500,000 characters, which previously
succeeded, now fails with a 400** (`INPUT_VALIDATION_ERROR`) it would not have hit
before this branch. Reproduced the arithmetic directly: a 400,000-character ASCII
document encodes to exactly 400,000 UTF-8 bytes — under the old 500,000-char limit, over
the new 350,000-byte one.

I did not find evidence this breaks the bundled `preset-data/` (its `manifest.json` is
185KB of metadata referencing external Athena/CMS data, not raw document text stored
inline), but any real main-app user pasting or uploading a long document in that
350K-500K character range — plausible for a very long chart, a large batch of combined
notes, or a big OCR'd document — will see a new, previously-nonexistent rejection.

**This is exactly the kind of product/judgment call the brief says not to unilaterally
change.** I left it as-is. The intent behind the 350,000-byte figure (Firestore's 1 MiB
document-size ceiling, sized to also leave headroom for a trial job's `output_data`
co-existing with `input_text` before `clear_input_text` runs) is sound *for trial jobs*,
where `input_text` is deleted immediately on completion. It is not obviously sound for
main-app jobs, which have **no** `clear_input_text` and therefore keep `input_text`
(now capped lower) alongside `output_data` in the same Firestore doc for the job's
entire lifetime anyway — the byte math that justifies 350,000 for trial doesn't
translate cleanly to a limit that should also bind the main app.

**Owner decision needed:** either (a) confirm the narrower 350,000-byte limit is
acceptable for main-app users too, or (b) give `validate_extracted_text_length` (or its
call sites) a `max_bytes` override so `routes/care_plan_jobs.py` can keep passing
500,000 as an effective byte-neutral char-only check (or a separately-computed,
main-app-appropriate byte ceiling) while trial keeps the tighter 350,000. No code change
made pending that decision.

---

## 4. Defects found and fixed

Only one clear, in-scope defect was found and fixed — a comment-only correction with no
behavioral change (verified: full backend suite re-run after the edit, still 684
passed):

**`backend/utils/constants.py`** — the comment justifying
`MIN_MEANINGFUL_CONTENT_CHARS=20` claimed `"Take Tylenol BID"` is `>20 chars` as a
"realistic terse clinical note" example; it is actually 16 characters and would itself
be rejected by the very check it was illustrating. Changed the example to
`"Take Tylenol 500mg BID"` (22 characters), which genuinely clears the floor. No
functional/behavioral change — comment only.

No other clear defects were found in the reviewed diff. Everything else checked in §2
either passed cleanly or is a judgment call reported in §3, not a bug to fix.

---

## 5. Owner-only items still outstanding (verified against the actual repo/infra, not just the reports)

Confirmed accurate and complete, cross-checked against
`edge-case-review-backend-2026-09-05.md`'s BLOCKING #3 and the existing
`.dev/trial-simplify/README.md`:

1. ~~**GCS lifecycle rule on `care_plan_trial/`** — not deployed.~~ **[DONE,
   2026-09-06]** — applied to `gs://juno-medical-clarity-backend` via
   `gcloud storage buckets update --lifecycle-file=...` (`Delete` action, `age: 1`,
   `matchesPrefix: ["care_plan_trial/"]`, verified live via `buckets describe`) and
   codified as an idempotent step in `deploy.yml` (`Apply GCS lifecycle rule for trial
   uploads`, in the `deploy-backend` job) so it's re-applied on every production deploy.
   `services/retention.py` needed no changes per the backend review.
2. ~~**Anonymous-account cleanup automation** — the Cloud Run Job
   (`juno-trial-anon-cleanup`), its Cloud Scheduler trigger, and the IAM bindings for it
   are not deployed.~~ **[DONE, 2026-09-06]** — the Cloud Run Job is live at
   `RETENTION_DRY_RUN=false`, the `juno-scheduler-invoker` service account holds
   `roles/run.invoker` on the Job, and the daily `juno-trial-anon-cleanup-daily` Cloud
   Scheduler trigger (`0 4 * * *`, `Etc/UTC`, OAuth-authenticated) is `ENABLED`.
   Verified end-to-end with a forced `gcloud scheduler jobs run`: the scheduler attempt
   returned HTTP 200, a new Job execution completed successfully, and its log line read
   `scanned=6 matched=0 deleted=0 errors=0 dry_run=False` — zero eligible accounts, so
   nothing was deleted. Both the `RETENTION_DRY_RUN=false` value and a create-or-update
   step for the Scheduler trigger are now codified idempotently in `deploy.yml`; the
   one-time SA + IAM binding creation remains documented manual setup.
   `scripts/cleanup_anonymous_users.py` (unit-tested,
   `tests/scripts/test_cleanup_anonymous_users.py`) is now genuinely invoked in
   production.
3. Only the Firestore native TTL policies (`care_plan_outputs.expires_at`,
   `trial_rate_limits.expires_at`) are confirmed active — this is the one retention
   backstop that *is* live.
4. **Legal-copy review** (Privacy Policy / Terms) — still a first draft, not
   lawyer-reviewed (D8, unchanged status from the existing README).
5. `frontend-trial`'s UI does not yet surface the newly-added `skipped_files` field to
   the end user (it's persisted on the job doc and covered by a passing e2e test, but no
   component reads it) — not a regression, just an acknowledged gap per the model's own
   comment ("a future trial UI can show..."). Not blocking.

Net effect: **[UPDATED, 2026-09-06]** item 2 is now also done (item 1, the GCS
lifecycle rule, was already done as of 2026-09-06) — both retention backstops for an
abandoned/never-completed trial upload are now live, closing the gap in the
"no-retention trial" framing given to users. This was flagged BLOCKING in the backend
edge-case review and, at the time of this verification pass, was deliberately not
addressed in code (pure infra/deploy work); that gap has since been closed by the
owner's manual go-live plus this session's CI codification and end-to-end verification.

---

## 6. Release verdict

**[UPDATED, 2026-09-06] Infra blocker cleared — one product decision and legal-copy
review remain before shipping the code as-is.**

- **Code quality / test coverage: READY.** All three suites are 100% green
  (684 / 103 / 189 tests), `tsc`, lint, and both frontend builds are clean, and every
  integration point I could independently verify (upload limits per route, text-length
  enforcement, `clear_input_text` lifecycle, worker lease/retry safety, the 413 path,
  the `VITE_API_PROCESSING_URL` guard) behaves correctly and matches its stated intent.
- **[RESOLVED, 2026-09-06] Former blocker (infra, owner-only):** anonymous-account
  cleanup automation (edge-case review BLOCKING #3) is now deployed and verified
  end-to-end — Cloud Run Job live at `RETENTION_DRY_RUN=false`, Cloud Scheduler trigger
  `ENABLED` and firing successfully via OAuth, a forced run confirming
  `scanned=6 matched=0 deleted=0`. Combined with the GCS lifecycle rule (already done
  2026-09-06, §5 item 1), the "no-retention trial" claim made to users is now actually
  true for an abandoned trial's anonymous Firebase Auth account.
- **Decision needed (product, not a blocker to *some* release, but should be resolved
  before or shortly after shipping):** confirm whether narrowing the main app's
  effective text-input ceiling from 500,000 characters to ~350,000 UTF-8 bytes (an
  unintended side effect of the new trial-motivated `MAX_TEXT_BYTES` constant being
  applied globally) is acceptable, or have it scoped to trial only.
- **Legal-copy review** (pre-existing gate, unchanged) is still outstanding and remains
  the other pre-launch gate per the existing README.

With the cleanup-automation infra blocker now cleared, this branch is ready to merge once
the main-app text-limit question is resolved one way or the other and the legal-copy
review is complete.
