# Juno Trial: Overview

**Scope of this document.** This is the entry point for understanding Juno's public
trial — what it is, why it exists, what a user experiences, how it works, and its
current status and known gaps — written for a technical reader who wants to understand
the whole thing in one sitting. It is deliberately shallow on internals: two companion
documents carry the depth, and this document hands off to them by section number rather
than repeating their content:

- [`docs/care-plan-pipeline.md`](care-plan-pipeline.md) — the backend processing
  pipeline (input extraction, OCR, the five simplification stages, term detection,
  scoring, error taxonomy).
- [`docs/trial-architecture.md`](trial-architecture.md) — the trial system's own
  architecture (topology, auth and trust boundary, API surface, rate limiting, data
  lifecycle, frontend structure, analytics, CI/CD, legal surface, known gaps).

As implemented on branch `users/tejitpabari/trial-optimizations`, as of 2026-09-06.
Source pointers use `path:line`; line numbers are for orientation — verify against the
current file. Where the code and a planning document in `.dev/trial-simplify/`
disagree, the code is treated as ground truth and the disagreement is called out
explicitly rather than silently resolved.

---

## 1. What Juno is

The problem: a patient leaves a clinical visit with a note written by and for
clinicians — dense, abbreviation-heavy, organized around clinical reasoning rather than
"what do I actually need to do." Juno's "Simplify" pipeline takes that document (a SOAP
note, discharge summary, or appointment summary) and produces a structured,
plain-language version organized around what a patient needs to know and do.

**Who it's for:** patients (or the people helping them, e.g. family) who have a
clinical document and want a version they can actually read and act on. It is not a
clinical decision-support tool, does not give medical advice, and is not a substitute
for talking to a clinician (see §9 legal/compliance discussion in
`docs/trial-architecture.md` §9 and `docs/hipaa-compliance-action-plan.md`).

**What the transformation looks like, structurally.** The output is broken into a
fixed set of sections, rendered by `frontend/src/components/CarePlanView.tsx` (shared
between the trial and the full app) — verified directly against the component's own
`title=` props (`CarePlanView.tsx:154,165,197,220,233,246,268,288,320,331,339,352`):
**Why You Came In**, **What the Doctor Found**, **Your Medications**, **Tests**,
**Procedures**, **Other Instructions**, **What to Watch For**, **Questions to Ask at
Your Next Visit**, **Follow-Up**, **Other Items From Your Visit**, **Medical Terms
Glossary**, and **Data Sources**. These map onto fields of the `CarePlanV1_2` Pydantic
model (`backend/models/care_plan/versions/v1_2.py:107-125`) — e.g. `medications`,
`warning_signs`, `follow_up`, `questions`, `terms` — which is what the last pipeline
stage produces (care-plan-pipeline.md §4.4).

**Illustrative before/after.** The example below is deliberately generic and obviously
synthetic — it is not derived from any real patient record, and no such record was used
to construct it. It exists only to show the *shape* of the transformation, using the
real section names above:

> **Before (excerpt of a clinical note):**
> "Pt presents s/p fall, R wrist ORIF x1 wk ago, c/o persistent edema and mild
> paresthesia distal to cast. Rx: continue Amoxicillin 500mg PO TID x7d for surgical
> site erythema. F/u ortho 2 wks, d/c sutures. Return precautions given for signs of
> compartment syndrome."
>
> **After (Simplify output, structured):**
> - *Why You Came In:* Follow-up after wrist surgery (a repair of a broken wrist).
> - *What the Doctor Found:* Some swelling and mild numbness/tingling below your cast —
>   your doctor is watching this closely.
> - *Your Medications:* Amoxicillin 500 mg, three times a day for 7 days, for a skin
>   infection at your surgery site.
> - *Follow-Up:* See your orthopedic doctor in 2 weeks to have your stitches removed.
> - *What to Watch For:* Worsening pain, tightness, or numbness in your hand or fingers
>   could be a sign of a serious complication — call your doctor or go to the ER right
>   away if this happens.

