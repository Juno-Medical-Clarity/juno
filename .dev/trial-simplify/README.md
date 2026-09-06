# Juno Trial App — PRD Index (2026-09-05)

## Overview

This directory contains a design-only decomposition (PRDs only; `TASKS.md` files are
generated later via `/dev-tasks`) of the Juno Trial App initiative: a bare-bones,
public, no-login, no-retained-data trial of Juno's care-plan simplification, hosted at
the project's primary web address, `juno-medical-clarity.web.app`. The existing full app
(auth, navbar, dataset/Athena presets, grading UI, admin surface) relocates to a new
Firebase Hosting site, `juno-app-99.web.app`, in the same Firebase/GCP project
(`juno-medical-clarity`). The work is additive — existing frontend and backend code is
not overridden — and splits into five sub-projects: image input support, a trial backend
route with rate limiting and retention, a standalone trial frontend, the hosting split
plus legal pages, and retention automation (TTL + anonymous-user cleanup).

---

## Implementation status (as of 2026-09-05)

**All five sub-projects (SP1–SP5) are IMPLEMENTED, reviewed, and fix-verified** on
`users/tejitpabari/trial-app`. Two review rounds have run against the branch:

- `review-2026-09-05-0554.md` — SP1 (Image Input) + SP2 (Trial Backend), merged. One
  must-fix finding (a `JunoError` fall-through to a bare 500 on illegible-image uploads),
  fixed in `cba4b5ed` and verified.
