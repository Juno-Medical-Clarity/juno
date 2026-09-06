# Juno Documentation Index

This is the reading guide for `docs/` and the surrounding documentation on branch
`users/tejitpabari/trial-optimizations`, as of 2026-09-06. It exists so a reader (human
or agent) can find the right document without opening all of them.

**Source of truth.** The code is authoritative. `docs/` describes the system as built
and is kept close to the code, but can drift. `.dev/` is decision history for the trial
build-out (PRDs, task lists, run artifacts, reviews) — it records why things were done a
certain way at a point in time, and can be stale where later work superseded it. In
particular, `.dev/trial-simplify/README.md`'s "Infrastructure already provisioned"
section makes several live-infra claims (e.g. that `min-instances=0` "now holds with no
exceptions") that a later, read-only GCP check —
[`.dev/trial-simplify/gcp-verification-2026-09-06.md`](../.dev/trial-simplify/gcp-verification-2026-09-06.md)
— found to be wrong at the time it ran (`juno-api` was live at `min-instances=1`, not
`0`). Where the two disagree, trust the 2026-09-06 verification doc, and ultimately trust
a fresh check against live GCP over any document.

---

## 1. Every doc in `docs/`

| File | What it covers | Who should read it, and when |
|---|---|---|
| [`trial-overview.md`](trial-overview.md) | Entry point for the public trial: what Juno's Simplify pipeline does, what the trial is and why it exists, the user experience end to end, a brief architecture summary, and a candid "current status and known gaps" section (including test/verification posture). Deliberately shallow on internals; hands off to the two docs below by section number. | Anyone who wants to understand the trial. Read this first, always. |
| [`trial-architecture.md`](trial-architecture.md) | Deep reference for the trial system itself: hosting/system topology, the anonymous-auth trust boundary, the `/trial/*` API surface, rate limiting and abuse protection, every data-deletion path and its live deployment status, the `frontend-trial/` frontend structure, GA4 analytics, CI/CD, the legal-copy surface, and known gaps. Explicitly out of scope: the processing pipeline internals (cross-referenced to `care-plan-pipeline.md` by section) and the full app's non-trial surfaces. | Engineers working on trial infra, auth, rate limiting, retention/deletion, CI/CD, or legal copy. |
| [`care-plan-pipeline.md`](care-plan-pipeline.md) | Deep reference for the backend processing pipeline shared by the authenticated app (`POST /care_plan/jobs`) and the trial (`POST /trial/jobs`): input acquisition and text extraction (including the image/OCR path via Gemini on Vertex AI), async job orchestration via Firestore + Cloud Tasks, the five simplification stages, the medical-term/jargon database, readability scoring, observability, and the error taxonomy. Explicitly out of scope: datasets/Athena, admin, saved outputs, batch jobs — full-app-only surfaces. | Engineers working on the pipeline, extraction, scoring, or debugging a specific job's behavior. |
| [`backend-infrastructure.md`](backend-infrastructure.md) | Architectural (not step-by-step) description of the backend's infrastructure shape: Flask/Gunicorn runtime, Cloud Run hosting, the service dependency table (Cloud Build, Artifact Registry, Firebase Auth, Firestore, GCS, Secret Manager, Vertex AI, Cloud Logging/Trace), data architecture, the auth/request boundary, deployment architecture, and a logging runbook pointer. Predates the trial's two-service (`juno-api`/`juno-worker`) split described in `setup_gcloud_deployment.md` and `trial-architecture.md` §1 — still broadly accurate but written at a coarser grain. | Anyone wanting a map of what cloud services the backend depends on and why, before diving into deployment specifics. |
| [`logging.md`](logging.md) | The single home for Juno observability: the three correlation IDs (`trace_id`, `span_id`, `session_id`) and how they relate, working Cloud Logging/Trace/Metrics Explorer queries, the code-marker developer guide for adding instrumentation, the full `jsonPayload` field reference, and `gcloud` logging recipes. | Anyone debugging a production issue, adding a new instrumentation point, or querying logs/traces/metrics. |
| [`datasets.md`](datasets.md) | Catalog of every dataset integrated into the preset-data pipeline (doctor-patient conversations, clinical Q&A, text-simplification corpora), with source links, sample counts, parsing notes, and how to reproduce parsing; also lists PhysioNet-gated datasets and how to add a new one. Not related to the trial. | Anyone working with `preset-data/`, dataset presets, or grading/evaluation data. |
| [`hipaa-compliance-action-plan.md`](hipaa-compliance-action-plan.md) | HIPAA status and gap-remediation plan for the platform generally (dated 2026-06-28, and framed around the authenticated, clinician-facing app): PHI surface map, data flows, a prioritized (P0–P4) list of compliance gaps, a share-link security analysis, planned-feature HIPAA implications, and a vendor BAA tracker. Does not cover the trial's own privacy posture (anonymous, no clinician relationship) — see `trial-architecture.md` §9 and `trial-overview.md` §5 for that. | Anyone assessing compliance risk on the authenticated app, or triaging the P0–P4 gap list. |
| [`local-development.md`](local-development.md) | How to run `backend/` and `frontend/` locally: prerequisites, env file setup, running the full app, running only the frontend against the production backend, useful commands, and troubleshooting. Written for the authenticated app; does not mention `frontend-trial/`. | Anyone setting up a local dev environment for the authenticated app. |
| [`setup_gcloud_deployment.md`](setup_gcloud_deployment.md) | Step-by-step runbook to recreate Juno's GCP/Firebase infrastructure from scratch: the `juno-api`/`juno-worker` Cloud Run service topology, API enablement, Firebase product setup, Cloud Storage/Artifact Registry/Cloud Build, the GitHub Actions deploy service account and IAM, Cloud Tasks + worker OIDC security, Gemini/Vertex AI setup, GitHub secrets and repo configuration checklists, first deploy, production tagging, git-based rollback, post-deploy verification, and common failure modes. | Whoever provisions or rebuilds cloud infrastructure, sets up CI/CD secrets, or is debugging a deploy failure. |
| [`public-version-scope.md`](public-version-scope.md) | **Superseded — see note below.** An earlier design proposal for a public/B2C version of Juno: `DEPLOYMENT_MODE=public/internal` env-var split, separate `CarePlanV1_2Public`/`CarePlanV1_2Internal` models, a `public_care_plan_outputs` Firestore collection, session-token (not Firebase) anonymous auth, and a "login to save"/account-claim flow. | Historical interest only — read `trial-overview.md` and `trial-architecture.md` instead for what was actually built. |
| `agent_files/` (directory, not a single doc — see below) | Athena Health EHR API exploration: sample API responses, a CSS/HTML injection script for encounter exports, and research notes on Athena integration, EHR/clinic compliance requirements, and a HIPAA compliance roadmap (all dated June 2026), plus two dated `tasks/` folders from an earlier, pre-`.dev/` task-tracking convention. Unrelated to the trial. | Anyone investigating a future EHR/Athena integration, or archaeology on how the project's task-tracking evolved before `.dev/`. |

### `public-version-scope.md` is superseded

This document is stale. It proposes a materially different design from what was actually
built: a `DEPLOYMENT_MODE` env-var toggling separate public/internal backend instances
and frontend ports, a parallel `CarePlanV1_2Public` model and `public_care_plan_outputs`
collection, session-token-based anonymous auth, and a "login to save"/`POST
/public/claim/{job_id}` flow to convert an anonymous session into a real account. None of
this exists in the codebase or in `.dev/trial-simplify/`. What was actually built and
shipped (documented in `trial-overview.md` and `trial-architecture.md`) is simpler and
different in almost every particular: a separate `frontend-trial/` Vite app (not a env
flag), real Firebase Anonymous Auth (`signInAnonymously()`) sharing the existing
`@verify_firebase_token`/job pipeline, trial jobs living in the *same*
`care_plan_outputs` collection marked `is_trial: true` with an `expires_at` TTL field (no
separate public collection), and a purely ephemeral trial with **no** account-linking or
"save permanently" path at all. `trial-overview.md`'s own "Where to read next" section
(§9) does not list `public-version-scope.md`, which is itself a signal it was left behind
once the trial's real design (`.dev/trial-simplify/brainstorm.md` onward) diverged from
it. Treat `public-version-scope.md` as historical only.

### `agent_files/` in more detail

`docs/agent_files/` predates the trial work and predates `.dev/`. It holds:
- `athena-bruno/` — sample Athena Health API responses (Postman-style JSON collections)
  and encounter-download scripts, used to explore what an EHR integration would look
  like.
- `athena-encounters.css` / `inject-css.py` — a stylesheet and injection script for
  rendering Athena encounter-summary HTML exports.
- `research/` — three research memos (all explicitly flagged as non-legal-advice
  planning resources, dated June 2026): `athena-health-api-integration.md`,
  `ehr-clinic-compliance-requirements.md`, `hipaa-compliance-juno.md`.
- `tasks/2026-06-27/` and `tasks/2026-06-29/` — dated, numbered task folders from an
  earlier task-tracking convention that predates `.dev/`'s PRD/TASKS structure.

None of this is part of the trial or the current pipeline; it's retained context for a
possible future EHR integration.

---

## 2. Reading paths

### "I want to understand the trial version" (start here if this is your goal)

1. [`trial-overview.md`](trial-overview.md) — read start to finish. It's the entry point
   and is deliberately shallow; it tells you what the trial is, why it exists, what a
   user does, and gives you the vocabulary (job docs, `is_trial`, anonymous auth,
   expiry) the deeper docs assume.
2. [`trial-overview.md` §7 "Current status and known gaps"](trial-overview.md) — read
   this specifically before anything else, even before the deep docs, because it tells
   you what to be skeptical of in the rest of the material.
3. [`trial-architecture.md`](trial-architecture.md) §1–2 (topology, auth and the trust
   boundary) — understand where the trial's traffic goes and why an anonymous Firebase
   user is trusted at all.
4. [`trial-architecture.md`](trial-architecture.md) §3–4 (API surface, rate limiting) —
   the actual `/trial/jobs` contract and what stops abuse.
5. [`trial-architecture.md`](trial-architecture.md) §5 (data management) — every
   deletion path and, critically, §5.4's "what is actually live vs. code-complete but
   unconfirmed" — this is the section most likely to be ahead of what's really deployed.
6. [`care-plan-pipeline.md`](care-plan-pipeline.md) — once you know the trial's shape,
   read the pipeline it invokes: input extraction, OCR, the five stages, scoring. Read
   this fourth, not first, because the trial docs assume you know what a "job doc" and
   "worker" are, which this document defines in depth.
7. [`trial-architecture.md`](trial-architecture.md) §6–9 (frontend, analytics, CI/CD,
   legal) — the remaining surface area, useful once you have the core model.
8. [`.dev/trial-simplify/gcp-verification-2026-09-06.md`](../.dev/trial-simplify/gcp-verification-2026-09-06.md)
   — the most current, independently-checked answer to "what is actually live in GCP
   right now," which supersedes both the architecture doc's aspirational claims and
   `.dev/trial-simplify/README.md`'s infra-status section.
9. (Optional, if you want the "why") [`.dev/trial-simplify/README.md`](../.dev/trial-simplify/README.md)
   and `brainstorm.md` — see the design-history reading path below.

### "I want to understand how the processing works end to end"

1. [`care-plan-pipeline.md`](care-plan-pipeline.md) §1 — the one-document journey
   diagram; get the shape of client → API → Firestore → worker before the detail.
2. [`care-plan-pipeline.md`](care-plan-pipeline.md) §2 — input acquisition and
   extraction, including the image/OCR path.
3. [`care-plan-pipeline.md`](care-plan-pipeline.md) §3 — async job orchestration: the
   Firestore job document as a state machine, the Cloud Tasks handoff, idempotency.
4. [`care-plan-pipeline.md`](care-plan-pipeline.md) §4–5 — the five simplification
   stages and the output shape they produce.
5. [`care-plan-pipeline.md`](care-plan-pipeline.md) §6–7 — term detection/jargon
   database and scoring.
6. [`care-plan-pipeline.md`](care-plan-pipeline.md) §8–10 — observability, error
   taxonomy, and known sharp edges, so you know what's brittle before you touch it.
7. [`logging.md`](logging.md) — once you understand the pipeline's stages, this shows
   you how to actually observe one running (trace/span/session IDs, query recipes).

### "I want to run it locally"

1. [`local-development.md`](local-development.md) — the whole thing, in order:
   prerequisites, env files, running backend + frontend, troubleshooting. Covers the
   authenticated app (`backend/` + `frontend/`).
2. Root [`README.md`](../README.md) — the condensed quick-start version; useful as a
   refresher once you've done the full setup once.
3. For `frontend-trial/`, there is no dedicated local-dev doc; follow the same backend
   setup from `local-development.md`, then run `frontend-trial/` the same way as
   `frontend/` (`npm install`, copy its `.env.local.example`, `npm run dev`) — see
   [`trial-architecture.md`](trial-architecture.md) §6 for how it differs from
   `frontend/` (shared components via a path alias, no auth UI).

### "I want to deploy or operate it"

1. [`setup_gcloud_deployment.md`](setup_gcloud_deployment.md) — the full runbook:
   service topology, IAM, secrets, first deploy, rollback, post-deploy verification, and
   common failure modes. This is the operational source of truth.
2. [`backend-infrastructure.md`](backend-infrastructure.md) — the higher-level "what
   depends on what" map, useful context before or alongside the runbook.
3. [`trial-architecture.md`](trial-architecture.md) §8 "CI/CD and deploy" — what's
   specific to the trial: the multi-target Hosting setup, the `workflow_run`-gated
   auto-deploy, and the `rollback-production.yml` gotcha history.
4. [`logging.md`](logging.md) — once it's deployed, this is how you watch it.
5. [`.dev/trial-simplify/gcp-verification-2026-09-06.md`](../.dev/trial-simplify/gcp-verification-2026-09-06.md)
   — the latest ground truth on what's actually live (min-instances values, TTL state,
   the cleanup job/scheduler), useful for a sanity check against what the runbook says
   *should* be true.

