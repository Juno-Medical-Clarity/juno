# Trial Application Architecture

**Scope of this document.** This is a reference for how Juno's public, no-login trial
(`frontend-trial/` + `backend/routes/trial.py` + the supporting hosting/CI/retention
infrastructure) is built and operated end to end — topology, auth, the API surface,
abuse protection, data lifecycle, frontend structure, analytics, CI/CD, and legal
copy — as implemented on branch `users/tejitpabari/trial-optimizations` as of
2026-09-06.

**Out of scope.** The processing pipeline itself — input extraction, OCR, the five
simplification stages, term detection, scoring, error taxonomy — is covered in depth in
[`docs/care-plan-pipeline.md`](care-plan-pipeline.md); this document cross-references it
by section (`§N`) rather than repeating it. The full authenticated app's own surfaces
(datasets/Athena presets, admin, saved outputs, batch jobs, grading UI) are likewise out
of scope except where the trial's existence changes something about them (CORS, hosting
target, `min-instances`).

Source pointers use the form `path:line`. Line numbers are for orientation; verify
against the current file. Where this document states something about live GCP
infrastructure rather than checked-in code, it says so explicitly and cites its source,
because code alone cannot prove what is actually deployed.

---

## 1. System topology

```
                              ┌─────────────────────────────┐
                              │   Firebase Hosting project    │
                              │      juno-medical-clarity      │
                              │                                │
  Public internet             │  site: juno-medical-clarity ───┼──► target "trial"
  ───────────────────────────►│    (primary address)           │    frontend-trial/dist
                              │                                │
                              │  site: juno-app-99 ────────────┼──► target "app"
  (workflow_dispatch only) ──►│    (relocated full app)        │    frontend/dist
                              └─────────────────────────────┘
                                          │  fetch() with Firebase ID token (Bearer)
                                          ▼
                       ┌──────────────────────────────────────┐
                       │  Cloud Run: juno-api (JUNO_MODE=api)   │  max-instances=10
                       │  allow-unauthenticated, public HTTPS   │  min-instances=1 (live; §8)
                       │  routes/trial.py, care_plan_jobs.py,…  │
                       └───────────────┬────────────────────────┘
                                       │ create job doc            │ enqueue Cloud Task
                                       ▼                           ▼
                       ┌──────────────────────────┐   ┌─────────────────────────────┐
                       │  Firestore                │   │  Cloud Tasks                 │
                       │  care_plan_outputs         │   │  care-plan-jobs (main app)   │
                       │  trial_rate_limits         │   │  care-plan-jobs-trial (trial)│
                       └──────────────┬─────────────┘   └───────────────┬───────────────┘
                                      │  live listener (client)          │ OIDC-signed POST
                                      │                                  ▼
                                      │                  ┌───────────────────────────────┐
                                      │                  │ Cloud Run: juno-worker          │ max-instances=5
                                      │                  │ (JUNO_MODE=worker)               │ min-instances=0
                                      │                  │ no-allow-unauthenticated,        │
                                      │                  │ internal ingress                 │
                                      │                  │ routes/worker.py                 │
                                      │                  └───────────────┬───────────────────┘
                                      │                                  │
                                      │                          Vertex AI (Gemini)
                                      │                          GCS bucket:
                                      │                            care_plan/{uid}/inputs/…      (main app)
                                      │                            care_plan_trial/{uid}/inputs/… (trial)
                                      └──────────────────────────────────┘

  Daily: Cloud Scheduler ──► Cloud Run Job juno-trial-anon-cleanup ──► Firebase Auth
  (confirmed live and ENABLED in GCP, with a real recorded invocation — see §5.4; not
  yet created by any checked-in workflow, so a from-scratch deploy would not recreate it)
```

**Hosting split.** `firebase.json` declares two hosting targets, each with its own
`public` directory and an SPA rewrite:

```json
"hosting": [
  { "target": "trial", "public": "frontend-trial/dist", ... },
  { "target": "app",   "public": "frontend/dist", ... }
]
```

`.firebaserc` maps those target names to actual Firebase Hosting sites within the single
`juno-medical-clarity` Firebase project: `trial` → `juno-medical-clarity` (the project's
primary/default site — the trial therefore lives at the address the full app used to
occupy), `app` → `juno-app-99` (a second site created specifically to receive the
relocated full app, at `juno-app-99.web.app`). There is no custom domain on either side.

**Cloud Run services.** `juno-api` and `juno-worker` are the same Flask application
(`backend/app.py`) deployed twice, distinguished only by `JUNO_MODE` and which blueprint
list it registers (`routes/__init__.py`; see care-plan-pipeline.md §1 for the
API/worker split itself). `juno-api` is `--allow-unauthenticated` (it's the public
front door for both the trial and the full app) with `max-instances=10`; `juno-worker`
is `--no-allow-unauthenticated --ingress=internal` (reachable only via Cloud
Tasks-signed OIDC requests) with `max-instances=5`. The design intends
`min-instances=0` for both; `juno-worker` is live at effectively 0, but **`juno-api` is
confirmed live at `min-instances=1`, not 0** — see §8 for why. These max-instances
numbers are wired into `.github/workflows/deploy.yml` via `API_MAX_INSTANCES`/
`WORKER_MAX_INSTANCES` env vars in the `deploy-backend` job.