- `review-2026-09-05-0835.md` — the full branch, SP1–SP5, three personas (Bug Hunter,
  Security/Adversarial, Architect). Five findings (three blocking, one of which was
  downgraded after its premise was independently re-investigated and did not hold for
  this deployment's topology; two must-fix), all fixed and independently re-verified by
  a fourth agent that re-ran every check rather than trusting the fixing agents' reports.
  The six fix commits: `fec11a37` (deny anonymous Firebase tokens on non-trial
  authenticated routes), `93df2a08` (keep trial results rendered after the job doc is
  deleted), `5585ef4d` (make the trusted-proxy-hop count for per-IP rate limiting an
  explicit, documented constant), `5d1c226e` (escape all `buildPdfHtml` fields and drop
  the report window's `opener`), `e45b04a6` (enforce server-side max text length on job
  creation), `dd5fd3eb` (tag the deployed commit, not the branch head, in `deploy.yml`).
  Verdict: **PASS**.

Run artifacts, one per sub-project:
[`01-image-input/code-2026-09-05-0554.md`](01-image-input/code-2026-09-05-0554.md),
[`02-trial-backend/code-2026-09-05-0554.md`](02-trial-backend/code-2026-09-05-0554.md),
[`03-trial-frontend/code-2026-09-05-0741.md`](03-trial-frontend/code-2026-09-05-0741.md),
[`04-hosting-split-and-legal/code-2026-09-05-0749.md`](04-hosting-split-and-legal/code-2026-09-05-0749.md),
[`05-retention-automation/code-2026-09-05-0758.md`](05-retention-automation/code-2026-09-05-0758.md).
SP6 (a separate follow-on branch, `users/tejitpabari/trial-optimizations`) has its own
run artifact:
[`06-trial-optimizations/code-2026-09-05-2131.md`](06-trial-optimizations/code-2026-09-05-2131.md).

**SP6 branch, same day (2026-09-05/06): a deep edge-case review pass, fixes, scenario
validation, and an independent final verification.** After SP6's three optimization
tasks landed, the trial pathway (`routes/trial.py` + `routes/worker.py` +
`services/care_plan_input.py`/`care_plan_pipeline.py` + `frontend-trial/`) went through:
- [`edge-case-review-backend-2026-09-05.md`](edge-case-review-backend-2026-09-05.md) —
  10 findings (3 BLOCKING, 5 SHOULD FIX, 2 NICE TO HAVE): a char-count text cap that
  didn't bound Firestore's byte-based 1 MiB limit, a no-text-layer document silently
  bypassing `EMPTY_DOCUMENT`, the GCS-lifecycle/anon-cleanup retention backstops never
  having been deployed (BLOCKING, infra-only — see below), `input_text` never cleared
  for trial jobs, a lone UTF-16 surrogate crashing job creation, corrupt/encrypted PDFs
  500ing instead of returning a clean error, a worker idempotency gap letting a Cloud
  Tasks redelivery re-run (and re-bill) the whole LLM pipeline, one bad file aborting an
  entire multi-file trial upload, an unsalted-IP-hash fallback, and raw exception text
  reaching the client.
- [`edge-case-review-frontend-2026-09-05.md`](edge-case-review-frontend-2026-09-05.md)
  — no BLOCKING findings; 8 SHOULD-FIX/NICE-TO-HAVE items: no client-side watchdog or
  escape hatch for a job stuck in `processing`, `useAnonAuth`'s pending state having no
  timeout, missing a11y announcements across screen transitions, `CarePlanView`'s Copy
  button lacking error/success feedback, Privacy Policy deletion-timing wording, no
  guard on a missing `VITE_API_PROCESSING_URL`, the client's text-length mirror not
  matching the backend's byte-based cap, and raw Firebase SDK error text reaching the
  UI.
- All applicable findings (everything except BLOCKING #3, deliberately left as an infra
  step — see "Still requires you" below) were fixed across 13 commits (`74efe230`
  through `eac5dc84`): trial-only upload limits (5 files/10MB aggregate/no per-file cap)
  plus a shared byte-based text cap and min-content threshold, a clean 413 JSON envelope
  for oversized requests, a defensive min-content guard plus `input_text` clearing on
  trial completion plus the worker processing-lease idempotency check, a fail-safe
  rate-limit IP salt fallback and stripped unclassified-exception detail, a
  corrupt-image-bytes rejection before the Vertex AI call, and on the frontend: a
  processing watchdog with restart cleanup and a11y announcements, a bounded
  `useAnonAuth` pending-state timeout, `CarePlanView` Copy-button error handling, tighter
  Privacy Policy wording, a `VITE_API_PROCESSING_URL` guard, a Firebase SDK error mapper,
  and a `MAX_TEXT_BYTES` mirror of the backend's byte cap.
- [`scenario-validation-2026-09-05.md`](scenario-validation-2026-09-05.md) — 11
  end-to-end scenarios (typical discharge summary, phone-photo OCR, mixed-batch limits,
  multibyte-near-limits, degenerate inputs, partial-failure batches, filename
  hostility, lifecycle races, failure surfaces, rate limiting, access control) run
  against the fixed code; two bugs found during validation itself were fixed
  (surfaced in the same commit range above), all 11 scenarios PASS.
- [`final-verification-2026-09-05.md`](final-verification-2026-09-05.md) — an
  independent re-verification pass (re-ran every suite and re-derived every integration
  claim rather than trusting the above reports): confirms all three test suites are
  100% green at the totals below, confirms every checked integration point (upload
  limits per call site, `clear_input_text` lifecycle, worker lease/retry safety, the 413
  path, the `VITE_API_PROCESSING_URL` guard) behaves as intended, found and fixed one
  minor comment-accuracy bug (`MIN_MEANINGFUL_CONTENT_CHARS`'s justifying comment used a
  16-character example while claiming `>20 chars`), and flagged one **unresolved product
  decision, not fixed**: the new `MAX_TEXT_BYTES=350,000` cap is enforced globally, not
  just on the trial route, silently narrowing the main app's effective pasted-text/
  upload ceiling from 500,000 characters to ~350,000 bytes (~350,000 ASCII characters)
  for documents that previously fit. Verdict: **NOT RELEASE-READY** — blocked on the
  pre-existing BLOCKING #3 retention-automation deploy gap (unchanged from before
  today), plus this text-limit question needing an owner call.

**Test totals** (from `final-verification-2026-09-05.md`'s independent re-run, the most
current numbers as of 2026-09-06 — supersedes the "at last review close" totals this
line used to carry): backend `python3 -m pytest tests/ -q` → **684 passed**, 1
pre-existing warning (unrelated `PyPDF2` deprecation), 94% coverage; `frontend-trial` →
**19 files / 103 tests** passed, `tsc --noEmit` clean, lint clean, build clean;
`frontend` → **23 files / 189 tests** passed, `tsc --noEmit` clean, build clean.