### "I want to understand data handling, privacy, and compliance"

1. [`trial-overview.md`](trial-overview.md) §5 "Data, privacy, and auth, in brief" — the
   short version, for the trial.
2. [`trial-architecture.md`](trial-architecture.md) §5 "Data management" — the long
   version: what's stored, every deletion path and its timing, worst-case data lifetime,
   and what's actually live vs. aspirational.
3. [`trial-architecture.md`](trial-architecture.md) §9 "Legal/compliance surface" — the
   trial's Privacy Policy/Terms and their accuracy against the code.
4. [`hipaa-compliance-action-plan.md`](hipaa-compliance-action-plan.md) — the
   authenticated app's broader HIPAA posture and open gaps (different scope: clinician
   relationship, PHI, BAAs — the trial is explicitly a different, B2C-without-clinicians
   posture, see `trial-overview.md` §2).
5. `docs/agent_files/research/hipaa-compliance-juno.md` and
   `ehr-clinic-compliance-requirements.md` — older, broader research memos if you need
   regulatory background beyond the action plan (both explicitly flagged as non-legal-advice).

### "I want the design history and why decisions were made the way they were"

Everything here lives in [`.dev/trial-simplify/`](../.dev/trial-simplify/), which is
decision history, not a description of the current system — see the source-of-truth note
above. Artifact types, in the order they were produced for each sub-project:

1. **`brainstorm.md`** — the original brainstorm and locked decision log (D1–D11) for the
   whole trial initiative. Read this first for "why does the trial look the way it
   does" — hosting layout, auth model, rate-limit numbers, what was explicitly rejected.
2. **`README.md`** (the `.dev/trial-simplify/` one, not this file) — the PRD index: an
   overview, current implementation/verification status, the locked-decisions summary,
   the SP1–SP6 table, dependency graph, infrastructure-provisioned checklist, and
   consolidated manual/owner-only steps. The single best orientation document for the
   whole decision record — but see the source-of-truth note above about its stale
   infra-status claims.
3. **`PRD.md`** (one per `NN-name/` sub-project folder) — the actual design document for
   that sub-project: scope, goals, non-goals, detailed design, open questions (marked
   `[OPEN]`/`[RESOLVED]`/`[DEFERRED]`), and manual-steps sections.
4. **`TASKS.md`** (one per sub-project) — the junior-dev-followable task breakdown
   generated from that PRD.
5. **`code-<timestamp>.md`** (one per sub-project) — the run artifact from actually
   implementing the tasks: what was built, what changed, and any deviations from the
   PRD.
6. **`review-<timestamp>.md`** — independent post-implementation code review artifacts
   (bug/security/architecture personas), with findings and their fix status. Two exist:
   one for SP1+SP2 merged, one for the full SP1–SP5 branch.