**Cloud Tasks queues.** Two separate queues exist so trial traffic cannot starve or be
starved by main-app job dispatch: `care-plan-jobs` (main app) and `care-plan-jobs-trial`
(trial, `max-concurrent-dispatches=5`, `max-dispatches-per-second=2` per
`deploy.yml`'s idempotent `gcloud tasks queues create ... || echo "queue already
exists"` step). `backend/routes/trial.py` reads the trial queue's name from the
`CLOUD_TASKS_QUEUE_TRIAL` env var; see care-plan-pipeline.md §3.3 for the dispatch
mechanics shared by both queues.

**Firestore.** One collection, `care_plan_outputs`, is shared between trial and
main-app job documents (§6.1) — there is no separate `trial_jobs` collection (a
proposal from the original brainstorm that was explicitly rejected in favor of reusing
existing job-creation helpers, per `.dev/trial-simplify/README.md`'s Locked Decisions).
A second collection, `trial_rate_limits`, exists only for the trial's per-IP counters
(§5).

**GCS bucket.** One bucket, `juno-medical-clarity-backend`, holds both main-app uploads
(`care_plan/{uid}/inputs/{uuid}.pdf`) and trial uploads
(`care_plan_trial/{uid}/inputs/{uuid}.pdf`) under distinct prefixes — the prefix split
exists specifically so a GCS lifecycle rule can target only trial data (§6.1, §6.3).

**Vertex AI.** Treated as a black box exactly as in care-plan-pipeline.md: the trial
sends it the same OCR and pipeline-stage requests any main-app job would (same model,
same prompts, same token budgets), and processes the response the same way. No
trial-specific prompt or model exists.

---

## 2. Auth model and the trust boundary

**D1 (locked decision): anonymous Firebase Auth.** The trial has no login screen. On
page load, `frontend-trial/src/hooks/useAnonAuth.ts` calls Firebase's
`signInAnonymously()` and subscribes to `onAuthStateChanged`; once a non-null user
arrives, `authState` becomes `'ready'`. If neither the sign-in promise nor the auth
listener produces a user within `AUTH_TIMEOUT_MS` (10 seconds), `authState` becomes
`'error'` and a retry affordance is shown (`useAnonAuth.ts:15,33-37` — this bounded
timeout was itself an edge-case-review fix; an earlier version could hang in `'pending'`
forever with no actionable UI).

**Token acquisition per request.** `frontend-trial/src/api/trialApi.ts`'s
`getCurrentUser()` does not assume auth has already settled by the time a request is
made: it checks `firebaseAuth.currentUser`, then waits up to `AUTH_WAIT_TIMEOUT_MS`
(5000 ms) for `onAuthStateChanged`, and if still nothing, attempts one self-heal
`signInAnonymously()` call before giving up (`trialApi.ts:23-71`). This covers the
startup race where a user clicks "Simplify" before the mount-time sign-in has resolved.
`getIdToken()` failures are caught and mapped to a plain-English message that never
mentions "signing in" — the code comment is explicit that a no-login trial must never
surface sign-in language to the user (`trialApi.ts:73-89`). The resulting Firebase ID
token is sent as `Authorization: Bearer <token>` on every `/trial/jobs` request.

**Backend verification.** `backend/utils/firebase.py:verify_firebase_token` is the same
decorator used by every authenticated route in the app. It calls
`auth.verify_id_token(token)` (signature/issuer/expiry via the Firebase Admin SDK), then
inspects the decoded token's `firebase.sign_in_provider` claim
(`_is_anonymous_token`, `firebase.py:83-91`) to determine whether the caller is an
anonymous user.

**The trust boundary, precisely stated:** a Firebase ID token minted by
`signInAnonymously()` on the public trial site is a *valid, correctly-signed* credential
against the same Firebase project the full app uses. Nothing about the token itself
marks it as "trial-only" from the perspective of Firebase's own verification — it is a
real, verifiable identity. The decorator therefore defaults to **deny**: if
`is_anonymous` is true and the route did not explicitly pass `allow_anonymous=True`, the
request is rejected with `403 ANONYMOUS_ACCESS_FORBIDDEN` (`firebase.py:104-153`,
specifically the `if is_anonymous and not allow_anonymous:` check). Only two routes in
the entire application opt into `allow_anonymous=True`: `POST /trial/jobs` and
`DELETE /trial/jobs/<job_id>` (`routes/trial.py:97,158`). Every other authenticated
route — datasets, Athena presets, grading, admin, saved outputs, batch jobs, and
`POST /care_plan/jobs` itself — silently rejects an anonymous token before its own
handler ever runs.

This deny-by-default posture was not the original design — it was a specific fix
(`fec11a37`, per `.dev/trial-simplify/README.md`'s review log) added after a security
review found that, without it, an anonymous token minted for the trial would work as an
unthrottled, unbounded-cost backdoor into every authenticated main-app endpoint,
completely bypassing the trial's own rate limit (§5). The worker's own inbound auth
(Cloud Tasks OIDC verification, `verify_oidc_token`, `firebase.py:180-238`) is a
separate, unrelated trust boundary — see care-plan-pipeline.md §3.4 for that mechanism;
anonymous Firebase tokens play no role in it.

---

## 3. The trial API surface (`backend/routes/trial.py`)

Two endpoints, both requiring `Authorization: Bearer <anonymous Firebase ID token>`.

### `POST /trial/jobs`

Accepts either:
- **Pasted text** — `text` form field or JSON body field. Validated with the same
  `validate_extracted_text_length` used by the main app (care-plan-pipeline.md §2.8):
  500,000-character and 350,000-UTF-8-byte caps, plus the unstorable-text check.
- **File upload(s)** — `files` (multipart), up to `Constants.Trial.MAX_FILE_COUNT` = 5,
  aggregate ≤ `Constants.Trial.MAX_AGGREGATE_FILE_BYTES` = 10 MB, **no per-file cap**
  (`trial.py:72-78`) — a deliberately more-permissive-per-file/tighter-in-aggregate
  policy than the main app's 10 files / 10 MB-per-file / 25 MB-aggregate limits, which
  this route does not touch. `tolerate_unusable_files=True` means one bad file (blank
  scan, corrupt PDF, unsupported type) is skipped rather than aborting the whole
  request — the request only fails if *no* file yields usable content.

**Fields the client cannot control, and why:**

| Field | What the client sends | What actually happens |
|---|---|---|
| `version` | Not accepted at all — there is no version field in the trial's request shape | Hard-coded server-side to `Constants.Pipeline.PIPELINE_VERSION_V1_2` (`trial.py:54,86`). No version selector exists in the trial UI. |
| `grading_enabled` | Not accepted | Hard-coded `True` (`trial.py:55,87`) — the trial always computes readability scores; there is no opt-out. |
| `doc_id` | Not accepted — the trial has no prior-upload concept to reference, since there is no login and nothing persists across sessions | The trial input resolver (`_resolve_trial_input`) only ever produces `input_source_kind` of `"text"` or `"upload"`; `doc_id`-based re-runs are exclusively a main-app capability (care-plan-pipeline.md §2.1). |

This is a narrower request surface than `POST /care_plan/jobs` by construction, not by
filtering out fields after the fact — `_resolve_trial_input` (`trial.py:37-92`) simply
never reads or writes those fields.

**Response contract.** On success: `202 {"job_id": "<uuid>"}`. On a client input error:
`400` with the standard `ApiResponse` error envelope (`INPUT_VALIDATION_ERROR`, or the
`JunoError`'s own code/status for a classified failure like `EMPTY_DOCUMENT`). On a
missing/misconfigured Cloud Tasks queue: `500 INTERNAL_ERROR`, logged server-side — this
route deliberately validates `CLOUD_TASKS_QUEUE_TRIAL`/`WORKER_URL`/
`WORKER_SERVICE_ACCOUNT` via `require_env` *before* writing the Firestore job doc
(`trial.py:114-122`), so a config error can never orphan a job document with no task
behind it (the main-app route does not have this ordering guarantee — see
care-plan-pipeline.md §3.3).

**Job-status polling contract.** The route itself never streams status. The client
polls by attaching a live Firestore listener directly to the `care_plan_outputs/{job_id}`
document (`frontend-trial/src/hooks/useTrialJobSnapshot.ts`) and reads `status`/`stage`
as the worker updates them (care-plan-pipeline.md §3.2, §3.5). There is no
trial-specific polling endpoint — the trial relies on the same Firestore document shape
and lifecycle the main app uses.

### `DELETE /trial/jobs/<job_id>`

Not rate-limited (`trial.py:158`'s comment cites this as a reviewed decision — deletion
is a cleanup action, not a cost-incurring one). Requires the caller's `uid` to match
`data["uid"]` **and** `data["is_trial"]` to be true (`trial.py:175`) — both checks are
required so a trial-scoped delete endpoint can never be used to delete a main-app
document even if a `uid` collision were somehow possible. On success: best-effort GCS
cleanup of the stored input PDF (`delete_gcs_object`, swallows its own errors, never
raises) followed by `ref.delete()`, returning `204`. On a missing document: `404
RESOURCE_NOT_FOUND`. On an ownership/trial mismatch: `403 RESOURCE_FORBIDDEN`.

---

## 4. Abuse protection (`backend/utils/rate_limit.py`)

**D4/D11 (locked decisions): per-IP rate limit + hard caps + a Cloud Run ceiling, no
CAPTCHA.** The rate limiter is Firestore-backed rather than in-memory, because Cloud
Run's autoscaled, non-shared-memory instances cannot share an in-process counter
(module docstring, `rate_limit.py:1-4`).

**The limit itself.** 5 requests per IP per fixed wall-clock hour
(`Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR = 5`). The counter document ID is
`{ip_hash}_{window_start:%Y%m%d%H}` in the `trial_rate_limits` collection; a Firestore
transaction (`_check_and_increment`, `rate_limit.py:156-163`) atomically reads the
current count and increments it only if under the limit, avoiding a check-then-write
race between concurrent requests from the same IP. This is a **fixed** window, not
sliding — the module's own docstring flags this as a known, accepted limitation: an IP
sending 5 requests just before an hour boundary and 5 more just after can get 10 through
within seconds (`rate_limit.py:170-178`).

**Deriving the client IP.** `get_client_ip()` reads `X-Forwarded-For` and takes the
value `TRIAL_TRUSTED_PROXY_HOPS` positions from the *right* end
(`rate_limit.py:90-118`). This is deliberate, not the traditional "first XFF value"
convention: everything to the left of the trusted-hop boundary is client-supplied and
spoofable, and only what a trusted proxy itself appended can be relied on. The constant
is `1` today (`Constants.Trial.TRUSTED_PROXY_HOPS`), and the code's own extensive
citation (`rate_limit.py:30-56`) explains why: this deployment reaches `juno-api`
directly on its `*.run.app` URL with no External/Classic Load Balancer, Cloud Armor, or
CDN in front of it — verified (per the comment) by a live `gcloud compute url-maps list`
returning `PERMISSION_DENIED`/`SERVICE_DISABLED` because the Compute Engine API itself
is disabled on this project. Cloud Run's own front end is therefore the only proxy hop,
and Google's documented behavior appends exactly one IP (the real client's) to the right
of whatever `X-Forwarded-For` value a client sent in. **Why this would break under an
extra proxy layer:** a Global External Application Load Balancer appends *two* values
(`"<existing>,<client-ip>,<lb-ip>"` per Google's own docs) — if this deployment is ever
placed behind a GCLB or any other additional trusted proxy, `TRUSTED_PROXY_HOPS` must
become `2` (select the second-to-last value, not the last), or every real client behind
that proxy would collapse onto the load balancer's own IP as a single rate-limit bucket.
The value is exposed as the `TRIAL_TRUSTED_PROXY_HOPS` env var specifically so this
correction never requires a code change. If the header has fewer values than the
configured hop count, the code falls back to `request.remote_addr` rather than trusting
an unverified position (`rate_limit.py:107-118`).

**IP hashing.** Client IPs are never stored in plaintext; `_hash_ip` computes
`HMAC-SHA256(salt, ip)` truncated to 20 hex characters, keyed by the
`TRIAL_RATE_LIMIT_SALT` env var (a GitHub Actions secret). **Fail-safe fallback:** if the
salt is unset, the code does not fall back to unsalted SHA-256 (which would have been
trivially reversible against the small IPv4 address space, turning the collection into
an effective plaintext IP log) — instead it falls back to a random, process-local
32-byte salt generated once at import time (`_FALLBACK_IP_HASH_SALT`,
`rate_limit.py:20-25`), logged at `ERROR` since a missing salt in production is a
misconfiguration to fix, not a routine condition. The accepted cost of this fallback is
that rate-limit buckets for the same IP will not match across process
restarts/instances until the env var is actually set.

**Fail-open, by design.** Any exception raised while checking the rate limit (e.g. a
transient Firestore error) is caught in `rate_limit_trial`'s wrapper and the request is
allowed through (`rate_limit.py:199-206`) — explicitly documented as an
availability-over-strict-enforcement choice appropriate to an abuse guard on a free
feature, not a security boundary.

**Hard caps as a second layer, independent of the rate limiter.** Regardless of how many
requests an IP has made this hour, a single trial request is capped at 5 files and 10 MB
aggregate (§3, `Constants.Trial.MAX_FILE_COUNT`/`MAX_AGGREGATE_FILE_BYTES`) — these are
trial-only limits, tighter in aggregate than the main app's. `frontend-trial/src/utils/
validateFiles.ts` mirrors the same numbers client-side (own comment: "keep these two
values in sync" — there is no shared/generated source of truth between the Python and
TypeScript copies, so this is a manual-sync convention, not an enforced invariant).

**The cost backstop.** Above both of these sits the Cloud Run `max-instances` ceiling
(§1: `juno-api`=10, `juno-worker`=5) — even a rate-limit-evading or distributed abuse
pattern cannot spin up unbounded concurrent Cloud Run instances or unbounded concurrent
Cloud Tasks dispatches (the trial queue is itself capped at 5 concurrent
dispatches/2-per-second, §1), which bounds worst-case Vertex AI spend independently of
the per-IP logic above.

**No CAPTCHA.** This is an explicit, locked design decision (D4), not an oversight — a
per-IP rate limit, hard file/size caps, and the Cloud Run ceiling were judged sufficient
for a free demo tool, and a CAPTCHA/Turnstile step was traded off against the added
friction it would add to a deliberately frictionless trial experience.

---

## 5. Data management

This section tracks every piece of user-submitted data from the moment it is received to
the moment every copy of it is expected to be gone.

### 5.1 What is stored, where, and in what shape

| Store | Shape | Trial-specific markers |
|---|---|---|
| Firestore `care_plan_outputs` (shared with the main app) | One `JobDoc` per job (care-plan-pipeline.md §3.2) | `is_trial: true`; `expires_at` (a Firestore `Timestamp`, `now + Constants.Trial.JOB_TTL_HOURS` = 1 hour, set at job creation, `trial.py:129`, `models/job.py:77-78,167-195`) |
| Firestore `trial_rate_limits` | One doc per `{ip_hash, hour}` (§4) | Entirely trial-only; carries its own `expires_at` set to the rate-limit window's end plus `RATE_LIMIT_COUNTER_TTL_HOURS` (2h) buffer, so the TTL sweep has margin past the window's own natural expiry |
| GCS bucket `juno-medical-clarity-backend` | Merged audit-copy PDF of the original submission (care-plan-pipeline.md §2.5) | Trial uploads write to `care_plan_trial/{user_id}/inputs/{uuid}.pdf`, a prefix distinct from the main app's `care_plan/{uid}/inputs/{uuid}.pdf`. This split was a deliberate, later addition (`.dev/trial-simplify/README.md`'s Locked Decisions): the original design put both under the identical `care_plan/` shape, which gave a GCS lifecycle rule no safe way to distinguish trial objects from main-app objects. Moving trial uploads to their own prefix is what makes a prefix-scoped lifecycle rule (§5.3) safe. |

The `care_plan_outputs` collection is intentionally **shared**, not split into a
separate `trial_jobs` collection — reusing the existing job-doc model and
create/complete/fail helpers was judged simpler than forking storage, at the cost of
every reader of that collection needing to check `is_trial` before assuming main-app
semantics.

### 5.2 Every deletion path, and its timing

1. **Explicit client `DELETE /trial/jobs/<id>`** (primary path, effectively immediate).
   Fired by `ResultScreen.tsx` the instant the result screen mounts for a
   completed-or-errored job (`ResultScreen.tsx:32-36`) — the user does not need to
   navigate away or close the tab for this to happen. Guarded by a shared `deletedRef`
   `Set` so it can never double-fire alongside the unload-cleanup path below.
2. **Best-effort `DELETE` on page unload.** `useUnloadCleanup.ts` wires
   `window.pagehide` (fires on genuine navigation-away/teardown, including bfcache
   eviction) for any non-upload app state, and `visibilitychange`→`hidden` *only* once
   `appState === 'result'` — deliberately **not** while `processing`, because an earlier
   version wired `visibilitychange` unconditionally and was found to delete perfectly
   healthy, still-running jobs the instant a user switched tabs or locked their phone
   (`useUnloadCleanup.ts:5-27`). A processing job that gets abandoned mid-flight is left
   to the TTL backstop (item 5), not force-deleted.
3. **GCS input cleanup.** The worker's `finally` block deletes the trial's stored input
   PDF unconditionally at the end of job execution — success, failure, or
   exception — via `delete_gcs_object` (best-effort, swallows its own errors)
   whenever `job.is_trial` and `job.input_pdf_gcs_uri` are set (`routes/worker.py:
   315-317`). This runs once per job, after the pipeline has already extracted whatever
   text it needed from the stored PDF.
4. **`input_text` clearing on completion.** `complete_job`/`fail_job` accept a
   `clear_input_text` flag, passed as `is_trial` on every call site in
   `routes/worker.py` (e.g. lines 132, 174, 191, 228, 298) — so a trial job's raw
   `input_text` field on the Firestore document itself is deleted at the same moment the
   job reaches a terminal status, regardless of whether it succeeded or failed. (The
   *serialized* copy of the input inside `output_data.input.text` is separately trimmed
   at the pipeline-output level — see care-plan-pipeline.md §5.)
5. **Firestore native TTL backstop.** `expires_at` (1 hour from job creation, or the
   rate-limit counter's own window-based `expires_at`) is a field Firestore's native TTL
   feature can be configured to sweep on — see §5.4 for whether this configuration is
   actually active.
6. **GCS lifecycle rule on `care_plan_trial/`.** An `age: 1` day, `Delete` rule scoped to
   `matchesPrefix: ["care_plan_trial/"]` — see §5.4, this one **is** confirmed live.
7. **Daily anonymous-Auth-account cleanup.** A Cloud Run Job
   (`juno-trial-anon-cleanup`, entrypoint `backend/scripts/cleanup_anonymous_users.py` →
   `backend/services/retention.py:cleanup_anonymous_users`) intended to run daily via
   Cloud Scheduler, deleting anonymous Firebase Auth accounts (no linked sign-in
   provider — `_is_anonymous` in `retention.py:29-45`) older than
   `DEFAULT_MAX_AGE_HOURS` = 24. Gated by a `RETENTION_DRY_RUN` env var (default `true`)
   so the job can be deployed once and later flipped to actually delete — see §5.4 for
   current status. This targets Auth accounts, not Firestore/GCS data — it's a separate
   cleanup surface (an abandoned anonymous identity, not an abandoned job document).

### 5.3 Worst-case data lifetime, and how it's described to users

A trial job's `expires_at` is 1 hour past creation. Firestore's documented native-TTL
behavior is a sweep with SLA "typically within 24 hours" of the expiry timestamp, not an
immediate delete. Worst case, if neither the explicit `DELETE` nor the unload-cleanup
path ever fires (e.g. the user closes the tab mid-processing and never returns): **1
hour (`expires_at`) + up to ~24 hours (TTL sweep latency) ≈ 25 hours** before the job
document is guaranteed gone. The Privacy Policy (`frontend-trial/src/pages/
PrivacyPage.tsx`) reflects this honestly rather than promising immediacy: "The job
record ... is deleted as soon as your browser has finished displaying your
results ... As a safety net ... an automatic backstop still removes it, **typically
within a day**" (`PrivacyPage.tsx:66-72`) — not "within an hour." Per
`.dev/trial-simplify/README.md`, an earlier draft of this copy did say "generally within
an hour" and was corrected specifically because it overclaimed relative to Firestore's
actual TTL SLA; that correction is what's live in the current file.

### 5.4 Deployment status — what is actually live, and what is code-complete but unconfirmed

This section previously reported a three-way disagreement between the code, the
planning docs, and a dedicated live-GCP verification pass. That disagreement is now
resolved: a fresh, dated, read-only live-GCP check
(`.dev/trial-simplify/gcp-verification-2026-09-06.md`) directly queried every piece of
this infrastructure on 2026-09-06 and found all of it live. What follows states the
verified live state and which prior source it vindicates.

- **GCS lifecycle rule on `care_plan_trial/` — confirmed live.** `deploy.yml`'s
  "Apply GCS lifecycle rule for trial uploads" step (added in commit `ce7aace2`,
  2026-09-06) applies the age-1-day delete rule idempotently on every production deploy.
  Re-confirmed directly (`gsutil lifecycle get`) on 2026-09-06: exactly one rule, delete
  at age 1 day, scoped to `care_plan_trial/`. Uncontested by any source, live or
  otherwise.
- **Firestore native TTL on `care_plan_outputs.expires_at` / `trial_rate_limits.expires_at`
  — EXISTS, confirmed live.** `gcloud firestore fields ttls list`, re-run on 2026-09-06,
  reports both fields' `ttlConfig.state` as `ACTIVE`. This vindicates
  `.dev/trial-simplify/gcp-verification-2026-09-05.md`'s finding from the prior day;
  `.dev/trial-simplify/README.md`'s "Infrastructure already provisioned" section and its
  manual-steps checklist item 9, which still list the `gcloud firestore fields ttls
  update` commands as outstanding, are stale and were never folded back to reflect the
  live state.
- **`juno-trial-anon-cleanup` Cloud Run Job — EXISTS, dry-run tested, and now live-run
  tested too.** `deploy.yml`'s "Deploy anonymous-user-cleanup Cloud Run Job" step
  (`deploy.yml:97-110`) deploys `gcloud run jobs deploy juno-trial-anon-cleanup` on every
  production deploy. Direct inspection on 2026-09-06 (`gcloud run jobs
  executions list` + `gcloud logging read`) found two completed executions: a dry run
  (`dry_run=True`, `scanned=6 matched=0 deleted=0`, run manually) — matching commit
  `8f3e4693`'s and `final-verification-2026-09-05.md`'s reported numbers exactly — and,
  since then, a live non-dry-run execution (`dry_run=False`, same
  `scanned=6 matched=0 deleted=0`) triggered by `juno-scheduler-invoker`, i.e. by Cloud
  Scheduler itself, not a human. The Job's current live env var is
  `RETENTION_DRY_RUN=false` (flipped after commit `8f3e4693` pinned it to `true`,
  consistent with README's own Manual Steps item 8 recording that flip). This
  contradicts and supersedes the README's "Not yet created" bullet for this item, and
  goes beyond `final-verification-2026-09-05.md`'s claim — the live check found an
  actual production (non-dry-run) execution, not just a dry run.
- **Cloud Scheduler trigger for that Job — EXISTS, ENABLED, and end-to-end verified with
  a real invocation.** `gcloud services list --enabled` on 2026-09-06 shows
  `cloudscheduler.googleapis.com` enabled (the 2026-09-05 check found it disabled — an
  accurate snapshot of an earlier state, since changed). `gcloud scheduler jobs list
  --location=us-central1` shows `juno-trial-anon-cleanup-daily`, schedule `0 4 * * *`
  `Etc/UTC`, state `ENABLED`, targeting the Cloud Run Job's `:run` endpoint via OAuth as
  `juno-scheduler-invoker@juno-medical-clarity.iam.gserviceaccount.com`. Its
  `lastAttemptTime` (`2026-09-06T01:31:43.592078Z`) matches the Cloud Run Job execution
  `juno-trial-anon-cleanup-p4jg4`'s creation time to the millisecond, and that
  execution's `RUN BY` is the scheduler's own invoker service account — direct,
  first-hand proof of a real scheduler-triggered invocation, not merely a config that
  claims to be wired up. This vindicates `final-verification-2026-09-05.md`'s claim that
  the trigger is `ENABLED` and end-to-end verified. **No file in this repository
  (`deploy.yml` or otherwise) creates this Scheduler job or its IAM binding as checked-in
  infrastructure-as-code** — it exists live in GCP but not (yet) reproducibly from a
  fresh deploy; that gap is worth tracking even though the live resource itself is
  confirmed present and working.

**Net honest statement, updated 2026-09-06:** all four retention mechanisms — the GCS
lifecycle rule, both Firestore TTL policies, the cleanup Cloud Run Job, and its Cloud
Scheduler trigger — are live in production and have been directly verified with
read-only GCP commands (`.dev/trial-simplify/gcp-verification-2026-09-06.md`). The
Scheduler trigger has already fired once for real and deleted nothing (because nothing
matched, per its own logs). The one remaining gap is that the Scheduler job and its IAM
binding are not created by any checked-in workflow — a re-deploy from scratch would not
recreate them.

---

## 6. Frontend architecture (`frontend-trial/`)

**A separate Vite project in the same repo**, its own `package.json`,
`node_modules`, `vite.config.ts`, and `tsconfig.json` — not a second entry point inside
`frontend/`.

**What it shares with `frontend/src`, and how.** Exactly four things, via a path alias
(`@main/*` → `../frontend/src/*`, `vite.config.ts` and `tsconfig.app.json`):
`CarePlanView` (and its own dependency, `MedicalTerm`), `buildPdfHtml`, and the `types/`
directory. This is enforced by convention/code review, not by tooling — nothing stops a
future import of an unrelated `frontend/src` module through the same alias; PRD §4.4
records this as a deliberate scope boundary, not a technical one. `vite.config.ts`
additionally pins `react`/`react-dom` to `frontend-trial`'s own `node_modules` copies
ahead of the `@main` alias (`vite.config.ts:12-28`) — without this, the shared
components (which use hooks) would resolve React against `frontend/node_modules`
instead, creating a second React instance with its own unset hook dispatcher and
crashing on the first `useState` call.

**Screen flow.** `TrialPage.tsx` is a small state machine over `AppState` (`'upload' |
'processing' | 'result'`), holding `jobId` and a `finalJobDoc` snapshot:
- **Upload** (`UploadScreen.tsx`) — text or file input, client-side validation
  mirroring the server's caps (§4, §5.1).
- **Processing** (`ProcessingScreen.tsx`) — renders the five pipeline steps
  (care-plan-pipeline.md §4) driven by the live Firestore `stage` field, with a
  **watchdog**: if a job never reaches a terminal status within `WATCHDOG_TIMEOUT_MS` (6
  minutes — chosen to sit comfortably above both the worker's 270s internal deadline and
  the 300s Cloud Tasks dispatch deadline, while staying far below the ~24h TTL
  backstop), a "this is taking longer than expected... start over" affordance appears
  (`ProcessingScreen.tsx:17-32,81-84`). This exists specifically for the case where the
  worker container is hard-killed (OOM, crash) before its own `fail_job` call can run,
  leaving the Firestore doc stuck in `processing` with no other client-visible signal.
  "Start over" triggers `TrialPage.handleRestart`, which best-effort `DELETE`s the
  abandoned job (idempotent against the same `deletedRef` guard used everywhere else)
  rather than leaving cleanup solely to the TTL backstop.
- **Result** (`ResultScreen.tsx`) — renders `CarePlanView` (shared component) inside a
  local `ErrorBoundary`, fires the primary `DELETE` (§5.2 item 1), and offers **Download
  report**. The **error** sub-view (job status `error`) shows the error's `user_hint`
  and a **"Try again"** button that returns to the upload screen — a decision recorded as
  settled in the planning docs specifically for the error case; the **success** sub-view
  deliberately has no equivalent "Another care plan" button (also a settled,
  non-default choice).

**`useAnonAuth`'s pending-state timeout** is covered in §2. **Client-side caps**
(`utils/validateFiles.ts`) mirror the backend's file-count/aggregate-size/text-length/
text-byte limits (§4) — kept in sync by convention, not by a shared source of truth
between the Python and TypeScript copies.

**The `VITE_API_PROCESSING_URL` guard.** `api/firebase.ts` throws at module load if this
env var is unset (`firebase.ts:24-30`) — deliberately loud and immediate, because
leaving it unset makes every API call resolve to the literal string
`"undefined/trial/jobs"`, which 404s against the static hosting bucket with no hint of
the real cause. A trailing slash is also stripped to avoid a double-slash URL.

**The Firebase SDK error mapper.** Both `useAnonAuth` and `trialApi.getAuthHeader()`
catch raw Firebase SDK errors (e.g. `"Firebase: Error (auth/network-request-failed)."`)
and replace them with a plain-English message before they can reach a user-facing
catch-all (`trialApi.ts:79-87`) — an edge-case-review fix; raw SDK error text used to
reach the UI verbatim.

**Download-report path and `buildPdfHtml` hardening.** `downloadReport.ts` calls the
shared `buildPdfHtml` (every interpolated field passed through `escapeHtml`, verified
directly in `frontend/src/utils/buildPdfHtml.ts`), opens a blank `window.open('', '_blank')`,
writes the HTML into it, and then **explicitly nulls `printWindow.opener`**
(`downloadReport.ts:17-23`) before writing — `window.open` without the `noopener`
feature still leaves the new window holding a live `window.opener` handle back into the
trial tab, and since the write itself needs that handle (`document.write`), the fix nulls
it out immediately afterward rather than avoiding the handle altogether. This was a
specific, named fix (`5d1c226e` per the README's review log) for exactly this
window-opener risk plus the escaping itself.

---

## 7. Analytics (GA4)

Measurement ID `G-4R0CDYKSPW`, loaded and configured in
`frontend-trial/src/analytics/ga.ts` only when `VITE_GA_MEASUREMENT_ID` is set
(`ga.ts:1,42`) — deploys without that secret configured simply don't load GA at all,
rather than failing.

**Instrumented events** (`ga.ts:25-39`, all typed as a discriminated union so an
unrecognized event name is a compile error, not a silent typo): `page_view`,
`input_mode_selected`, `files_selected`, `simplify_clicked`, `simplify_submit_success`,
`simplify_submit_error`, `pipeline_step_start`/`pipeline_step_complete` (per pipeline
step, keyed by a fixed `step_id`/`step_key`, not a user-provided string),
`simplify_complete` (duration + before/after **scores**, not content),
`simplify_pipeline_error` (an `error_code` enum + numeric `stage_reached`, not the raw
error message), `report_downloaded`, `legal_link_clicked`, `auth_ready`, `auth_failed`.

**Verifying the hard "no document content" rule against the code, not just restating
it:** every event's parameter shape was read directly (`ga.ts:25-39` and every
`trackEvent(...)` call site in `UploadScreen.tsx`, `ProcessingScreen.tsx`,
`ResultScreen.tsx`, `Footer.tsx`, `App.tsx`). Every parameter is one of: a fixed literal
(`mode`, `input_mode`, `link`), a count (`file_count`), a category string built from
file extensions rather than filenames (`file_types`), a numeric ID/duration/score
(`step_id`, `total_duration_ms`, `score_before`/`score_after`), an `error_code` enum
value, or a page path (`page_path`, `source_screen` — a route like `/` or `/privacy`,
never document content). No call site passes a filename, pasted-text value, extracted
text, or any field from `output_data.care_plan`. This holds up under direct
inspection — the rule as stated in the Privacy Policy (§8, `PrivacyPage.tsx:104-107`) is
accurate to the current code, not just an aspirational claim.

---

## 8. CI/CD and deploy

Three workflows: `.github/workflows/ci.yml`, `deploy.yml`, `rollback-production.yml`
(a fourth, `preview.yml`, covers ephemeral PR-preview environments and is not detailed
here).

**What triggers a trial deploy.** `deploy.yml` listens for `workflow_run` on the `CI`
workflow completing on `main` (`deploy.yml:4-7`), gated on
`github.event.workflow_run.conclusion == 'success'` — **not** a bare `push` trigger.
This means a trial deploy can only happen after CI has actually run and passed against
the exact commit being deployed (`ref: github.event.workflow_run.head_sha`), structurally
preventing a merge-then-immediately-deploy race against an untested commit. On this
automatic path, `deploy-frontend` always builds and deploys the `trial` Hosting target
(`deploy_target trial`, unconditional, `deploy.yml:219`), but only builds/deploys the
`app` target when the trigger was a manual `workflow_dispatch`
(`if: github.event_name == 'workflow_dispatch'`, lines 148, 216-218).

**Why the relocated full app is never auto-deployed.** This asymmetry is deliberate: a
merge to `main` should be able to safely roll out trial changes continuously, but the
relocated full app (real user data, admin surface, saved outputs) only deploys when a
human explicitly runs the workflow via `workflow_dispatch`. A merge to `main` therefore
cannot accidentally push a change to `juno-app-99.web.app`.

**The CORS ordering constraint during cutover.** `backend/app.py`'s CORS `origins` list
includes both `https://juno-medical-clarity.web.app`/`.firebaseapp.com` (the trial's
address) and `https://juno-app-99.web.app`/`.firebaseapp.com` (the relocated app's new
address), plus a regex for PR-preview subdomains (`app.py:47-65`). Because the backend
is one shared Cloud Run deployment behind both frontends, the CORS allow-list must
already include the new `juno-app-99` origins *before* the relocated app can work at its
new address at all — the backend deploy step in `deploy.yml` runs ahead of the frontend
deploy step in the same job graph (`deploy-frontend` `needs: deploy-backend`), which is
what gives this ordering guarantee structurally rather than by discipline alone.

**Rollback path.** `rollback-production.yml` is `workflow_dispatch`-only, takes a
`prod_tag` input validated to match `prod-*` (tags created by `deploy.yml`'s own `tag`
job on every successful production deploy), and redeploys `juno-worker`/`juno-api` plus
**only the `app` Hosting target** (`target: app`, `rollback-production.yml`'s final
step) — it does not redeploy `frontend-trial`. A rollback therefore restores backend
behavior for both frontends (since they share the same Cloud Run services) but only
restores the full app's static assets, not the trial's; rolling back a bad trial
frontend deploy would need a separate, ordinary `deploy.yml` run pointed at an earlier
commit rather than this workflow.

**`min-instances=0`, no cold-start-masking (D7) — confirmed live-contradicted, not just
a code-vs-planning-doc disagreement.** The Locked Decisions record in
`.dev/trial-simplify/README.md` states D7 ("min-instances=0, no cold-start masking") now
"applies with no exceptions," citing a fix that corrected `rollback-production.yml`'s
`juno-api` step from a pre-existing `--min-instances=1` to `--min-instances=0`
(`.dev/trial-simplify/04-hosting-split-and-legal/PRD.md` §4.4/§9 Q4). That fix is real
and confirmed in the current `rollback-production.yml` (`--min-instances=0` on both the
`juno-worker` and `juno-api` deploy steps). **However, the primary, far-more-frequently-run
deploy path does not actually satisfy D7.** `deploy.yml`'s main backend step runs
`gcloud builds submit --config ./backend/cloudbuild.yaml`, and `backend/cloudbuild.yaml`
itself deploys `juno-api` with `--min-instances=1` (`cloudbuild.yaml:23`) — a flag never
touched by the PRD's rollback-only fix, and never revisited since (last modified in
pre-trial commits `a2cf8832`/`b16e9751`). `deploy.yml`'s subsequent `gcloud run services
update juno-api` step (the one that sets `max-instances`, env vars, and secrets) does not
pass `--min-instances` at all, and `gcloud run services update` only changes flags it is
given — so the `min-instances=1` set by `cloudbuild.yaml` is never reset to `0` on any
automatic trial deploy. **This was confirmed directly against live GCP on 2026-09-06**
(`.dev/trial-simplify/gcp-verification-2026-09-06.md`): `juno-api`'s live
`autoscaling.knative.dev/minScale` annotation is `1`, not `0` — not a theoretical
reading of the deploy config, the value actually running in production. **Net effect:
every merge-to-main auto-deploy currently leaves `juno-api` configured with at least one
always-warm instance, contradicting D7's "no exceptions" claim, and this is live right
now, not just latent in the deploy config** — only the rarely-used manual rollback path
actually deploys `juno-api` at `min-instances=0`. `juno-worker`'s `cloudbuild.yaml` step
does correctly set `--min-instances=0` (`cloudbuild.yaml:35`), confirmed live
(`juno-worker`'s live `minScale` is unset, i.e. effectively 0), so this discrepancy is
specific to `juno-api`. Whatever cold-start behavior a fresh visitor experiences today is
therefore better than the documented "no masking, ~15–30s wait after idle" description —
`juno-api` itself is being kept at least one instance warm in production — which may be a
harmless side effect or may be an unbudgeted, unreviewed cost the planning docs never
accounted for; this document does not resolve which, only that the two disagree and that
the live state, now confirmed, matches the code's `min-instances=1`, not D7's stated
intent.

---

## 9. Legal/compliance surface

`frontend-trial/src/pages/PrivacyPage.tsx` and `TermsPage.tsx` render at `/privacy` and
`/terms`, linked from `Footer.tsx` on every screen. Both are dated "Last updated:
September 4, 2026" as of this branch.

**What they claim, verified against this document's own findings:** the Privacy Policy's
data-retention section (§5.3 above) matches the actual code paths — explicit `DELETE` as
the primary, near-immediate mechanism, and an honest "typically within a day" framing
for the TTL backstop rather than an overclaim of immediacy. The Terms page states the
rate limit explicitly ("currently 5 per hour, subject to change without notice",
`TermsPage.tsx:71`), matching `Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR`. Both pages
disclaim medical advice and HIPAA coverage, and instruct users not to upload real PHI.

**Standing note — not yet lawyer-reviewed.** Per `.dev/trial-simplify/README.md`'s
Locked Decisions (D8) and its Consolidated Manual Steps, both pages are explicitly
recorded as a first draft, authored to be accurate to the implementation rather than
polished legal language, and reviewed for accuracy against the code by prior
agent passes — but not reviewed or approved by a lawyer. The README calls this "the one
item that gates launch." This document does not change that status; it only confirms the
copy is technically accurate to what the code does as of this branch.

**Cross-reference.** HIPAA posture and the broader compliance program are covered in
[`docs/hipaa-compliance-action-plan.md`](hipaa-compliance-action-plan.md) — not
restated here. The trial's own stance (not a HIPAA-covered service, no BAA, do not
upload real PHI) is a product-level containment decision layered on top of whatever that
document's action plan covers for the platform generally.

---

## 10. Known gaps and sharp edges

Sourced from `.dev/trial-simplify/edge-case-review-backend-2026-09-05.md`,
`edge-case-review-frontend-2026-09-05.md`, `final-verification-2026-09-05.md`, and
`review-2026-09-05-0835.md`, cross-checked against the current code.

- **Retention automation is fully deployed and live, verified directly against GCP on
  2026-09-06** — see §5.4 in full. This is no longer an open item: the GCS lifecycle
  rule, both Firestore TTL policies, the `juno-trial-anon-cleanup` Cloud Run Job, and
  its Cloud Scheduler trigger are all confirmed live, and the Scheduler trigger has
  already fired for real. The one remaining gap is that the Scheduler job and its IAM
  binding are not created by any checked-in workflow, so a from-scratch deploy would not
  recreate them.
- **`MAX_TEXT_BYTES=350,000` is enforced globally, not trial-only — an unresolved product
  decision.** This cap was added specifically for the trial's Firestore document-size
  safety (care-plan-pipeline.md §2.8), but `validate_extracted_text_length` is shared
  code, called from both `routes/trial.py` and `routes/care_plan_jobs.py`. The practical
  effect: the main app's previous 500,000-**character** ceiling is now also bounded by
  ~350,000 UTF-8 **bytes**, which narrows its effective limit for any document using
  more than one byte per character on average (and, in the ASCII case, simply caps it at
  350,000 characters outright — well under the nominal 500,000). `final-verification-
  2026-09-05.md` §3 flags this explicitly as found-but-not-fixed, needing an explicit
  owner call on whether the byte cap should be scoped to the trial route only.
- **`juno-api` deploys at `min-instances=1` on every automatic trial deploy, not `0`
  as D7 claims "with no exceptions"** (§8) — the primary deploy path
  (`backend/cloudbuild.yaml`, invoked from `deploy.yml`) was never updated when the
  rollback-only version of this same bug was fixed. Verified two ways: directly in the
  current `cloudbuild.yaml`, and directly against live GCP on 2026-09-06
  (`juno-api`'s live `minScale` annotation is `1`,
  `.dev/trial-simplify/gcp-verification-2026-09-06.md`) — this is a live production
  fact, not just a latent deploy-config issue.
- **Rate limiting is a fixed window, not sliding** (§4) — accepted, documented
  limitation, not a bug.
- **The rate limiter fails open** (§4) — a deliberate availability choice, not a gap, but
  worth restating plainly: a sustained Firestore outage would mean the trial has
  effectively no rate limit for its duration.
- **The `X-Forwarded-For` trusted-hop assumption is topology-specific** (§4) — correct
  today, silently wrong (under-attributing requests to the load balancer's own IP as one
  bucket) if an external proxy layer is ever added without updating
  `TRIAL_TRUSTED_PROXY_HOPS`.
- **The rollback workflow only restores the `app` Hosting target, not `trial`** (§8) — a
  scope gap worth knowing about before assuming a rollback fixes a bad trial frontend
  deploy.
- **Client/server cap duplication has no shared source of truth.** The file-count/
  aggregate-byte/text-length/text-byte limits are hand-mirrored between
  `backend/utils/constants.py` and `frontend-trial/src/utils/validateFiles.ts` — a
  `[DEFERRED]` open question in the SP3 PRD (moving these into one shared
  `frontend/src/constants.ts` import) was explicitly left unresolved rather than fixed,
  since it would touch `frontend/src`, outside that PRD's stated scope.
- **Legal-copy review is the standing launch gate** (§9) — not a code issue, included
  here only because it recurs across every one of the source review documents as the
  final blocking item.