The real pipeline additionally attaches a **Medical Terms Glossary** (inline
definitions for terms like "ORIF" or "compartment syndrome" that survive into the
rewritten text) and a readability score (before/after), covered in §3 below and
care-plan-pipeline.md §6–§7.

---

## 2. What the trial version is, and why it exists

The trial is a bare-bones, public, no-login way to try the core simplification with
zero commitment: no account, nothing saved beyond the current session, no setup. It
exists at the project's primary web address, `juno-medical-clarity.web.app` — the
address the full app used to occupy before this cutover
(`docs/trial-architecture.md` §1). The full authenticated app (login, datasets, Athena
presets, grading UI, saved history, admin) relocated to `juno-app-99.web.app`.

| | Trial (`juno-medical-clarity.web.app`) | Full app (`juno-app-99.web.app`) |
|---|---|---|
| Login | None — anonymous Firebase Auth only | Real account (email/password or provider) |
| Data retention | Nothing intentionally retained beyond the active session (§4) | Persistent — saved outputs, history |
| Input types | Pasted text, file upload (PDF/TXT/DOCX/HTML/image) | Same, plus `doc_id` re-run and GCS batch/Athena live fetch |
| File limits | ≤5 files, ≤10 MB aggregate, no per-file cap | ≤10 files, ≤10 MB per file, ≤25 MB aggregate |
| Dataset/Athena preset access | None | Yes |
| Grading UI (per-method scores) | No — only a combined before/after score | Yes — all 7 scoring methods × before/after |
| Saved history | No | Yes |
| Admin surface | No | Yes |
| Rate limit | 5 requests/IP/hour (`Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR`, `backend/utils/constants.py:202`) | None at this layer |
| Pipeline version | Hard-coded `v1-2`, not client-selectable (`routes/trial.py:54,86`) | Client-settable, defaults `v1-2` |

Full detail on every row: `docs/trial-architecture.md` §1–§5.