7. **`edge-case-review-backend-2026-09-05.md`** / **`edge-case-review-frontend-2026-09-05.md`**
   — a later, deeper adversarial pass specifically hunting edge cases (malformed input,
   race conditions, limits) after SP6 landed, separate from the standard review artifacts.
8. **`scenario-validation-2026-09-05.md`** — end-to-end scenario testing (11 named
   scenarios: typical use, phone-photo OCR, batch limits, degenerate inputs, races,
   rate limiting, access control) run against the fixed code.
9. **`final-verification-2026-09-05.md`** — an independent re-verification pass that
   re-ran everything rather than trusting prior reports' summaries; the most trustworthy
   single "is this actually done" document short of a fresh live check.
10. **`gcp-verification-2026-09-05.md`** and **`gcp-verification-2026-09-06.md`** — live,
    read-only `gcloud`/`firebase` checks against the actual GCP project, verifying claims
    made elsewhere in the decision record against reality. The 09-06 one is later and
    supersedes the 09-05 one and the README's infra-status section wherever they
    conflict (see the source-of-truth note above and the SP table below).
11. **`optimization-findings-2026-09-05.md`** — a read-only investigation of
    latency/cost/payload optimization opportunities in the trial pipeline that motivated
    SP6.

---

## 3. Map of `.dev/trial-simplify/`

