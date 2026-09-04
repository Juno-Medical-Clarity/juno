# Juno Trial — Bare-Bones Public Simplify Page

Brainstorm + decision log. Status: **decisions locked, ready for PRD/tasks.**
Date: 2026-09-04

## 1. Goal

A single-page, no-login, no-storage public trial of Juno's care-plan simplification, hosted at the project's primary web address, shareable with anyone. The existing full app moves to a separate Hosting site. **Additive only** — existing frontend and backend code is not overridden.

## 2. Product Scope (from the user)

### Input screen
- Upload files: **PDF, TXT, DOCX, and images**. Hard limit **5 files**.
- Paste text box (alternative input).
- **No preset datasets.** None of the dataset/Athena/GCS preset UI.
- **No grading option shown.** Grading runs by default, server-side.
- One button: **"Simplify"**.
- Footer: "No data is saved. All data is deleted." + links to **Privacy Policy** and **Terms & Conditions**.

### Processing screen
- Shows the pipeline steps as they execute (live progress).

### Results screen
- Care plan **title**.
- **Date** underneath (just the date — not "Simplified on <date>").
- The simplified care plan body.
- Score: **before → after only**, composite 0–100. No sub-score breakdown.
- One button: **Download report**.

### Explicitly excluded from results
No "Show original", no session ID, no trace ID, no "Another care plan" button, no score breakdown, no Download JSON, no grading UI, no sharing, no notes, no saved-outputs sidebar, no login, no navbar chrome from the main app.

## 3. What Exists Today (survey findings)

| Area | Current state | Implication for the trial |
|---|---|---|
| Backend auth | Every route gated by `@verify_firebase_token` (`backend/utils/firebase.py`) | A no-login page needs either anonymous auth or a new unauthenticated route |
| Job flow | Async: `POST /care_plan/jobs` → Cloud Tasks → `juno-worker` → Firestore doc → frontend live-subscribes via `useJobSnapshot` | Live step display comes free if we keep this flow |
| Storage | Input files → GCS bucket `juno-medical-clarity-backend`; results → Firestore | "Nothing is saved" must mean "deleted immediately after processing", not "never written" |
| File types | `ALLOWED_EXTENSIONS = {pdf, txt, docx, html, htm}`, `MAX_FILE_BYTES = 10MB`, `MAX_FILE_COUNT = 10` (`backend/utils/constants.py`) | **Images are not supported** — net-new extraction path |
| Scoring | `backend/utils/scoring.py` produces a 0–100 composite + sub-scores | Composite before/after is free |
| Grading envelope | `GradingEntry` already has `target: 'before' \| 'after'` and `grade` (`frontend/src/types/envelope.ts`) | Before→after is natively representable; no new data model |
| Report | `frontend/src/utils/buildPdfHtml.ts` already builds a PDF report | Reuse directly for "Download report" |
| Frontend | One Vite app, `frontend/`, deployed to Firebase Hosting site `juno-medical-clarity` | Needs a second Hosting site + second build target |
| Hosting config | `frontend/firebase.json` has a single unnamed `hosting` block; `.firebaserc` default project `juno-medical-clarity` | Must become a two-target `hosting` array with deploy targets |
| Cloud Run | `juno-api` + `juno-worker`, deployed by `.github/workflows/deploy.yml` (manual `workflow_dispatch`) | Trial reuses both services; CI gains a trial-frontend deploy job |

## 4. Decision Log