**Outstanding, owner-only (see `review-2026-09-05-0835.md`'s "Still requires you" for the
full consolidated list with exact commands):**
- **Legal-copy review and approval (D8) — this is the one item that gates launch.** The
  Privacy Policy and Terms rendered in `frontend-trial/src/pages/` are Claude's first
  draft, not yet reviewed by a lawyer.
- All of SP5's live-GCP steps: Firestore native TTL on `care_plan_outputs` /
  `trial_rate_limits`, one-time creation of the `juno-trial-anon-cleanup` Cloud Run Job
  (`RETENTION_DRY_RUN=true` first), Cloud Scheduler + IAM, a dry-run execution and log
  review before flipping `RETENTION_DRY_RUN=false`, the GCS lifecycle rule on
  `care_plan_trial/`, and optional Cloud Monitoring alerts.
- The production cutover ordering from SP4 PRD §4.5, and watching the first automatic
  `deploy.yml` run once this branch lands on `main`.

---

## Locked Decisions (apply across all SPs)

Distilled from `brainstorm.md`'s decision log (D1–D11) plus items settled since:

- **D1 — Auth model:** Anonymous Firebase Auth (`signInAnonymously()`). The existing
  `@verify_firebase_token` and job pipeline work unchanged; the trial user never sees a
  login screen.
- **D2 — Hosting layout:** The trial takes over the primary site
  `juno-medical-clarity.web.app`. The full app moves to a new site, `juno-app-99`
  (`juno-app-99.web.app`), same Firebase project. No custom domain.
- **D3 — Frontend structure:** A separate Vite build, `frontend-trial/`, in the same
  repo, sharing exactly `CarePlanView`, `MedicalTerm`, `buildPdfHtml`, and `types/` from
  `frontend/src` via a path alias — nothing else.
- **D4 — Abuse protection:** Per-IP rate limit + hard file/size caps + a Cloud Run
  `max-instances` ceiling. No CAPTCHA/Turnstile.
- **D5 — Image input:** Supported, and added to the **main app too** (shared
  `ALLOWED_EXTENSIONS` widening in `backend/services/care_plan_input.py`), not
  trial-scoped — user explicitly approved changing main-app behavior.
- **D6 — Score displayed:** Composite 0–100, before → after only. No sub-score
  breakdown.
- **D7 — Cold starts:** `min-instances=0`, no cold-start-masking UI. Accepted first-load
  wait (~15–30s) after idle.
- **D8 — Legal copy:** Claude drafts Privacy Policy + Terms & Conditions; user reviews
  and approves before launch.
- **D9 — Data cleanup cron:** Firestore native TTL (config-only) + a daily Cloud
  Scheduler → Cloud Run Job that deletes anonymous Firebase Auth users older than 24h.
- **D10 — Analytics:** GA4 (`G-4R0CDYKSPW`), copiously instrumented, with a hard rule:
  no document content, filenames, or care-plan text in any event parameter.
