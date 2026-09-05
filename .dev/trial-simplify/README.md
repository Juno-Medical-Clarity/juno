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

SP1 (Image Input Support) and SP2 (Trial Backend Route, Rate Limiting & Retention) are
**IMPLEMENTED** and merged into `users/tejitpabari/trial-app`. SP3-SP5 are not started, but
each now has a generated `TASKS.md` (SP3: 20 tasks, SP4: 9 tasks, SP5: 7 tasks), ready for
`/dev-code`. Run artifacts:
[`01-image-input/code-2026-09-05-0554.md`](01-image-input/code-2026-09-05-0554.md),
[`02-trial-backend/code-2026-09-05-0554.md`](02-trial-backend/code-2026-09-05-0554.md),
[`review-2026-09-05-0554.md`](review-2026-09-05-0554.md).

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

All five sub-projects now have both a PRD and a `TASKS.md`. SP1 and SP2 are implemented.
The next step is running `/dev-code` on SP3, then SP4, then SP5, in that dependency
order.