| # | Decision | Chosen | Rejected alternatives & why |
|---|---|---|---|
| D1 | Auth model | **Anonymous Firebase Auth.** Trial frontend calls `signInAnonymously()` on load; user never sees a login. Existing `@verify_firebase_token` and the whole job pipeline work unchanged. | *New public unauthenticated endpoint* — cleanest privacy story but loses live step streaming (SSE from scratch), risks the 300s Cloud Run timeout on synchronous processing, and needs new rate-limit plumbing. *Async public endpoint with job tokens* — keeps streaming but requires new auth-free security rules and token plumbing for no real gain over anonymous auth. |
| D2 | Hosting layout | **Trial takes the primary site** `juno-medical-clarity.web.app`. No custom domain exists. The full app moves to a NEW Firebase Hosting site `juno-app` (`juno-app.web.app`), created by us in the same Firebase project `juno-medical-clarity`. | *Trial on a new subdomain* — safer but doesn't put the trial at the primary URL, which is the stated goal. Accepted cost: existing links/bookmarks to the full app break and must be re-shared. |
| D3 | Frontend structure | **Separate Vite build in the same repo**: new `frontend-trial/` with its own `package.json`, `vite.config.ts`, and deploy target. Shares `CarePlanView`, `renderMarkdown`, `buildPdfHtml`, and `types/` from `frontend/src` via a path alias. | *New `/trial` route in the existing app* — least wiring, but ships the entire app bundle and Firebase config to public visitors and couples the two deploys. *Fully separate duplicated app* — max isolation but duplicates care-plan rendering, which then drifts. |
| D4 | Abuse protection | **Per-IP rate limit + hard caps**: in-app per-IP throttle on the trial job route, 5-file / 10MB caps, and a Cloud Run `max-instances` ceiling so cost cannot run away. Invisible to normal users. | *Turnstile/CAPTCHA* — stronger but adds friction and a third-party script. *Caps only* — accepts sustained hammering until the instance ceiling throttles. |
| D5 | Image input | **Yes, supported — and added to the main app too.** User approved widening the shared allowed-extension set rather than scoping it to the trial. Add `png/jpg/jpeg/webp/heic` to `ALLOWED_EXTENSIONS` in `backend/utils/constants.py` and a Gemini vision extraction path in `backend/services/care_plan_input.py`. Both the main app and the trial gain image support. | *Trial-scoped extension set* — was the earlier plan to avoid changing main-app behaviour; user explicitly approved changing the main app, so the simpler shared approach wins. |
| D6 | Score displayed | **Composite 0–100, before → after.** Nothing else. | Reading grade level; both metrics. User wants the minimum. |
| D7 | Cold starts | **`min-instances=0`, no masking UI.** First visitor after idle waits ~15–30s; that is acceptable. | Warm instance (~$15–35/mo idle); scheduled warm window. Cost not justified for a trial. |
| D8 | Legal copy | **Claude drafts, user reviews before ship.** Plain-language Privacy + Terms pages covering: Google Cloud / Vertex AI and Firebase process submitted content; data deleted immediately after processing; no accounts; no tracking. Plus a prominent "do not upload real patient information" notice. Not legal advice. | Footer disclaimer only — too thin for health-adjacent public sharing. |
| D9 | Data cleanup cron | **Yes, as a final stretch phase.** Firestore native TTL on the trial job collection (free, config-only) + a daily Cloud Scheduler → Cloud Run job that deletes anonymous Firebase Auth users older than 24h. Cost: cents/month. | No cleanup — anonymous Auth accounts accumulate indefinitely. |
| D10 | Analytics | **Google Analytics 4, measurement ID `G-4R0CDYKSPW`, instrumented copiously** across the trial app: page views, input mode chosen (file vs paste), file count/type, Simplify clicked, each pipeline step start/complete, total duration, success/error, report downloaded, privacy/terms clicks. **Hard rule: no document content, filenames, or care-plan text may ever be sent as an event parameter — counts, enums, and timings only.** | *No analytics* — user explicitly wants usage measurement. |
| D11 | Rate limit | **5 simplifications per IP per hour** on the trial job route. | Higher/lower caps; user specified this number. |

## 5. Zero-Retention Design

Honest framing: data **is** written (GCS + Firestore) because the async pipeline requires it, then deleted. The privacy copy says "deleted immediately after processing", never "never stored". Note also that Google Analytics is active on the trial pages (see D10) — the privacy copy must disclose it, and no document content may ever be included in an analytics event.