- **D11 — Rate limit:** 5 simplifications per IP per hour.
- **Trial job storage (settled since brainstorm):** trial jobs live in the **shared**
  `care_plan_outputs` Firestore collection, marked `is_trial: true` with an `expires_at`
  Timestamp — a separate `trial_jobs` collection (brainstorm's original §5 proposal) was
  **rejected** in favor of reusing the existing collection and job-creation helpers.
- **Results title (settled since brainstorm):** the results screen's title comes from
  the job doc's `name` field, not a client-side derivation.
- **"Try again" button (settled 2026-09-05):** the trial results screen's **ERROR**
  sub-view gets a "Try again" button, returning to the upload screen. The **SUCCESS**
  sub-view keeps the original exclusion — no "Another care plan" button.
- **Search indexing (settled 2026-09-05):** allowed. No `robots noindex` meta tag on the
  trial's `index.html`. Cost exposure from organic search traffic is bounded only by
  D11's rate limit and the Cloud Run `max-instances` ceiling.
- **Paste-text cap (settled 2026-09-05):** the trial's paste-text textarea gets a
  client-side cap of **100,000 characters** (SP3 §9 Q4) — generous, but bounds abuse and
  Gemini cost. No server-side text-length limit exists to mirror it.
- **Pipeline version (settled 2026-09-05):** the trial hard-codes `version="v1-2"`
  server-side (SP2 §9 Q14) — no client-controllable version, and no version selector in
  the trial UI. Any client-supplied `version`/`grading_enabled`/`doc_id` is silently
  ignored.
- **Trial GCS upload prefix (settled 2026-09-05):** trial uploads move off the shared
  `care_plan/` prefix onto a distinct `care_plan_trial/{user_id}/inputs/{object_id}.pdf`
  prefix (SP2 §9 Q15, `upload_combined_pdf`'s new `is_trial` flag) — main-app uploads are
  unaffected. This is what makes SP5's GCS lifecycle-rule backstop (§4.10) safe.
- **`max-instances` (settled 2026-09-05):** `juno-api` = 10, `juno-worker` = 5 (SP4 §9
  Q3), wired into `deploy.yml` via `API_MAX_INSTANCES`/`WORKER_MAX_INSTANCES`.
- **`min-instances=0` everywhere (settled 2026-09-05):** D7's "no cold-start masking"
  rule now applies with no exceptions — `rollback-production.yml`'s pre-existing
  `--min-instances=1` on `juno-api` is corrected to `0` (SP4 §9 Q4), matching every other
  deploy path.
- **Auto-deploy trigger (settled 2026-09-05):** merging to `main` automatically deploys
  the backend and the trial frontend (`frontend-trial/`), gated structurally on CI
  passing via a `workflow_run` trigger (SP4 §4.8) — not a bare `push` trigger. The
  relocated full app (`app` target, `juno-app-99.web.app`) is **never** auto-deployed; it
  stays `workflow_dispatch`-only, so a merge to `main` cannot risk that site.

---

## Sub-Projects

| SP # | Name | Phase | Scope (one line) | Depends On | PRD path | TASKS path |
|------|------|-------|-------------------|------------|----------|------------|
| SP1 | Image Input Support | P1 | Add `png/jpg/jpeg/webp/heic` to the shared `ALLOWED_EXTENSIONS`; a Gemini-vision (Vertex) extraction path in `care_plan_input.py`; images embedded into the combined PDF. Benefits main app + trial. | None | `01-image-input/PRD.md` | `01-image-input/TASKS.md` |
| SP2 | Trial Backend Route, Rate Limiting & Retention | P1 | New `/trial` route family (`POST`/`DELETE /trial/jobs/<id>`) reusing existing job-creation helpers; Firestore-backed per-IP rate limit (5/hr); `is_trial`/`expires_at` fields on the shared `care_plan_outputs` collection; GCS input cleanup after extraction. | None | `02-trial-backend/PRD.md` | `02-trial-backend/TASKS.md` |
| SP3 | Trial Frontend App | P2 | New `frontend-trial/` Vite app: upload → processing (live steps) → results screens, anonymous-auth wiring, GA4 instrumentation, download-report reuse, best-effort `DELETE` on unload. | SP2 (API contract) | `03-trial-frontend/PRD.md` | `03-trial-frontend/TASKS.md` |
| SP4 | Hosting Split, CI & Legal Pages | P3 | Multi-target `firebase.json`/`.firebaserc` (`app` + `trial`); `deploy.yml` gains a trial build/deploy job and fixes `rollback-production.yml`; CORS widened for `juno-app-99.web.app`; Privacy Policy + Terms & Conditions copy. | SP3 (build output); coordinates with SP2 (CORS, max-instances) | `04-hosting-split-and-legal/PRD.md` | `04-hosting-split-and-legal/TASKS.md` |
| SP5 | Retention Automation | P5 | Enables Firestore native TTL on `care_plan_outputs`/`trial_rate_limits`; daily Cloud Scheduler → Cloud Run Job deleting anonymous Auth users older than 24h. | SP2 (`expires_at` fields, `trial_rate_limits`); coordinates with SP4 (deploy workflow, legal copy accuracy) | `05-retention-automation/PRD.md` | `05-retention-automation/TASKS.md` |
| SP6 | Trial Pipeline Optimizations | P6 | Backend-only follow-on (separate branch `users/tejitpabari/trial-optimizations`, off `main` post-SP1–SP5): trims trial grading output to `combined`-only entries, populates the previously-always-`None` `Metrics.total_duration_ms`, and overlaps the `before`-grading score computation with the pipeline's LLM calls. | None (SP1–SP5 already on `main`) | `06-trial-optimizations/PRD.md` | `06-trial-optimizations/TASKS.md` |

---

## Dependency Graph

```
SP1 (independent) ──┐
SP2 (independent) ──┤
                     ▼
                    SP3 ◄── SP2 (API contract)
                     │
                     ▼
                    SP4 ◄── SP3 (build output); coordinates with SP2 (CORS, max-instances)
                     │
                     ▼
                    SP5 ◄── SP2 (expires_at, trial_rate_limits); coordinates with SP4 (deploy, legal copy)
```

**Recommended execution order under a 2-concurrent-agent cap:**

`[SP1 ‖ SP2] → SP3 → SP4 → SP5`

SP1 and SP2 touch disjoint backend surfaces (extraction path vs. new route file) and can
run in parallel. SP3 cannot start meaningfully until SP2's API contract (§5) is stable.
SP4 needs SP3's `frontend-trial/dist` to exist before its deploy-target/CI work is
testable, and separately coordinates CORS/rate-limit-flag details with SP2. SP5 is last
because it activates destructive automation (TTL deletion, account cleanup) against
fields SP2 defines and legal copy SP4 drafts — it should not go live before both are
settled.

---

## Infrastructure already provisioned (as of 2026-09-05)

Verified to exist in GCP/Firebase, ahead of any SP5/SP4 code landing:

- **Firebase Hosting sites:** `juno-medical-clarity` (primary/default site — currently
  serving the full app; will serve the **trial** after cutover) and `juno-app-99`
  (created, empty — will receive the relocated full app).
- **`.firebaserc` hosting targets:** `trial` → `juno-medical-clarity`, `app` →
  `juno-app-99` — applied via `firebase target:apply` and committed to the repo root.
- **Cloud Tasks queue `care-plan-jobs-trial`** — created and `RUNNING`, alongside the
  existing `care-plan-jobs` queue (max 5 concurrent dispatches, 2/sec).
- **GitHub repository secret `TRIAL_RATE_LIMIT_SALT`** — added by the user.

**Not yet created** (correctly — these depend on SP5 code that doesn't exist yet):
- The Firestore TTL policies on `care_plan_outputs`/`trial_rate_limits`. The user's
  first attempt failed with `ERROR: (gcloud.firestore.fields.ttls.update) Exactly one
  of (--disable-ttl | [--enable-ttl : --expiration-offset]) must be specified.` — the
  missing `--enable-ttl` flag has since been corrected in SP5 §8 (and §4.1).
- The `juno-trial-anon-cleanup` Cloud Run Job.
- The Cloud Scheduler trigger for that Job — blocked on the Cloud Scheduler API not yet
  being enabled on the project.
- The GCS lifecycle rule on the `care_plan_trial/` prefix.

---

## Consolidated Manual Steps (owner-only)

Already **DONE**, per `brainstorm.md` §8:
- Merging prerequisite PR #35.
- Enabling the **Anonymous** sign-in provider in the Firebase console.

**The single authoritative list of remaining IAM grants, GitHub secrets, and one-time
`gcloud`/`firebase` commands the user must run lives in
`05-retention-automation/PRD.md` §8, under "### CI & IAM setup checklist" (around line
810).** It supersedes the individual per-SP manual-step lists below wherever they
overlap (the trial rate-limit salt secret, the Cloud Tasks queue, the Firestore TTL
commands, the anonymous-cleanup Job/Scheduler setup, the Hosting site/target setup, and
the GCS lifecycle rule are all copy-pasteable there in one place, in dependency order).
Run through that checklist top to bottom; the numbered items below are the remaining
status of each individual PRD's own manual-steps section for cross-reference.

1. **[RESOLVED/DONE]** Contact method supplied: `tejitpabari99@gmail.com` (SP4 §8#2).
   Both the Privacy Policy and Terms & Conditions now list this address in place
   of the `[CONTACT — placeholder]` line.
2. **Review and approve the Privacy Policy and Terms & Conditions copy before launch**
   (D8, SP4 §8#1) — still outstanding; first drafts, not lawyer-reviewed. Confirm the
   stated rate limit ("5 per hour") matches what SP2 ships, and confirm comfort with the
   liability/warranty language for a health-adjacent public tool. (The deletion-timing
   wording SP5 flagged is already corrected — see SP4 §9 Q9 — so this review is about
   tone/liability only, not a pending text fix.)
3. **[RESOLVED/DONE]** Deploy service account's IAM has been confirmed by the owner to
   cover `firebase hosting:sites:create` and `target:apply` (SP4 §8#4-5) — no role
   grant needed before creating the new `juno-app-99` Hosting site.
4. **Add a new GitHub Actions secret `TRIAL_RATE_LIMIT_SALT`** (SP2 §8#1) — see the CI &
   IAM checklist's item 1 for the exact command.
5. **Create the trial Cloud Tasks queue manually, once** (SP2 §8#2) — the CI & IAM
   checklist's investigation found `GCP_SA_KEY` holds no Cloud Tasks role, so this is a
   one-time human step (checklist item 2a), not a CI grant.
6. **[RESOLVED/DONE]** Cloud Run `max-instances` numbers: `juno-api` = 10, `juno-worker`
   = 5 (SP4 §8#3, SP4 §9 Q3, per user 2026-09-05) — wired into `deploy.yml` via
   `API_MAX_INSTANCES`/`WORKER_MAX_INSTANCES`.
7. **Confirm the Firebase service account has the Firebase Authentication Admin IAM
   role** (SP5 §8#1) — assumed already granted; grant only if a dry-run surfaces a
   permission error (checklist item 3c).
8. **Flip `RETENTION_DRY_RUN` from `true` to `false`** on the cleanup Cloud Run Job (SP5
   §8#2), only after reviewing at least one real dry-run's log output and confirming the
   scanned/matched counts look right. Deliberately manual, not automated (checklist
   item 4).
9. **Run the two one-time `gcloud firestore fields ttls update` commands** and confirm
   both report `ACTIVE` (SP5 §8#3, checklist item 2b).
10. **Run the one-time `gcloud run jobs deploy` and Cloud Scheduler/IAM setup** for the
    anonymous-cleanup job (SP5 §8#4, checklist items 2c-2d) — `deploy.yml` keeps it in
    sync automatically afterward.
11. **Optional: set up the two recommended Cloud Monitoring alerting policies** (SP5
    §8#6) — console-only, not blocking launch.
12. **Run the one-time GCS lifecycle-rule command** on the `care_plan_trial/` prefix
    (SP5 §8#7, checklist item 2e) — now safe since trial uploads have their own distinct
    prefix (SP2 §9 Q15).
13. **(Not blocking, awareness only) Verify `pillow-heif` wheel compatibility** with the
    `python:3.11-slim` deploy image once the dependency is added (SP1 §8#1) — a
    build-time check the implementing agent can do directly; falls back to one added
    `apt-get install libheif1` line in `backend/Dockerfile` if needed.

---

## Consolidated Open Questions

Re-derived by grepping all five PRDs' §9 sections for `[OPEN]` (2026-09-05): **there are
none.** Every §9 item across SP1–SP5 is now either `[RESOLVED]` or `[DEFERRED]`. The
`[DEFERRED]` items are listed below so none of them silently disappear:

**SP2 — Trial Backend Route, Rate Limiting & Retention**
- Q13: Is `X-Forwarded-For`'s last value always trustworthy? **[DEFERRED]** — true for the
  current topology (Cloud Run is the only proxy hop, no external LB/CDN/Cloud Armor); if a
  future change puts Cloud Run behind an additional external proxy layer,
  `get_client_ip()`'s "take the last value" logic must change to "take the
  second-to-last value."

**SP3 — Trial Frontend App**
- Q1: Should `ALLOWED_UPLOAD_EXTENSIONS` live in one shared `frontend/src/constants.ts`
  entry both `frontend/` and `frontend-trial/` import, instead of two hardcoded copies?
  **[DEFERRED]** — real duplication now that SP3 exists, but touches `frontend/src`
  (outside this PRD's non-goals) and isn't required for SP3's correctness; left as a
  flagged follow-up.
- Q7: Should a `tsc -b`/`npm run build` type-check step be added to `ci.yml`'s new
  `frontend-trial` job? **[DEFERRED]** — the existing `frontend` CI job also only runs
  `npm run test`, so adding a build/typecheck step only to the new job would be an
  inconsistency between the two frontend CI jobs worth deciding for both at once, not
  unilaterally here.

**SP4 — Hosting Split, CI & Legal Pages**
- Q2: Should there be a manual-approval gate between the `app` and `trial` deploy steps?
  **[DEFERRED]** — rejected for now as over-engineering for a single-operator project
  where Hosting deploys are seconds, not minutes, and the rollback path (§4.4) is the
  accepted safety net. Revisit if this project ever has multiple deploy operators.

**SP5 — Retention Automation**
- Q5: Should the cleanup job persist a `next_page_token` cursor across runs for faster
  resumption after a killed run? **[DEFERRED]** — not justified at this product's
  realistic daily volume; revisit only if actual volume approaches the 100k+ stress case.
- Q6: Should overlapping/concurrent job runs be prevented with an explicit lock?
  **[DEFERRED]** — a single Cloud Scheduler cadence makes accidental overlap unlikely and
  not unsafe (`delete_users` tolerates already-deleted uids); add a lock only if overlap
  is ever observed to actually cause problems.

---

## Cross-cutting risks

- **The cutover is the riskiest single step.** Deploying the trial to
  `juno-medical-clarity.web.app` overwrites the currently-live app at that address.
  Backend CORS must include `juno-app-99.web.app` **before** the relocated full app can work
  at its new address — a hard ordering constraint. SP4 defines the safe deploy order and
  the rollback path; do not deviate from it during the actual cutover.
- **`rollback-production.yml` is a second, independent Hosting deploy path** that breaks
  the moment `firebase.json` becomes multi-target (fixed in SP4 §4.4) — without that fix,
  a rollback would deploy to the wrong (or no) target. It also pre-existingly set
  `--min-instances=1` for `juno-api`, contradicting the locked D7 decision
  (`min-instances=0`, no cold-start masking) — **corrected to `0`** (SP4 §9 Q4,
  §4.4), so `min-instances=0` now holds with no exceptions across every deploy path.
- **GCS lifecycle rules were initially investigated and rejected**, then revisited once
  SP2 adopted a distinct trial upload prefix: the original `care_plan/` path shape was
  identical for trial and main-app uploads, giving a lifecycle rule no safe way to
  distinguish them. Per user direction (SP2 §9 Q15), trial uploads now write to
  `care_plan_trial/...` instead, which makes a prefix-scoped lifecycle rule (`age: 1`
  day) safe as a third backstop (SP5 §4.10) behind SP2's explicit worker cleanup and the
  Firestore TTL policy. See Locked Decisions above and Manual Steps #12 for the one-time
  command.
- **Deletion-timing wording was corrected across SP4's legal copy** after SP5's design
  pass found a real overclaim: SP4's original Privacy Policy draft said job records are
  deleted "generally within an hour," but Firestore's documented TTL behavior allows
  deletion up to 24 hours after expiration. With SP2's 1-hour `expires_at` plus TTL sweep
  latency, worst-case lifetime is ~25 hours, not "an hour." The corrected framing: an
  explicit `DELETE` call is the primary path and is effectively immediate; the TTL
  backstop is described as "typically within a day." **This amendment is done** — SP4's
  Privacy Policy, Terms, and footer copy (§6.2, §6.4) carry the corrected wording, and
  SP4 §9 Q9 records the resolution. The only remaining step is the owner's routine
  pre-launch legal-copy review (Manual Steps #2), not a pending text fix.

---

## Next step

All five sub-projects plus SP6's optimizations and today's edge-case-review fixes are
implemented and independently re-verified (see "Implementation status" above and
`final-verification-2026-09-05.md`). Most of what remains is owner-only: legal-copy
review and approval (D8, the launch gate), SP5's live-GCP setup (in particular the GCS
lifecycle rule and anonymous-account cleanup automation — still not deployed, the one
BLOCKING item today's verification pass reconfirmed), and the production cutover per SP4
PRD §4.5. See `review-2026-09-05-0835.md`'s "Still requires you" section for the
consolidated, exact-command version of that list.

One item is **not** owner-only and needs a product decision before or shortly after
shipping: `final-verification-2026-09-05.md` §3 found that the new
`MAX_TEXT_BYTES=350,000` cap (added for the trial route's Firestore-size safety) is
enforced globally, including on the main app's pasted-text, upload, and `doc_id` paths —
narrowing the main app's effective text ceiling from 500,000 characters to ~350,000
bytes for ASCII text. This was deliberately left unchanged pending an explicit owner
call on whether that's acceptable or should be scoped to trial only.