### Sub-projects (SP1–SP6)

| SP | Name | Scope (one line) |
|---|---|---|
| SP1 | Image Input Support | Add `png/jpg/jpeg/webp/heic` to the shared `ALLOWED_EXTENSIONS`, a Gemini-vision (Vertex) extraction path in `care_plan_input.py`, and image embedding into the combined PDF. Benefits the main app and the trial. |
| SP2 | Trial Backend Route, Rate Limiting & Retention | The new `/trial` route family (`POST`/`DELETE /trial/jobs/<id>`) reusing existing job-creation helpers; a Firestore-backed per-IP rate limit (5/hour); `is_trial`/`expires_at` fields on the shared `care_plan_outputs` collection; GCS input cleanup after extraction. |
| SP3 | Trial Frontend App | The new `frontend-trial/` Vite app: upload → processing (live steps) → results screens, anonymous-auth wiring, GA4 instrumentation, download-report reuse, best-effort `DELETE` on unload. |
| SP4 | Hosting Split, CI & Legal Pages | Multi-target `firebase.json`/`.firebaserc` (`app` + `trial`); `deploy.yml` gains a trial build/deploy job and fixes `rollback-production.yml`; CORS widened for `juno-app-99.web.app`; Privacy Policy + Terms & Conditions copy. |
| SP5 | Retention Automation | Firestore native TTL on `care_plan_outputs`/`trial_rate_limits`; a daily Cloud Scheduler → Cloud Run Job deleting anonymous Auth users older than 24h. |
| SP6 | Trial Pipeline Optimizations | Backend-only follow-on on this branch: trims trial grading output to `combined`-only entries, populates the previously-always-`None` `Metrics.total_duration_ms`, and overlaps the `before`-grading score computation with the pipeline's LLM calls. |

