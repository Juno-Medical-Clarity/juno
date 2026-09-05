# Juno Trial App — PRD Index (2026-09-05)

## Overview

This directory contains a design-only decomposition (PRDs only; `TASKS.md` files are
generated later via `/dev-tasks`) of the Juno Trial App initiative: a bare-bones,
public, no-login, no-retained-data trial of Juno's care-plan simplification, hosted at
the project's primary web address, `juno-medical-clarity.web.app`. The existing full app
(auth, navbar, dataset/Athena presets, grading UI, admin surface) relocates to a new
Firebase Hosting site, `juno-app.web.app`, in the same Firebase/GCP project
(`juno-medical-clarity`). The work is additive — existing frontend and backend code is
not overridden — and splits into five sub-projects: image input support, a trial backend
route with rate limiting and retention, a standalone trial frontend, the hosting split
plus legal pages, and retention automation (TTL + anonymous-user cleanup).

---

## Locked Decisions (apply across all SPs)

Distilled from `brainstorm.md`'s decision log (D1–D11) plus items settled since:

- **D1 — Auth model:** Anonymous Firebase Auth (`signInAnonymously()`). The existing
  `@verify_firebase_token` and job pipeline work unchanged; the trial user never sees a
  login screen.
- **D2 — Hosting layout:** The trial takes over the primary site
  `juno-medical-clarity.web.app`. The full app moves to a new site, `juno-app`
  (`juno-app.web.app`), same Firebase project. No custom domain.
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

---

## Sub-Projects

| SP # | Name | Phase | Scope (one line) | Depends On | PRD path |
|------|------|-------|-------------------|------------|----------|
| SP1 | Image Input Support | P1 | Add `png/jpg/jpeg/webp/heic` to the shared `ALLOWED_EXTENSIONS`; a Gemini-vision (Vertex) extraction path in `care_plan_input.py`; images embedded into the combined PDF. Benefits main app + trial. | None | `01-image-input/PRD.md` |
| SP2 | Trial Backend Route, Rate Limiting & Retention | P1 | New `/trial` route family (`POST`/`DELETE /trial/jobs/<id>`) reusing existing job-creation helpers; Firestore-backed per-IP rate limit (5/hr); `is_trial`/`expires_at` fields on the shared `care_plan_outputs` collection; GCS input cleanup after extraction. | None | `02-trial-backend/PRD.md` |
| SP3 | Trial Frontend App | P2 | New `frontend-trial/` Vite app: upload → processing (live steps) → results screens, anonymous-auth wiring, GA4 instrumentation, download-report reuse, best-effort `DELETE` on unload. | SP2 (API contract) | `03-trial-frontend/PRD.md` |
| SP4 | Hosting Split, CI & Legal Pages | P3 | Multi-target `firebase.json`/`.firebaserc` (`app` + `trial`); `deploy.yml` gains a trial build/deploy job and fixes `rollback-production.yml`; CORS widened for `juno-app.web.app`; Privacy Policy + Terms & Conditions copy. | SP3 (build output); coordinates with SP2 (CORS, max-instances) | `04-hosting-split-and-legal/PRD.md` |
| SP5 | Retention Automation | P5 | Enables Firestore native TTL on `care_plan_outputs`/`trial_rate_limits`; daily Cloud Scheduler → Cloud Run Job deleting anonymous Auth users older than 24h. | SP2 (`expires_at` fields, `trial_rate_limits`); coordinates with SP4 (deploy workflow, legal copy accuracy) | `05-retention-automation/PRD.md` |

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

## Consolidated Manual Steps (owner-only)

Already **DONE**, per `brainstorm.md` §8:
- Merging prerequisite PR #35.
- Enabling the **Anonymous** sign-in provider in the Firebase console.

Still outstanding:

1. **[RESOLVED]** Contact method supplied: `tejitpabari99@gmail.com` (SP4 §8#2).
   Both the Privacy Policy and Terms & Conditions now list this address in place
   of the `[CONTACT — placeholder]` line.
2. **Review and approve the Privacy Policy and Terms & Conditions copy before launch**
   (D8, SP4 §8#1) — first drafts, not lawyer-reviewed. Confirm the stated rate limit
   ("5 per hour") matches what SP2 ships, and confirm comfort with the liability/warranty
   language for a health-adjacent public tool. SP5 additionally requires **amending the
   deletion-timing wording** SP4 drafted (SP5 §8#5) — see Cross-cutting risks below.
3. **[RESOLVED]** Deploy service account's IAM has been confirmed by the owner to
   cover `firebase hosting:sites:create` and `target:apply` (SP4 §8#4-5) — no role
   grant needed before creating the new `juno-app` Hosting site.
4. **Add a new GitHub Actions secret `TRIAL_RATE_LIMIT_SALT`** (SP2 §8#1) — any random
   32+ byte value (`openssl rand -hex 32`), used to HMAC-hash client IPs before they're
   stored.
5. **Confirm the `GCP_SA_KEY` service account can create Cloud Tasks queues**
   (`cloudtasks.queues.create`/`.get`) (SP2 §8#2) — needed once, the first time the new
   trial Cloud Tasks queue deploy step runs. Grant `roles/cloudtasks.admin` (or a
   narrower custom role) if the step fails with a permission error.
6. **Confirm the Cloud Run `max-instances` numbers** for `juno-api`/`juno-worker` once
   SP2 proposes them (SP4 §8#3, SP4 §9 Q3) — SP4 defines where the flag goes in
   `deploy.yml`, not the final value.
7. **Confirm the Firebase service account has the Firebase Authentication Admin IAM
   role** (SP5 §8#1) — needed for `auth.list_users`/`auth.delete_users` from the new
   Cloud Run Job.
8. **Flip `RETENTION_DRY_RUN` from `true` to `false`** on the cleanup Cloud Run Job (SP5
   §8#2), only after reviewing at least one real dry-run's log output and confirming the
   scanned/matched counts look right. Deliberately manual, not automated.
9. **Run the two one-time `gcloud firestore fields ttls update` commands** and confirm
   both report `ACTIVE` (SP5 §8#3).
10. **Run the one-time `gcloud run jobs deploy` and Cloud Scheduler/IAM setup** for the
    anonymous-cleanup job (SP5 §8#4) — `deploy.yml` keeps it in sync automatically
    afterward.
11. **Optional: set up the two recommended Cloud Monitoring alerting policies** (SP5
    §8#6) — console-only, not blocking launch.
12. **(Not blocking, awareness only) Verify `pillow-heif` wheel compatibility** with the
    `python:3.11-slim` deploy image once the dependency is added (SP1 §8#1) — a
    build-time check the implementing agent can do directly; falls back to one added
    `apt-get install libheif1` line in `backend/Dockerfile` if needed.

---

## Consolidated Open Questions

Every remaining `[OPEN]` item across all five PRDs (excludes `[RESOLVED]` and
`[DEFERRED]` items):

**SP1 — Image Input Support**
- Q1: Can `pillow-heif`'s prebuilt wheel actually decode HEIC on the `python:3.11-slim`
  deploy target, or does it need `libheif1` via apt? Cannot be verified from the design
  phase; verify first thing in implementation, before the HEIC-specific test.
- Q2: Does Vertex's Gemini API actually accept `mime_type="image/heic"` for inline data on
  the specific deployed models, or does it need conversion to JPEG first? Not
  independently verified against a live Vertex call during design; requires a live smoke
  test before considering SP1 done.

**SP2 — Trial Backend Route, Rate Limiting & Retention**
- (None open — all 14 questions in SP2 §9 are `[RESOLVED]`.)

**SP3 — Trial Frontend App**
- Q2: If the `@main` alias fails `tsc -b` type-checking and the fallback (copying 5
  files) is used instead, who keeps the copies in sync when `frontend/src`'s originals
  change? No automated drift-detection proposed.
- Q4: Should the paste-text textarea have a client-side character/length cap? No
  server-side text-length limit exists to mirror; left uncapped unless a real problem
  surfaces.

**SP4 — Hosting Split, CI & Legal Pages**
- Q1: **[RESOLVED]** Does the existing `FIREBASE_SERVICE_ACCOUNT` secret's IAM role
  cover `hosting:sites:create` and `target:apply`, or only `hosting:deploy`? Owner has
  confirmed the IAM role covers both (see Manual Steps #3).
- Q3: Exact `max-instances` values for `juno-api`/`juno-worker` in `deploy.yml`. This PRD
  confirms where the flag goes; SP2 owns the number (see Manual Steps #6).
- Q4: `rollback-production.yml`'s `juno-api` deploy sets `--min-instances=1`,
  contradicting D7's locked "min-instances=0" for the primary pipeline. Pre-existing
  inconsistency, flagged for SP2 to resolve so an emergency rollback doesn't silently
  reintroduce always-warm-instance cost.

**SP5 — Retention Automation**
- Q1: Does the existing `firebase-service-account` identity already have Firebase
  Authentication Admin IAM, and does the identity running the one-time TTL commands have
  `roles/datastore.owner` (or equivalent)? Cannot be verified without a live IAM check
  (see Manual Steps #7, #9).
- Q4: What if a real (non-anonymous) user somehow has empty `provider_data`? Accepted
  risk, not engineered around — cannot arise via this codebase's actual sign-in paths
  today; mitigated operationally by the dry-run gate, not structurally.

---

## Cross-cutting risks

- **The cutover is the riskiest single step.** Deploying the trial to
  `juno-medical-clarity.web.app` overwrites the currently-live app at that address.
  Backend CORS must include `juno-app.web.app` **before** the relocated full app can work
  at its new address — a hard ordering constraint. SP4 defines the safe deploy order and
  the rollback path; do not deviate from it during the actual cutover.
- **`rollback-production.yml` is a second, independent Hosting deploy path** that breaks
  the moment `firebase.json` becomes multi-target (fixed in SP4 §4.4) — without that fix,
  a rollback would deploy to the wrong (or no) target. It also sets
  `--min-instances=1` for `juno-worker`, contradicting the locked D7 decision
  (`min-instances=0`, no cold-start masking) — flagged as SP4 §9 Q4, unresolved.
- **GCS lifecycle rules were investigated and rejected** as a retention backstop (SP5
  §9 Q3) because trial and main-app uploads share an identical GCS path shape — a
  lifecycle rule has no safe way to distinguish them. Deletion instead depends entirely
  on SP2's explicit worker cleanup (immediately after extraction) plus the Firestore TTL
  backstop (SP5) as defense in depth; there is no GCS-level third layer.
- **Deletion-timing wording was corrected across SP4's legal copy** after SP5's design
  pass found a real overclaim: SP4's original Privacy Policy draft said job records are
  deleted "generally within an hour," but Firestore's documented TTL behavior allows
  deletion up to 24 hours after expiration. With SP2's 1-hour `expires_at` plus TTL sweep
  latency, worst-case lifetime is ~25 hours, not "an hour." The corrected framing: an
  explicit `DELETE` call is the primary path and is effectively immediate; the TTL
  backstop is described as "typically within a day." This amendment still needs to be
  applied to SP4's PRD text and the actual `frontend-trial/` legal-page copy before
  launch (see Manual Steps #2).

---

## Next step

Run `/dev-tasks` against these five approved PRDs to generate a `TASKS.md` per
sub-project, in the dependency order above. **No `TASKS.md` exists in this directory yet
— by design:** this round was PRDs (design) only.