Three layers, defence in depth:
1. **Worker deletes the GCS input object** immediately after text extraction completes.
2. **Frontend fires `DELETE /trial/jobs/<id>`** once the result has rendered.
3. **Firestore native TTL** (e.g. 1 hour) on a dedicated `trial_jobs` collection as the safety net if the browser closes early.

Trial jobs live in their own Firestore collection (`trial_jobs`), never mixed with real user data, with their own security rules and TTL policy.

## 6. Proposed Architecture (additive)

### New backend
- `backend/routes/trial.py` — new blueprint: `POST /trial/jobs`, `GET /trial/jobs/<id>`, `DELETE /trial/jobs/<id>`. Reuses `care_plan_pipeline` unchanged.
- `backend/utils/rate_limit.py` — per-IP throttle decorator (Firestore-backed counter; in-memory is unreliable across autoscaled instances).
- Image extraction path added to `backend/services/care_plan_input.py`.
- **Risk:** widening `ALLOWED_EXTENSIONS` globally would change the main app's behaviour. The trial route must pass its own allowed-extension set rather than mutating the shared constant. Non-negotiable.

### New frontend
`frontend-trial/` — four screens: input, processing (live steps), results, and `/privacy` + `/terms` static pages.
- **Risk:** aliasing into `frontend/src` may drag in the auth context and router through `CarePlanView`'s import graph. If it does, copy the minimal renderer instead of sharing. The implementing agent decides after tracing the graph.

### Hosting / CI
- `frontend/firebase.json` (or a root one) becomes a two-target `hosting` array; `.firebaserc` gains deploy targets `app` and `trial`.
- `.github/workflows/deploy.yml` gains a `deploy-trial-frontend` job; the existing frontend job retargets to `hosting:app`.

## 7. Phasing

| Phase | Content |
|---|---|
| **P0** | ~~Merge PR #35~~ DONE. Branch `users/tejitpabari/trial-app` cut from `main`. DONE. |
| **P1 — Backend** | Trial blueprint, per-IP rate limit, trial-scoped extension set, image extraction, delete endpoint + GCS cleanup. |
| **P2 — Frontend** | `frontend-trial/` app: input, live steps, results, download report. |
| **P3 — Hosting & legal** | Two-site Hosting split, CI deploy job, Privacy + Terms pages, footer copy. |
| **P4 — Ship** | Deploy, smoke test, verify deletion actually happens end to end. |
| **P5 — Stretch** | Firestore TTL policy + daily anon-user cleanup job (D9). |

Riskiest items: the image extraction path (P1) and the Hosting split (P3), because the latter briefly touches the live site.

## 8. Owner-Only Tasks (user must do these)

- [x] Merge PR #35 (https://github.com/Juno-Medical-Clarity/juno/pull/35). — DONE
- [x] Enable the **Anonymous** sign-in provider in the Firebase console. — DONE
- [x] Create the second Firebase Hosting site — **delegated to us**, not owner-only.
- [ ] Review and approve the Privacy Policy and Terms copy before launch.

## 9. Resolved Inputs

- **Custom domain:** none. Trial serves from `juno-medical-clarity.web.app`.
- **Full app relocates to:** `juno-app.web.app` (new Hosting site, same Firebase project).
- **Firebase / GCP project ID:** `juno-medical-clarity`.
- **Rate limit:** 5 simplifications per IP per hour.
- **Analytics:** GA4 `G-4R0CDYKSPW`, copious instrumentation, no content in event params.
- **Image support:** added to the main app as well, not trial-scoped.

## 10. Remaining Unknowns

1. **Care plan title** — does the output envelope carry a title field, or must the results screen derive one from content? Verify during P2.
2. **Privacy copy vs. GA** — the footer cannot claim "no tracking". Agreed wording: document content is never stored, but Google Analytics measures usage, disclosed explicitly in the Privacy Policy.