The trial's motivation is straightforward: let anyone evaluate the core simplification
without asking them to create an account or trust the service with retained data,
while keeping the underlying pipeline identical to what the full app runs — same
Gemini calls, same prompts, same scoring (`docs/trial-architecture.md` §1: "No
trial-specific prompt or model exists").

---

## 3. What a user actually does

1. **Upload or paste.** On `UploadScreen.tsx`, the user either pastes text or selects
   files. Accepted file types: `pdf`, `txt`, `docx`, `html`/`htm`, and images
   (`png`/`jpg`/`jpeg`/`webp`/`heic`) — `Constants.Uploads.ALLOWED_EXTENSIONS`
   (`backend/utils/constants.py:20-22`, shared with the main app). Limits, enforced
   both client-side (`frontend-trial/src/utils/validateFiles.ts`) and server-side
   (`Constants.Trial`, `backend/utils/constants.py:194-213`):
   - Up to **5 files**, **10 MB aggregate**, no per-file cap.
   - Pasted text: up to **500,000 characters** and, independently, **350,000 UTF-8
     bytes** (`MAX_TEXT_LENGTH`/`MAX_TEXT_BYTES`) — both caps must pass; see §7 for why
     the byte cap exists and a caveat about its scope.
   - One bad file (blank scan, corrupt PDF) is skipped rather than aborting the whole
     request; the request only fails if no file yields usable content
     (care-plan-pipeline.md §2.2, §2.6).
2. **Processing.** `ProcessingScreen.tsx` shows the five pipeline steps live, driven by
   a Firestore field the worker updates as it progresses (care-plan-pipeline.md §4):
   reading the note, finding difficult/medical terms, simplifying language, clarifying
   actions and numbers, and organizing the care plan. A watchdog surfaces a "taking
   longer than expected" affordance if a job never reaches a terminal state within 6
   minutes (`docs/trial-architecture.md` §6).
3. **Result.** `ResultScreen.tsx` renders the structured sections listed in §1, with
   medical terms explained inline via the glossary and a readability score (a
   composite 0–100, before vs. after — care-plan-pipeline.md §7). The user can
   **download a report** (a standalone HTML file, generated client-side) or the result
   is simply left on screen; the job is deleted the moment this screen mounts (§4).
4. **First-load latency.** The design intends `min-instances=0` on both Cloud Run
   services (`docs/trial-architecture.md` §1), but **`juno-api` is confirmed live at
   `min-instances=1`, not 0** (verified 2026-09-06, §7 below) — only `juno-worker` is
   actually at 0. In practice this means the API front door itself rarely cold-starts;
   a cold start (roughly **15–30 seconds**) is still possible for `juno-worker` picking
   up a task after idle time. The `min-instances=0` design was a deliberate
   cost/latency trade-off for a free, unauthenticated trial, not a bug — see
   `docs/trial-architecture.md` §8 for the exact mechanism behind why `juno-api`
   deviates from it in practice.

For the full screen-by-screen frontend structure, see `docs/trial-architecture.md` §6.

---

## 4. How it works, in brief

```
Client → anonymous Firebase Auth → POST /trial/jobs (Cloud Run: juno-api)
       → job doc created in Firestore (care_plan_outputs) → Cloud Task enqueued
       → Cloud Run: juno-worker picks up the task (OIDC-verified)
       → five-stage pipeline (term detection, three sequential Gemini/Vertex AI calls)
       → structured output written to the job doc in Firestore
       → client polls via a live Firestore listener, renders the result
       → job explicitly deleted by the client (or by a backstop, §5)
```

- **Auth:** the client signs in anonymously via Firebase (`signInAnonymously()`, no
  email/password) before making any request; the resulting ID token is sent as a
  Bearer token. Full detail, including the trust-boundary fix that prevents this token
  from working against authenticated main-app routes: `docs/trial-architecture.md` §2.
- **Job creation and dispatch:** `POST /trial/jobs` creates a Firestore document and
  enqueues a Cloud Task against a trial-specific queue, so trial traffic can't starve
  main-app job dispatch. Full detail: `docs/trial-architecture.md` §1, §3;
  care-plan-pipeline.md §3.
- **The pipeline itself** (term detection → simplify → clarify actions → structure
  document, against Gemini on Vertex AI): care-plan-pipeline.md §4, in depth.
- **Polling:** there is no dedicated status endpoint — the client attaches a live
  Firestore listener to the job document and reads `status`/`stage` directly
  (`docs/trial-architecture.md` §3).
- **Deletion:** covered in §5 below.

---

## 5. Data, privacy, and auth, in brief

No account, no email, no password: the only identity involved is an anonymous Firebase
Auth UID generated on page load (`docs/trial-architecture.md` §2). What is stored, and
for how long:

| Deletion path | Trigger | Timing |
|---|---|---|
| Explicit client `DELETE /trial/jobs/<id>` | Fires the instant the result screen mounts | Effectively immediate |
| Best-effort delete on page unload | `pagehide`/`visibilitychange` while on the result screen | Immediate, best-effort |
| GCS input cleanup | Worker's `finally` block, every job (success/failure/exception) | End of job execution |
| `input_text` clearing on job completion | `complete_job`/`fail_job` with `clear_input_text=is_trial` | At the moment the job reaches a terminal status |
| Firestore native TTL sweep | `expires_at` = 1 hour after job creation | SLA "typically within 24h" of expiry — worst case ≈ **25 hours** |
| GCS lifecycle rule on `care_plan_trial/` | Bucket-level rule, `age: 1` day | Confirmed live in production (§7) |
| Daily anonymous-Auth-account cleanup | Cloud Scheduler → Cloud Run Job | Confirmed live and end-to-end verified in production, including an actual scheduler-triggered run (§7) |

Worst-case data lifetime for an abandoned job (browser closed mid-processing, user
never returns): **≈25 hours**, driven by the Firestore TTL sweep SLA, not by anything
faster. This is stated plainly in the trial's own Privacy Policy
(`frontend-trial/src/pages/PrivacyPage.tsx`) rather than promising immediacy.

Full treatment of every store, every deletion path, and the deployment-status caveats
on the automated backstops: `docs/trial-architecture.md` §5 (in particular §5.4, which
this document does not repeat — see §7 below for the summary).

**This is not a HIPAA-covered service.** No BAA covers the trial, and users are
instructed not to upload real PHI (both pages disclaim this). The platform's broader
compliance posture and action plan live in
[`docs/hipaa-compliance-action-plan.md`](hipaa-compliance-action-plan.md) — that
document's own scope is the authenticated app's PHI handling, not the trial
specifically; the trial's containment strategy (no login, aggressive deletion, explicit
no-PHI instruction) is a product-level decision layered on top of it.