Each `NN-name/` folder holds that sub-project's `PRD.md`, `TASKS.md`, and one or more
`code-<timestamp>.md` run artifacts (see the artifact-type list above).

### Standalone review/verification artifacts

| File | What it is |
|---|---|
| `brainstorm.md` | Original brainstorm + locked decision log (D1–D11) for the whole trial initiative. |
| `review-2026-09-05-0554.md` | Code review of SP1+SP2 merged; one must-fix finding, fixed. |
| `review-2026-09-05-0835.md` | Code review of the full SP1–SP5 branch, three personas; five findings, all fixed and re-verified. Verdict: PASS. |
| `edge-case-review-backend-2026-09-05.md` | Deep adversarial edge-case review of the backend trial pathway on this branch; 10 findings (3 blocking). |
| `edge-case-review-frontend-2026-09-05.md` | Same, for `frontend-trial/`; no blocking findings, 8 should-fix/nice-to-have. |
| `scenario-validation-2026-09-05.md` | 11 end-to-end scenarios run against the fixed code; all pass. |
| `final-verification-2026-09-05.md` | Independent re-verification pass re-running everything from scratch; flags one unresolved product decision (a global text-length cap side effect on the main app). |
| `gcp-verification-2026-09-05.md` | Live, read-only GCP check scoped to SP5's retention-automation checklist. |
| `gcp-verification-2026-09-06.md` | Later, broader live GCP check; supersedes the 09-05 check and the README's infra-status claims wherever they conflict. |
| `optimization-findings-2026-09-05.md` | Read-only investigation of pipeline latency/cost/payload optimizations that motivated SP6. |

---

## 4. Where the code lives

| Path | What's there |
|---|---|
| `backend/routes/` | Flask blueprints: `care_plan_jobs.py` (authenticated pipeline jobs), `trial.py` (public trial jobs), `worker.py` (the async worker endpoint both call into), plus `saved_outputs.py`, `batch_jobs.py`, `datasets.py`, `clinician_dataset.py`, `admin.py`, `grading.py` (full-app-only surfaces). |
| `backend/services/` | `care_plan_input.py` (input acquisition/extraction), `care_plan_pipeline.py` (the five-stage pipeline orchestration), `retention.py` (cleanup logic), `external_api/`. |
| `backend/care_plan/` | The versioned care-plan interface and model implementations (`v1_2/`). |
| `backend/utils/` | Shared utilities: `rate_limit.py`, `image_ocr.py`, `jargon_db.py`, `term_detection.py`, `scoring.py`/`scoring_methods.py`, `gcs.py`, `cloud_tasks.py`, `firebase.py`, `job_helpers.py`, `markers/` (observability). |
| `frontend/` | The full authenticated app (React + Vite), deployed to `juno-app-99.web.app`. |
| `frontend-trial/` | The public, no-login trial app (separate Vite build), deployed to `juno-medical-clarity.web.app`, sharing select components from `frontend/src` via a path alias. |
| `.github/workflows/` | `ci.yml`, `deploy.yml` (auto-deploy on merge to `main`, includes the trial build/deploy job), `preview.yml` (PR previews), `rollback-production.yml`. |