---

## 6. Engineering safeguards, in brief

- **Per-IP rate limit:** 5 requests/IP/hour, Firestore-backed (not in-memory, since
  Cloud Run instances don't share memory), fixed wall-clock-hour window, fails open on
  a transient Firestore error (an availability choice, not a security boundary).
- **Hard caps, independent of the rate limiter:** 5 files / 10 MB aggregate per
  request, regardless of how many requests an IP has made.
- **Cost backstop:** Cloud Run `max-instances` ceilings (`juno-api`=10,
  `juno-worker`=5) and the trial's own Cloud Tasks queue concurrency limits (5
  concurrent dispatches, 2/sec) bound worst-case Vertex AI spend independently of the
  rate limiter.
- **No content in analytics:** every GA4 event parameter was verified to be one of a
  fixed literal, a count, a category string built from file extensions (not
  filenames), a numeric score/duration, an error-code enum, or a page path — never
  document content, filenames, or extracted text.
- **Idempotent worker:** Cloud Tasks is at-least-once delivery; the worker uses a
  processing-lease pattern keyed on `started_at` so a redelivered task while a prior
  attempt is still within its internal deadline is a no-op, preventing a duplicate
  multi-call LLM run (and duplicate billing) for the same job.

Full mechanics, including the `X-Forwarded-For` trusted-hop derivation and its
topology assumption: `docs/trial-architecture.md` §4.

---

## 7. Current status and known gaps

This section is intentionally candid. Sourced from
`.dev/trial-simplify/final-verification-2026-09-05.md`,
`.dev/trial-simplify/review-2026-09-05-0835.md`,
`.dev/trial-simplify/edge-case-review-backend-2026-09-05.md`,
`.dev/trial-simplify/edge-case-review-frontend-2026-09-05.md`, and the gap sections of
both companion documents, cross-checked directly against the current code.

- **Legal copy is a first draft, not lawyer-reviewed — the stated launch gate.** The
  Privacy Policy and Terms (`frontend-trial/src/pages/PrivacyPage.tsx`,
  `TermsPage.tsx`) were authored to be technically accurate to the implementation, and
  reviewed for that accuracy, but not reviewed or approved by a lawyer. Every source
  document that addresses this (`.dev/trial-simplify/README.md`'s Locked Decisions,
  both review docs) calls this the one item gating launch. Unchanged as of this
  writing.

- **Retention automation is fully deployed and live, verified directly against GCP on
  2026-09-06** (`.dev/trial-simplify/gcp-verification-2026-09-06.md`), resolving the
  prior disagreement between `.dev/trial-simplify/README.md` (said not yet created),
  `gcp-verification-2026-09-05.md` (found TTL active, Scheduler API disabled), and
  `final-verification-2026-09-05.md` (claimed job created and Scheduler enabled):
  - The **GCS lifecycle rule** on `care_plan_trial/` (age-1-day delete) is live on
    production and codified idempotently in `.github/workflows/deploy.yml`. Uncontested
    by any source.
  - The **Firestore TTL policies** on `care_plan_outputs.expires_at` and
    `trial_rate_limits.expires_at` are both live and `ACTIVE`
    (`gcloud firestore fields ttls list`, re-confirmed 2026-09-06). README's
    "not-yet-created" status for this item is stale.
  - The **`juno-trial-anon-cleanup` Cloud Run Job** exists and has two successful
    executions in production: a dry run (`dry_run=True`, scanned=6/matched=0/deleted=0,
    matching `final-verification-2026-09-05.md`'s reported numbers exactly) and, since
    then, a live non-dry-run execution (`dry_run=False`, same scanned=6/matched=0/
    deleted=0) triggered by Cloud Scheduler itself. Its current live config has
    `RETENTION_DRY_RUN=false`.
  - The **Cloud Scheduler trigger** (`juno-trial-anon-cleanup-daily`, `0 4 * * *`
    `Etc/UTC`) exists, is `ENABLED`, and has a recorded real invocation whose timestamp
    matches the Cloud Run Job execution run by `juno-scheduler-invoker` to the
    millisecond — genuine end-to-end proof, not just a config claim. The Cloud Scheduler
    API, found disabled in the 2026-09-05 check, is enabled now; that finding was
    accurate for its own point in time but has since changed.
  See `docs/trial-architecture.md` §5.4 for the full item-by-item breakdown and
  `.dev/trial-simplify/gcp-verification-2026-09-06.md` for the exact commands and
  output this is based on.

- **`MAX_TEXT_BYTES=350,000` is enforced globally, not trial-only — an open product
  decision.** This cap was added for the trial's Firestore document-size safety, but
  `validate_extracted_text_length` (`backend/services/care_plan_input.py:91-133`) is
  shared code, called from both `routes/trial.py` and `routes/care_plan_jobs.py`.
  Effect: the main app's previous 500,000-**character** ceiling is now also bounded by
  350,000 UTF-8 **bytes** — for plain ASCII text that's simply a lower character limit
  than before. `final-verification-2026-09-05.md` §3 flags this as found-but-not-fixed,
  awaiting an explicit owner call on whether the byte cap should be scoped to the trial
  route only (see care-plan-pipeline.md §2.8 for the full mechanics).

- **`backend/cloudbuild.yaml` deploys `juno-api` with `--min-instances=1`**
  (`cloudbuild.yaml:23`), contradicting the project's stated `min-instances=0`
  decision for a trial meant to have no cold-start masking. That fix was applied to
  `rollback-production.yml` only — the far more frequently run automatic deploy path
  (`deploy.yml` → `cloudbuild.yaml`) was never updated, and `deploy.yml`'s subsequent
  `gcloud run services update` step does not pass `--min-instances`, so it never resets
  the value `cloudbuild.yaml` set. **Confirmed live on 2026-09-06**
  (`.dev/trial-simplify/gcp-verification-2026-09-06.md`): `juno-api`'s live
  `autoscaling.knative.dev/minScale` is `1`, not `0` — this is not a theoretical
  reading of the deploy config, it is the value actually running in production right
  now. `juno-worker` is live at effectively `min-instances=0`, as intended. Net effect:
  every merge-to-main auto-deploy currently leaves `juno-api` with at least one
  always-warm instance — better cold-start behavior than documented, but an unreviewed
  deviation from the stated design (full detail: `docs/trial-architecture.md` §8).

- **The `X-Forwarded-For` trusted-hop assumption is topology-specific.** The rate
  limiter reads the client IP from a fixed position in `X-Forwarded-For`
  (`TRIAL_TRUSTED_PROXY_HOPS=1`), correct for the current direct-Cloud-Run topology
  (no external load balancer). If any additional proxy layer (e.g. a Global External
  Application Load Balancer) is ever placed in front of Cloud Run, this constant must
  be updated or the rate limiter will silently collapse all real clients behind that
  proxy onto a single IP bucket (`docs/trial-architecture.md` §4).

- **Search indexing is deliberately allowed.** There is no `noindex` meta tag and no
  `robots.txt` restricting crawlers in `frontend-trial/` (verified: neither exists in
  `frontend-trial/index.html`/`dist/index.html` or as a static file). Cost exposure
  from organic/crawler traffic is therefore bounded only by the per-IP rate limit and
  the Cloud Run `max-instances` ceiling described in §6, not by keeping the site out of
  search results.

Additional accepted (non-blocking) limitations, carried from the companion documents
without restatement here: the rate limiter is a fixed window, not sliding
(`docs/trial-architecture.md` §4); client/server cap duplication between
`backend/utils/constants.py` and `frontend-trial/src/utils/validateFiles.ts` has no
shared source of truth; the rollback workflow only restores the `app` Hosting target,
not `trial`.

---

## 8. Test and verification posture

Reproduced directly, on this branch, on 2026-09-06 (not cited from a report):

- **Backend** (`cd backend && python3 -m pytest tests/ -q`): **684 passed**, 1 warning
  (a pre-existing `PyPDF2` deprecation warning, unrelated to the trial), 24 subtests
  passed, **94% statement coverage** (9,941 statements, 611 missed).
- **`frontend-trial`** (`npm test -- --run`): **19 test files / 103 tests passed.**

Both figures match `final-verification-2026-09-05.md`'s reported numbers exactly,
confirming no regression since that pass. `tsc --noEmit`, `npm run lint`, and
`npm run build` were reported clean in that same document as of 2026-09-05/06 but were
not independently re-run for this document; treat those three as of that date rather
than as freshly confirmed here.

`final-verification-2026-09-05.md` also reports the main `frontend` (full app) suite at
189 passed / 23 files, and describes a set of independently-reproduced integration
checks (upload-limit call sites, `clear_input_text` firing on every terminal worker
path, the worker's processing-lease idempotency math, the `413`-handling path exercised
against a live Flask test client, and the `VITE_API_PROCESSING_URL` build-time guard)
— cite that document directly for the methodology behind each of those, rather than
restating it here.

Earlier review passes (`review-2026-09-05-0835.md`, the two
`edge-case-review-*-2026-09-05.md` documents) found and fixed several blocking issues
before this state was reached — including the anonymous-token trust-boundary bypass
(§4/§5 above), a race that briefly blanked the result screen, and an unescaped
interpolation in the PDF-report path with a `window.opener` risk. All are recorded as
fixed and independently re-verified in the later passes; see those documents for the
specific commits.

---

## 9. Where to read next

- [`docs/trial-architecture.md`](trial-architecture.md) — the trial's own architecture
  in full depth: topology, auth trust boundary, API surface, rate limiting, every data
  deletion path and its deployment status, frontend structure, GA4 analytics, CI/CD,
  and legal surface.
- [`docs/care-plan-pipeline.md`](care-plan-pipeline.md) — the processing pipeline in
  full depth: input extraction, image OCR, the five simplification stages, term
  detection, scoring, and error taxonomy.
- [`docs/backend-infrastructure.md`](backend-infrastructure.md) — backend service
  infrastructure generally.
- [`docs/logging.md`](logging.md) — observability: fields, query recipes, adding a new
  marker.
- [`docs/setup_gcloud_deployment.md`](setup_gcloud_deployment.md) — GCP/deployment
  setup.
- [`docs/local-development.md`](local-development.md) — running the app locally.
- [`docs/hipaa-compliance-action-plan.md`](hipaa-compliance-action-plan.md) — the
  platform's broader HIPAA/compliance posture and action plan (the authenticated app's
  scope, not the trial specifically).
- `.dev/trial-simplify/` — the full decision record for the trial's build-out:
  `README.md` (locked decisions, manual-steps checklist, infrastructure status),
  `brainstorm.md`, per-subproject PRDs (`01-image-input/` through
  `06-trial-optimizations/`), and the dated review/verification documents cited
  throughout this document and `docs/trial-architecture.md` §5.4.
